"""Build the golden datasets from the raw exports in dataset/.

    python3 golden/build_golden.py [--as-of YYYY-MM-DD]

Writes three Excel-friendly CSVs (UTF-8 with BOM, CRLF):

  golden/golden_requests.csv   one row per intro request. APPEND-ONLY: rows
                               already in the file are never changed; only
                               request_ids not yet present are appended.
  golden/golden_companies.csv  one row per real company (grouped by domain).
                               Always rebuilt from golden_requests.csv plus
                               crm_accounts.csv and supply_reach.csv.
  golden/supply_reach.csv      one row per way of reaching a company.

Company identity is the CRM domain, not the account name. A request or
connection row that names a company with no CRM record is resolved by
name/alias and, failing that, becomes its own company with no domain.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from golden.resolver import domain_stem, normalize, normalize_strict  # noqa: E402

DATASET = ROOT / "dataset"
OUT = ROOT / "golden"

REQUESTS_OUT = OUT / "golden_requests.csv"
COMPANIES_OUT = OUT / "golden_companies.csv"
SUPPLY_OUT = OUT / "supply_reach.csv"

REQUEST_COLUMNS = [
    "request_id", "company_id", "company_as_written", "requested_by", "request_date",
    "raw_ask", "value_usd", "urgency_declared", "status_as_filed", "routed_to", "routed_on",
    "route_score", "route_reason", "asked_date", "responded", "intro_sent", "meeting_booked",
    "opportunity_usd", "offer_in_thread", "thread_replies", "resolved_by", "needs_review",
]
COMPANY_COLUMNS = [
    "company_id", "company_name", "also_known_as", "domain", "industry", "crm_account_ids",
    "duplicate_accounts", "owner", "stage", "value_usd", "total_requests", "open_requests",
    "distinct_requesters", "latest_request_id", "latest_request_date", "latest_request_status",
    "routed_to", "routed_on", "route_reason", "paths_available", "best_path_type",
    "someone_offered", "days_since_movement",
]
SUPPLY_COLUMNS = [
    "connector", "connector_type", "company_id", "company_name", "reach_type", "contact_name",
    "contact_title", "observed_date", "strength", "in_focus_area", "monthly_capacity",
    "delivery_rate",
]

OPEN_STATUSES = {"Open", "Routed", "Stalled"}

# ---------------------------------------------------------------------------
# routing constants (same weights as halyard/relay)
# ---------------------------------------------------------------------------
SENIORITY = {
    "chief operating officer": 1.00, "chief data officer": 1.00, "chief digital officer": 1.00,
    "chief information officer": 1.00, "chief technology officer": 1.00,
    "svp digital": 0.85, "vp data & analytics": 0.85, "vp enterprise architecture": 0.80,
    "head of innovation": 0.70, "head of platform engineering": 0.70, "head of automation": 0.70,
    "head of developer productivity": 0.70, "product director": 0.65, "director of it": 0.65,
    "director of software engineering": 0.60, "principal architect": 0.50, "platform lead": 0.50,
    "senior manager, engineering": 0.45, "engineering manager": 0.40, "program manager": 0.35,
    "staff engineer": 0.30,
}
DEFAULT_SENIORITY = 0.45
PATH_BASE = {"board": 1.00, "investor": 0.72, "direct": 0.60, "alumni": 0.34}
PRIOR_RATE, PRIOR_WEIGHT = 0.38, 6.0
OFFER_RE = re.compile(
    r"happy to intro|leave it with me|i'll take this one|i met their|happy to reach out", re.I
)


def seniority(title: str) -> float:
    return SENIORITY.get((title or "").strip().lower(), DEFAULT_SENIORITY)


def freshness(connected_on: str, today: date) -> float:
    try:
        years = max(0, today.year - int(connected_on[:4]))
    except (TypeError, ValueError):
        return 0.8
    return max(0.55, 1.0 - 0.045 * years)


# ---------------------------------------------------------------------------
# io helpers
# ---------------------------------------------------------------------------
def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, columns: list[str], rows: list[dict], mode: str = "w") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = mode == "w" or not path.exists() or path.stat().st_size == 0
    with open(path, mode, newline="", encoding="utf-8-sig" if new_file else "utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\r\n", extrasaction="ignore")
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in columns})


def parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s.strip()[:10], "%Y-%m-%d").date()
    except (AttributeError, ValueError):
        return None


def money(s: str) -> str:
    try:
        return str(int(float(s)))
    except (TypeError, ValueError):
        return ""


# ---------------------------------------------------------------------------
# company registry: domain-first identity
# ---------------------------------------------------------------------------
class Company:
    def __init__(self, domain: str):
        self.domain = domain
        self.accounts: list[dict] = []
        self.names: Counter = Counter()  # every spelling seen anywhere
        self.how: dict[str, str] = {}    # spelling -> how it was matched to this company
        self.company_id = ""

    @property
    def survivor(self) -> dict | None:
        if not self.accounts:
            return None
        return sorted(self.accounts, key=lambda a: (a["account_id"].startswith("A9"), a["account_id"]))[0]

    @property
    def name(self) -> str:
        s = self.survivor
        if not s:
            return self.names.most_common(1)[0][0] if self.names else self.domain
        crm = s["account_name"]
        if crm.isupper():
            key = normalize_strict(crm)
            for n, _ in self.names.most_common():
                if normalize_strict(n) == key and not n.isupper():
                    return n
        return crm


class Registry:
    def __init__(self, accounts: list[dict]):
        self.by_domain: dict[str, Company] = {}
        self._strict: dict[str, Company] = {}
        self._loose: dict[str, Company] = {}
        self._stem: dict[str, Company] = {}
        for a in accounts:
            c = self.by_domain.setdefault(a["domain"].lower(), Company(a["domain"].lower()))
            c.accounts.append(a)
            c.names[a["account_name"]] += 1
            c.how.setdefault(a["account_name"], "crm-name")
        for c in self.by_domain.values():
            self._stem[domain_stem(c.domain)] = c
            for n in c.names:
                self._index(n, c)

    def _index(self, name: str, c: Company) -> None:
        self._strict.setdefault(normalize_strict(name), c)
        self._loose.setdefault(normalize(name), c)

    def resolve(self, raw: str, domain_hint: str = "") -> tuple[Company | None, str]:
        """Return (company, method). Never creates."""
        if domain_hint:
            c = self.by_domain.get(domain_hint.lower()) or self._stem.get(domain_stem(domain_hint))
            if c:
                return c, "domain"
            if not raw:
                raw = domain_stem(domain_hint)
        strict = normalize_strict(raw)
        if not strict:
            return None, "empty"
        if strict in self._strict:
            return self._strict[strict], "name-exact"
        if strict in self._stem:
            return self._stem[strict], "domain-stem"
        loose = normalize(raw)
        if loose in self._loose:
            c = self._loose[loose]
            # 'Apex Logistics Group' vs 'Apex Logistics' differ on a real word.
            if any(normalize_strict(n) == strict for n in c.names):
                return c, "name-exact"
            if strict.startswith(normalize_strict(c.name)) or normalize_strict(c.name).startswith(strict):
                return c, "name-loose"
            return None, "ambiguous"
        if loose in self._stem:
            return self._stem[loose], "domain-stem"
        if len(loose) >= 8:
            cands = {}
            for k, c in list(self._loose.items()) + list(self._stem.items()):
                if k and min(len(k), len(loose)) >= 8 and (k.startswith(loose) or loose.startswith(k)):
                    cands[c.domain] = c
            if len(cands) == 1:
                return next(iter(cands.values())), "name-prefix"
            if len(cands) > 1:
                return None, "ambiguous"
        return None, "unmatched"

    def resolve_or_create(self, raw: str, domain_hint: str = "") -> tuple[Company, str]:
        c, method = self.resolve(raw, domain_hint)
        if c is None:
            c = Company(domain_hint.lower())
            self.by_domain[domain_hint.lower() or f"~{normalize_strict(raw)}"] = c
            method = "new-company"
        if domain_hint and not c.domain:
            # a request supplied the email domain for a company the CRM lacks
            self.by_domain.pop(f"~{normalize_strict(c.name)}", None)
            c.domain = domain_hint.lower()
            self.by_domain[c.domain] = c
        if domain_hint:
            self._stem[domain_stem(domain_hint)] = c
        if raw and raw != domain_hint:
            raw = raw.strip()
            c.names[raw] += 1
            method = c.how.setdefault(raw, method)
            self._index(raw, c)
        return c, method

    def assign_ids(self) -> None:
        def sort_key(c: Company):
            return (0 if c.accounts else 1, c.domain or "~", c.name.lower())
        for i, c in enumerate(sorted(self.by_domain.values(), key=sort_key), 1):
            c.company_id = f"C{i:03d}"

    def companies(self) -> list[Company]:
        return sorted(self.by_domain.values(), key=lambda c: c.company_id)


# ---------------------------------------------------------------------------
# raw_ask parsing for requests with no target_company_raw
# ---------------------------------------------------------------------------
_ASK_PATTERNS = [
    re.compile(r"account I actually need is (?P<c>[^(.,]+?)\s*[\(.]"),
    re.compile(r"^(?P<c>[^.]+?) is the target\."),
    re.compile(r"trying to reach [^.]+? at (?P<c>[^.]+?)\.\s"),
    re.compile(r"we need (?P<c>[^.]+?)\.\s"),
]
_DOMAIN_RE = re.compile(r"email domain is (?P<d>[a-z0-9.-]+\.[a-z]{2,})", re.I)


def company_from_ask(text: str) -> tuple[str, str]:
    """-> (company string, domain hint)"""
    m = _DOMAIN_RE.search(text)
    if m:
        return "", m.group("d").lower()
    for pat in _ASK_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group("c").strip(), ""
    return "", ""


# ---------------------------------------------------------------------------
# supply side
# ---------------------------------------------------------------------------
def load_roster() -> dict[str, dict]:
    roster = {}
    for r in read_csv(DATASET / "connector_roster.csv"):
        r["focus"] = {x.strip() for x in r["focus_areas"].split(";") if x.strip()}
        r["hard_decline"] = "decline anything outside" in r["notes"].lower()
        roster[r["name"]] = r
    return roster


def delivery_rates(roster: dict, outcomes: list[dict]) -> dict[str, float]:
    asks, intros = Counter(), Counter()
    for o in outcomes:
        asks[o["connector_asked"]] += 1
        if o["intro_sent"] == "Y":
            intros[o["connector_asked"]] += 1
    return {n: (intros[n] + PRIOR_RATE * PRIOR_WEIGHT) / (asks[n] + PRIOR_WEIGHT) for n in roster}


def fit(connector: dict, industry: str) -> float:
    if not industry:
        return 0.7
    if industry in connector["focus"]:
        return 1.0
    if connector["hard_decline"]:
        return 0.0
    return 0.45


def build_supply(reg: Registry, roster: dict, rates: dict, today: date) -> list[dict]:
    rows: list[dict] = []
    person_to_connectors: dict[str, list[tuple[str, dict]]] = defaultdict(list)

    def emit(connector: str, company: Company, kind: str, contact: str, title: str, observed: str, strength: float):
        r = roster[connector]
        s = company.survivor
        industry = s["industry"] if s else ""
        rows.append({
            "connector": connector,
            "connector_type": r["type"],
            "_company": company,
            "company_id": "",
            "company_name": company.name,
            "reach_type": kind,
            "contact_name": contact,
            "contact_title": title,
            "observed_date": observed,
            "strength": f"{strength:.3f}",
            "in_focus_area": "yes" if industry and industry in r["focus"] else ("unknown" if not industry else "no"),
            "monthly_capacity": r["stated_monthly_capacity"],
            "delivery_rate": f"{rates[connector]:.3f}",
        })

    for name, r in roster.items():
        for c in read_csv(DATASET / r["connections_file"]):
            person_to_connectors[c["name"]].append((name, c))
            company, _ = reg.resolve_or_create(c["company"])
            s = PATH_BASE["direct"] * (0.55 + 0.45 * seniority(c["title"])) * freshness(c["connected_on"], today)
            emit(name, company, "direct", c["name"], c["title"], c["connected_on"], s)

    for inv in read_csv(DATASET / "investor_network.csv"):
        person = inv["person"]
        if inv["portfolio_company"] and person in roster:
            company, _ = reg.resolve_or_create(inv["portfolio_company"])
            kind = "board" if inv["board_seat"].lower() == "true" else "investor"
            emit(person, company, kind, "CEO / exec team",
                 f"{inv['fund']} {'board seat' if kind == 'board' else 'portfolio company'}", "", PATH_BASE[kind])
        if inv["prior_employer"]:
            company, _ = reg.resolve_or_create(inv["prior_employer"])
            for connector, conn in person_to_connectors.get(person, []):
                s = PATH_BASE["alumni"] * freshness(conn["connected_on"], today)
                emit(connector, company, "alumni", person,
                     f"ex-{inv['prior_employer']} ({inv['prior_employer_start']}-{inv['prior_employer_end']}), now {conn['title']} at {conn['company']}",
                     conn["connected_on"], s)
    return rows


# ---------------------------------------------------------------------------
# demand side
# ---------------------------------------------------------------------------
def load_threads() -> dict[str, dict]:
    out = {}
    with open(DATASET / "slack_threads.jsonl", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            t = json.loads(line)
            replies = t["messages"][1:]
            offer = any(OFFER_RE.search(m["text"]) for m in replies)
            out[t["request_id"]] = {"replies": len(replies), "offer": "Y" if offer else "N"}
    return out


def best_route(paths: list[dict], roster: dict, rates: dict, industry: str, exclude_connector: str = "") -> tuple[dict | None, float]:
    best, best_score = None, 0.0
    for p in paths:
        if p["connector"] == exclude_connector:
            continue
        f = fit(roster[p["connector"]], industry)
        score = float(p["strength"]) * f * rates[p["connector"]]
        if score > best_score:
            best, best_score = p, score
    return best, best_score


def build_requests(reg: Registry, roster: dict, rates: dict, supply_by_company: dict[str, list[dict]]) -> list[dict]:
    outcomes = {o["request_id"]: o for o in read_csv(DATASET / "intro_outcomes.csv")}
    threads = load_threads()
    rows = []
    for rq in read_csv(DATASET / "intro_requests.csv"):
        rid = rq["request_id"]
        written = rq["target_company_raw"].strip()
        domain_hint = ""
        parsed_from_ask = False
        if not written:
            written, domain_hint = company_from_ask(rq["raw_ask"])
            parsed_from_ask = bool(written or domain_hint)

        review = []
        if written or domain_hint:
            company, method = reg.resolve_or_create(written, domain_hint)
            if not written:
                written = domain_hint
            if parsed_from_ask:
                method = f"raw_ask:{method}"
            if not company.accounts:
                review.append("no CRM account")
        else:
            company, method = None, "unresolved"
            review.append("company not identifiable")

        s = company.survivor if company else None
        industry = s["industry"] if s else ""
        paths = supply_by_company.get(company.company_id, []) if company else []

        o = outcomes.get(rid)
        routed_to = routed_on = route_reason = ""
        route_score = ""
        if o:
            routed_to, routed_on = o["connector_asked"], o["asked_date"]
            if routed_to not in roster:
                route_reason = f"asked {routed_to}, who is not on the connector roster"
                review.append("asked person not on roster")
            else:
                own = [p for p in paths if p["connector"] == routed_to]
                bp, sc = best_route(own, roster, rates, industry)
                if bp:
                    route_score = f"{sc:.3f}"
                    route_reason = f"asked; {bp['reach_type']} path via {bp['contact_name']}"
                    if bp["contact_title"] and bp["reach_type"] == "direct":
                        route_reason += f" ({bp['contact_title']})"
                else:
                    route_reason = "asked; no known path from this connector to the company"
                    review.append("asked with no known path")
                alt, alt_sc = best_route(paths, roster, rates, industry, exclude_connector=routed_to)
                if alt and alt_sc > (sc or 0):
                    route_reason += f"; stronger path existed via {alt['connector']} ({alt['reach_type']}, {alt_sc:.2f})"
        else:
            bp, sc = best_route(paths, roster, rates, industry)
            if bp:
                routed_to = bp["connector"]
                route_score = f"{sc:.3f}"
                route_reason = f"recommended, not yet asked; {bp['reach_type']} path via {bp['contact_name']}"
                if bp["contact_title"] and bp["reach_type"] == "direct":
                    route_reason += f" ({bp['contact_title']})"
            elif company:
                route_reason = "not asked; no path to this company in the network"
            else:
                route_reason = "not asked; company unresolved"

        th = threads.get(rid, {"replies": 0, "offer": "N"})
        if not money(rq["deal_value_usd"]):
            review.append("no deal value")

        rows.append({
            "request_id": rid,
            "company_id": company.company_id if company else "",
            "company_as_written": written,
            "requested_by": rq["requested_by"],
            "request_date": rq["request_date"],
            "raw_ask": rq["raw_ask"],
            "value_usd": money(rq["deal_value_usd"]),
            "urgency_declared": rq["urgency"],
            "status_as_filed": rq["status"],
            "routed_to": routed_to,
            "routed_on": routed_on,
            "route_score": route_score,
            "route_reason": route_reason,
            "asked_date": o["asked_date"] if o else "",
            "responded": o["responded"] if o else "",
            "intro_sent": o["intro_sent"] if o else "",
            "meeting_booked": o["meeting_booked"] if o else "",
            "opportunity_usd": money(o["opportunity_value_usd"]) if o else "",
            "offer_in_thread": th["offer"],
            "thread_replies": th["replies"],
            "resolved_by": method,
            "needs_review": "; ".join(review) if review else "no",
        })
    rows.sort(key=lambda r: r["request_id"])
    return rows


def append_only_write(rows: list[dict]) -> tuple[int, int, list[str]]:
    """Append rows whose request_id is new. Existing rows are never touched.
    Returns (existing, appended, drift warnings)."""
    existing = read_csv(REQUESTS_OUT) if REQUESTS_OUT.exists() else []
    seen = {r["request_id"]: r for r in existing}
    if existing and list(existing[0].keys()) != REQUEST_COLUMNS:
        sys.exit(f"{REQUESTS_OUT} has a different column set; refusing to append.")
    warnings = []
    new = []
    for r in rows:
        old = seen.get(r["request_id"])
        if old is None:
            new.append(r)
            continue
        diff = [c for c in REQUEST_COLUMNS if str(old.get(c, "")) != str(r.get(c, ""))]
        if diff:
            warnings.append(f"{r['request_id']}: recomputed {', '.join(diff)} differ from filed row (kept filed)")
    write_csv(REQUESTS_OUT, REQUEST_COLUMNS, new, mode="a")
    return len(existing), len(new), warnings


# ---------------------------------------------------------------------------
# companies: rebuilt from golden_requests.csv every run
# ---------------------------------------------------------------------------
def build_companies(reg: Registry, supply: list[dict], today: date) -> list[dict]:
    requests = read_csv(REQUESTS_OUT)
    by_company = defaultdict(list)
    for r in requests:
        if r["company_id"]:
            by_company[r["company_id"]].append(r)
    supply_by = defaultdict(list)
    for s in supply:
        supply_by[s["company_id"]].append(s)
    outcomes = {o["request_id"]: o for o in read_csv(DATASET / "intro_outcomes.csv")}

    rows = []
    for c in reg.companies():
        reqs = sorted(by_company.get(c.company_id, []), key=lambda r: (r["request_date"], r["request_id"]))
        latest = reqs[-1] if reqs else None
        s = c.survivor
        owners = sorted({a["owner"] for a in c.accounts})
        if len(c.accounts) > 1:
            dup = "yes - owners disagree" if len(owners) > 1 else "yes - same owner"
        else:
            dup = "no"
        aka = sorted({n for n in c.names if n != c.name}, key=str.lower)
        if s:
            value = str(max(int(a["arr_potential_usd"] or 0) for a in c.accounts))
        else:
            vals = [int(r["value_usd"]) for r in reqs if r["value_usd"]]
            value = str(max(vals)) if vals else ""
        paths = supply_by.get(c.company_id, [])
        best = max(paths, key=lambda p: float(p["strength"]), default=None)

        moves = [parse_date(r["request_date"]) for r in reqs]
        for r in reqs:
            o = outcomes.get(r["request_id"])
            if o:
                moves += [parse_date(o[k]) for k in ("asked_date", "response_date", "intro_date")]
        for a in c.accounts:
            moves.append(parse_date(a["last_touch_date"]))
        moves = [m for m in moves if m]
        rows.append({
            "company_id": c.company_id,
            "company_name": c.name,
            "also_known_as": " | ".join(aka),
            "domain": c.domain,
            "industry": s["industry"] if s else "",
            "crm_account_ids": " | ".join(sorted(a["account_id"] for a in c.accounts)),
            "duplicate_accounts": dup,
            "owner": " | ".join(owners),
            "stage": s["stage"] if s else "",
            "value_usd": value,
            "total_requests": len(reqs),
            "open_requests": sum(1 for r in reqs if r["status_as_filed"] in OPEN_STATUSES),
            "distinct_requesters": len({r["requested_by"] for r in reqs}),
            "latest_request_id": latest["request_id"] if latest else "",
            "latest_request_date": latest["request_date"] if latest else "",
            "latest_request_status": latest["status_as_filed"] if latest else "",
            "routed_to": latest["routed_to"] if latest else "",
            "routed_on": latest["routed_on"] if latest else "",
            "route_reason": latest["route_reason"] if latest else "",
            "paths_available": len(paths),
            "best_path_type": best["reach_type"] if best else "",
            "someone_offered": "yes" if any(r["offer_in_thread"] == "Y" for r in reqs) else "no",
            "days_since_movement": (today - max(moves)).days if moves else "",
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=date.today().isoformat())
    args = ap.parse_args()
    today = parse_date(args.as_of) or date.today()

    reg = Registry(read_csv(DATASET / "crm_accounts.csv"))
    roster = load_roster()
    outcomes = read_csv(DATASET / "intro_outcomes.csv")
    rates = delivery_rates(roster, outcomes)

    # Register every spelling first (requests, connections, investors) so
    # company IDs are stable regardless of which file mentions a company.
    for rq in read_csv(DATASET / "intro_requests.csv"):
        written, hint = rq["target_company_raw"].strip(), ""
        if not written:
            written, hint = company_from_ask(rq["raw_ask"])
        if written or hint:
            reg.resolve_or_create(written, hint)
    supply = build_supply(reg, roster, rates, today)
    reg.assign_ids()
    for s in supply:
        s["company_id"] = s["_company"].company_id
        s["company_name"] = s["_company"].name
    write_csv(SUPPLY_OUT, SUPPLY_COLUMNS, supply)

    supply_by = defaultdict(list)
    for s in supply:
        supply_by[s["company_id"]].append(s)
    requests = build_requests(reg, roster, rates, supply_by)
    existing, appended, warnings = append_only_write(requests)

    companies = build_companies(reg, supply, today)
    write_csv(COMPANIES_OUT, COMPANY_COLUMNS, companies)

    print(f"golden_requests.csv   {existing + appended} rows ({existing} kept, {appended} appended)")
    print(f"golden_companies.csv  {len(companies)} rows (rebuilt)")
    print(f"supply_reach.csv      {len(supply)} rows (rebuilt)")
    for w in warnings:
        print("WARN", w)


if __name__ == "__main__":
    main()
