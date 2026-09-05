"""Build the golden datasets from the raw exports in dataset/.

    python3 golden/build_golden.py [--as-of YYYY-MM-DD]

Writes four CSVs (UTF-8, no BOM, CRLF):

  golden/golden_requests.csv   one row per intro request. APPEND-ONLY: rows
                               already in the file are never changed; only
                               request_ids not yet present are appended. New
                               columns may be added to the schema; existing
                               values are never rewritten.
  golden/golden_companies.csv  one row per in-scope company (grouped by
                               domain). Always rebuilt from golden_requests.csv
                               plus crm_accounts.csv and supply_reach.csv.
  golden/supply_reach.csv      one row per way into an in-scope company, from
                               four sources: direct (connections_*.csv),
                               alumni and investor (investor_network.csv;
                               board_seat = yes/no is a strength modifier, not
                               a separate type) and offer (someone volunteered
                               in a Slack thread).
                               Every askable person (roster, off-roster people
                               asked in intro_outcomes.csv, Slack volunteers)
                               has at least one row: reach_type = "none" if
                               they have no in-scope path. Connector-level
                               facts (capacity, asks, allocation) are repeated
                               on every row of that connector on purpose.
  golden/golden_allocation.csv one row per live, not-yet-asked request: the
                               connector it is allocated to this cycle, or an
                               exception (capacity exhausted this cycle / no
                               path / company unresolved). Rebuilt wholesale.
                               A connector is never allocated more than
                               stated_monthly_capacity minus asks already made
                               this cycle; everything allocated to one
                               connector shares one batch_id (one consolidated
                               ask per connector per cycle).

Scope. A company is in scope if it is in crm_accounts.csv or is named as the
target of any intro request. The set is recomputed on every run; nothing is
hard-coded. Connection / investor rows naming a company outside that set are
not emitted (the raw exports are left as delivered).

Company identity is the CRM domain, not the account name. Spellings from any
source are matched on the resolver's normalised key ("Blackwood Industrial" ->
"Blackwood Holdings"). A requested company with no CRM record becomes its own
company with no domain. company_ids are pinned to whatever the existing golden
files already use, so they never shift between runs.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
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
ALLOCATION_OUT = OUT / "golden_allocation.csv"

REQUEST_COLUMNS = [
    "request_id", "company_id", "company_as_written", "target_title", "requested_by", "request_date",
    "raw_ask", "value_usd", "urgency_declared", "status_as_filed", "routed_to", "routed_on",
    "route_score", "route_reason", "asked_date", "responded", "intro_sent", "meeting_booked",
    "opportunity_usd", "offer_in_thread", "thread_replies", "thread_all_noise", "resolved_by",
    "needs_review",
]
COMPANY_COLUMNS = [
    "company_id", "company_name", "also_known_as", "domain", "industry", "crm_account_ids",
    "duplicate_accounts", "owner", "stage", "value_usd", "largest_request_usd", "total_requests",
    "open_requests", "distinct_requesters", "targets_wanted", "latest_request_id",
    "latest_request_date", "latest_request_status", "routed_to", "routed_on", "route_reason",
    "paths_available", "durable_paths", "best_path_type", "someone_offered", "days_since_movement",
]
SUPPLY_COLUMNS = [
    "connector", "connector_type", "company_id", "company_name", "reach_type", "board_seat", "contact_name",
    "contact_title", "observed_date", "offer_age_days", "strength", "in_focus_area", "monthly_capacity",
    "delivery_rate", "connector_paths_total", "asks_received", "intros_sent", "awaiting_forward",
    "allocated_this_cycle", "idle_capacity", "last_asked_date", "evidence",
]

ALLOCATION_COLUMNS = [
    "cycle", "request_id", "company_id", "company_name", "target_title", "value_usd",
    "urgency_declared", "request_date", "status_as_filed", "allocated_to", "batch_id", "batch_size",
    "path_type", "contact_name", "route_score", "exception_reason", "best_path_if_unbudgeted",
]

MULTI = " | "  # delimiter for multi-value cells (never a comma)
OPEN_STATUSES = {"Open", "Routed", "Stalled"}
URGENCY_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
OFF_ROSTER_CAPACITY = 2  # monthly asks assumed for anyone askable who is not on the roster
CAPACITY_EXHAUSTED = "capacity exhausted this cycle"
# reach types that outlast the request they were observed on; offers are request-scoped
DURABLE_REACH = {"direct", "investor", "alumni"}

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
PATH_BASE = {"offer": 0.80, "investor": 0.72, "direct": 0.60, "alumni": 0.34}
BOARD_SEAT_STRENGTH = 0.90  # investor path when the connector's fund also holds a board seat
PRIOR_RATE, PRIOR_WEIGHT = 0.38, 6.0
OFFER_RE = re.compile(
    r"happy to intro|leave it with me|i'll take this one|i met their|happy to reach out", re.I
)
# what the offer says about who they can reach
_OFFER_TITLE_RE = re.compile(r"i met their (?P<t>.+?) at a conference|their (?P<t2>[^,]+?) reports to", re.I)
_OFFER_PERSON_RE = re.compile(r"\bI know (?P<p>[A-Z][\w'\-]+(?: [A-Z][\w'\-]+)+) there")
# stock replies that carry no path information
NOISE_RE = re.compile(
    r"^(no idea sorry|did we not already lose this one\?|what's the deal size here\?"
    r"|wrong channel\? this feels like a partner ask|i think their procurement is frozen until q1"
    r"|is this the same as the one from last month\?|adding .+? who might know|bumping this)$",
    re.I,
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
    with open(path, mode, newline="", encoding="utf-8") as f:
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

    def resolve_in_scope(self, raw: str) -> tuple[Company | None, str]:
        """Resolve a spelling from a supply-side source. Never creates: a company
        that is neither in the CRM nor requested is out of scope. Records the
        spelling on the company so also_known_as reflects it."""
        c, method = self.resolve(raw)
        if c is not None and raw and raw.strip():
            raw = raw.strip()
            c.names[raw] += 1
            c.how.setdefault(raw, method)
            self._index(raw, c)
        return c, method

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

    def pinned_ids(self) -> dict[Company, str]:
        """company_ids already used by the golden files, so IDs never shift.
        golden_requests.csv (append-only) wins over golden_companies.csv."""
        pinned: dict[Company, str] = {}

        def pin(cid: str, spellings: list[str], domain: str = "") -> None:
            if not cid:
                return
            c = self.by_domain.get(domain.lower()) if domain else None
            for s in spellings:
                if c is not None:
                    break
                if not s:
                    continue
                c, _ = self.resolve(s)
                if c is None:
                    c, _ = self.resolve("", s)
            if c is not None:
                pinned.setdefault(c, cid)

        if REQUESTS_OUT.exists():
            for r in read_csv(REQUESTS_OUT):
                pin(r["company_id"], [r["company_as_written"]])
        if COMPANIES_OUT.exists():
            for r in read_csv(COMPANIES_OUT):
                pin(r["company_id"], [r["company_name"], *r["also_known_as"].split(MULTI)], r["domain"])
        if SUPPLY_OUT.exists():
            for r in read_csv(SUPPLY_OUT):
                pin(r["company_id"], [r["company_name"]])
        return pinned

    def assign_ids(self) -> None:
        pinned = self.pinned_ids()
        used = set(pinned.values())

        def sort_key(c: Company):
            return (0 if c.accounts else 1, c.domain or "~", c.name.lower())

        nxt = 1
        for c in sorted(self.by_domain.values(), key=sort_key):
            if c in pinned:
                c.company_id = pinned[c]
                continue
            while f"C{nxt:03d}" in used:
                nxt += 1
            c.company_id = f"C{nxt:03d}"
            used.add(c.company_id)

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


def delivery_rates(roster: dict, outcomes: list[dict], threads: dict[str, dict]) -> dict[str, float]:
    """intros / asks shrunk toward PRIOR_RATE, for everyone askable: roster,
    anyone asked in intro_outcomes.csv, anyone who volunteered in Slack."""
    asks, intros = Counter(), Counter()
    for o in outcomes:
        asks[o["connector_asked"]] += 1
        if o["intro_sent"] == "Y":
            intros[o["connector_asked"]] += 1
    names = set(roster) | set(asks) | {m["user"] for th in threads.values() for m in th["offers"]}
    return {n: (intros[n] + PRIOR_RATE * PRIOR_WEIGHT) / (asks[n] + PRIOR_WEIGHT) for n in names}


def capacity(roster: dict, name: str) -> int:
    r = roster.get(name)
    return int(r["stated_monthly_capacity"] or 0) if r else OFF_ROSTER_CAPACITY


def fit(connector: dict, industry: str) -> float:
    if not industry:
        return 0.7
    if industry in connector["focus"]:
        return 1.0
    if connector["hard_decline"]:
        return 0.0
    return 0.45


def build_supply(reg: Registry, roster: dict, rates: dict, today: date,
                 request_company: dict[str, Company | None], threads: dict[str, dict]) -> list[dict]:
    """One row per way into an in-scope company. Sources that name a company
    outside the CRM + requested set produce no row."""
    rows: list[dict] = []
    person_to_connectors: dict[str, list[tuple[str, dict]]] = defaultdict(list)

    def emit(connector: str, company: Company, kind: str, contact: str, title: str,
             observed: str, strength: float, evidence: str, offer_age: int | None = None,
             board_seat: str = ""):
        r = roster.get(connector)
        s = company.survivor
        industry = s["industry"] if s else ""
        if r:
            focus = "yes" if industry and industry in r["focus"] else ("unknown" if not industry else "no")
        else:
            focus = "unknown"
        rows.append({
            "connector": connector,
            "connector_type": r["type"] if r else "not on roster",
            "company_id": company.company_id,
            "company_name": company.name,
            "reach_type": kind,
            "board_seat": board_seat,
            "contact_name": contact,
            "contact_title": title,
            "observed_date": observed,
            "offer_age_days": "" if offer_age is None else offer_age,
            "strength": f"{strength:.3f}",
            "in_focus_area": focus,
            "monthly_capacity": capacity(roster, connector),
            "delivery_rate": f"{rates[connector]:.3f}",
            "evidence": evidence,
        })

    # direct: first-degree connections of a roster connector
    for name, r in roster.items():
        for c in read_csv(DATASET / r["connections_file"]):
            person_to_connectors[c["name"]].append((name, c))
            company, _ = reg.resolve_in_scope(c["company"])
            if company is None:
                continue
            s = PATH_BASE["direct"] * (0.55 + 0.45 * seniority(c["title"])) * freshness(c["connected_on"], today)
            emit(name, company, "direct", c["name"], c["title"], c["connected_on"], s,
                 f"{r['connections_file']}: {c['name']}, {c['title']} at {c['company']}, connected {c['connected_on']}")

    # investor: a roster investor's fund holds a position (board seat strengthens it);
    # alumni: a connection's prior employer
    for inv in read_csv(DATASET / "investor_network.csv"):
        person = inv["person"]
        if inv["portfolio_company"] and person in roster:
            company, _ = reg.resolve_in_scope(inv["portfolio_company"])
            if company is not None:
                seat = inv["board_seat"].lower() == "true"
                emit(person, company, "investor", "CEO / exec team",
                     f"{inv['fund']} {'board seat' if seat else 'portfolio company'}", "",
                     BOARD_SEAT_STRENGTH if seat else PATH_BASE["investor"],
                     f"investor_network.csv: {person} ({inv['role']}), portfolio_company={inv['portfolio_company']}, board_seat={inv['board_seat']}",
                     board_seat="yes" if seat else "no")
        if inv["prior_employer"]:
            company, _ = reg.resolve_in_scope(inv["prior_employer"])
            if company is None:
                continue
            tenure = f"{inv['prior_employer_start']}-{inv['prior_employer_end']}"
            for connector, conn in person_to_connectors.get(person, []):
                s = PATH_BASE["alumni"] * freshness(conn["connected_on"], today)
                emit(connector, company, "alumni", person,
                     f"ex-{inv['prior_employer']} ({tenure}), now {conn['title']} at {conn['company']}",
                     conn["connected_on"], s,
                     f"investor_network.csv: {person} prior_employer={inv['prior_employer']} ({tenure}); "
                     f"{roster[connector]['connections_file']}: connection of {connector} since {conn['connected_on']}")

    # offer: someone volunteered a path in the request's Slack thread
    for rid, th in threads.items():
        company = request_company.get(rid)
        if company is None:
            continue
        for m in th["offers"]:
            title_m = _OFFER_TITLE_RE.search(m["text"])
            person_m = _OFFER_PERSON_RE.search(m["text"])
            title = (title_m.group("t") or title_m.group("t2")) if title_m else ("exec team" if "exec team" in m["text"] else "")
            made = parse_date(m["ts"])
            emit(m["user"], company, "offer", person_m.group("p") if person_m else "", title,
                 m["ts"][:10], PATH_BASE["offer"],
                 f"slack_threads.jsonl {rid} {m['ts'][:10]} {m['user']}: \"{m['text']}\"",
                 (today - made).days if made else None)

    rows.sort(key=lambda r: (r["company_id"], r["reach_type"], r["connector"], r["contact_name"], r["evidence"]))
    return rows


def finish_supply(rows: list[dict], roster: dict, rates: dict, outcomes: list[dict],
                  allocation: dict[str, dict], threads: dict[str, dict], today: date) -> list[dict]:
    """Add a placeholder row for every askable person with no in-scope path,
    then stamp connector-level facts on every row.

    allocated_this_cycle = asks dated in the as-of month plus requests the
    allocator assigned to the connector this cycle. idle_capacity =
    monthly_capacity - allocated_this_cycle, never negative because the
    allocator stops at the budget."""
    paths = Counter(r["connector"] for r in rows)
    asks, intros, awaiting, allocated = Counter(), Counter(), Counter(), Counter()
    last_asked: dict[str, str] = {}
    for o in outcomes:
        n = o["connector_asked"]
        asks[n] += 1
        if o["intro_sent"] == "Y":
            intros[n] += 1
        elif o["responded"] == "Y":
            awaiting[n] += 1
        if o["asked_date"]:
            last_asked[n] = max(last_asked.get(n, ""), o["asked_date"])
    cycle = today.strftime("%Y-%m")
    for o in outcomes:
        if o["asked_date"].startswith(cycle):
            allocated[o["connector_asked"]] += 1
    for a in allocation.values():
        if a["allocated_to"]:
            allocated[a["allocated_to"]] += 1

    askable = set(roster) | {o["connector_asked"] for o in outcomes if o["connector_asked"]}
    askable |= {m["user"] for th in threads.values() for m in th["offers"]}
    for name in sorted(askable - set(paths)):
        r = roster.get(name)
        rows.append({
            "connector": name,
            "connector_type": r["type"] if r else "not on roster",
            "company_id": "",
            "company_name": "",
            "reach_type": "none",
            "board_seat": "",
            "contact_name": "",
            "contact_title": "",
            "observed_date": "",
            "offer_age_days": "",
            "strength": "0.000",
            "in_focus_area": "",
            "monthly_capacity": capacity(roster, name),
            "delivery_rate": f"{rates[name]:.3f}",
            "evidence": "no in-scope path",
        })

    for r in rows:
        n = r["connector"]
        r.update({
            "connector_paths_total": paths[n],
            "asks_received": asks[n],
            "intros_sent": intros[n],
            "awaiting_forward": awaiting[n],
            "allocated_this_cycle": allocated[n],
            "idle_capacity": int(r["monthly_capacity"]) - allocated[n],
            "last_asked_date": last_asked.get(n, ""),
        })
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
            offers = [m for m in replies if OFFER_RE.search(m["text"])]
            if not replies:
                all_noise = "no replies"
            else:
                all_noise = "yes" if all(NOISE_RE.match(m["text"].strip()) for m in replies) else "no"
            out[t["request_id"]] = {
                "replies": len(replies),
                "offer": "Y" if offers else "N",
                "offers": offers,
                "all_noise": all_noise,
            }
    return out


def best_route(paths: list[dict], roster: dict, rates: dict, industry: str, exclude_connector: str = "") -> tuple[dict | None, float]:
    best, best_score = None, 0.0
    for p in paths:
        if p["connector"] == exclude_connector:
            continue
        score = path_score(p, roster, rates, industry)
        if score > best_score:
            best, best_score = p, score
    return best, best_score


def path_score(p: dict, roster: dict, rates: dict, industry: str) -> float:
    r = roster.get(p["connector"])
    f = fit(r, industry) if r else 0.7
    return float(p["strength"]) * f * rates.get(p["connector"], PRIOR_RATE)


def allocate(roster: dict, rates: dict, outcomes: list[dict], supply_by_company: dict[str, list[dict]],
             resolved: dict[str, dict], today: date) -> dict[str, dict]:
    """request_id -> allocation row for every live request not yet asked,
    taken from the request file (filed rows plus the ones about to be appended).

    Each connector has a budget for the cycle: stated_monthly_capacity minus
    asks already dated in the cycle (OFF_ROSTER_CAPACITY off the roster).
    Requests are taken in priority order (urgency, value, age) and each goes to
    its best-scoring connector that still has budget. Once every connector
    with a path is spent the request becomes an exception. Requests allocated
    to the same connector share a batch_id: one consolidated ask."""
    cycle = today.strftime("%Y-%m")
    budget: dict[str, int] = defaultdict(lambda: OFF_ROSTER_CAPACITY)
    budget.update({n: capacity(roster, n) for n in roster})
    for o in outcomes:
        if o["asked_date"].startswith(cycle):
            budget[o["connector_asked"]] -= 1

    asked = {o["request_id"] for o in outcomes}
    live = [(rid, rq) for rid, rq in resolved.items() if rq["status"] in OPEN_STATUSES and rid not in asked]
    live.sort(key=lambda t: (URGENCY_RANK.get(t[1]["urgency"], 9), -float(t[1]["value_usd"] or 0),
                             t[1]["request_date"], t[0]))

    out: dict[str, dict] = {}
    for rid, rq in live:
        company = rq["company"]
        s = company.survivor if company else None
        industry = s["industry"] if s else ""
        paths = supply_by_company.get(company.company_id, []) if company else []
        row = {
            "cycle": cycle,
            "request_id": rid,
            "company_id": company.company_id if company else "",
            "company_name": company.name if company else "",
            "target_title": rq["target_title"],
            "value_usd": rq["value_usd"],
            "urgency_declared": rq["urgency"],
            "request_date": rq["request_date"],
            "status_as_filed": rq["status"],
            "allocated_to": "", "batch_id": "", "batch_size": "", "path_type": "", "contact_name": "",
            "route_score": "", "exception_reason": "", "best_path_if_unbudgeted": "",
        }
        out[rid] = row
        if company is None:
            row["exception_reason"] = "company unresolved"
            continue
        scored = sorted(((path_score(p, roster, rates, industry), p) for p in paths),
                        key=lambda t: -t[0])
        scored = [(sc, p) for sc, p in scored if sc > 0]
        if not scored:
            row["exception_reason"] = "no path to this company in the network"
            continue
        best_sc, best = scored[0]
        row["best_path_if_unbudgeted"] = f"{best['connector']} ({best['reach_type']}, {best_sc:.2f})"
        for sc, p in scored:
            n = p["connector"]
            if budget[n] <= 0:
                continue
            budget[n] -= 1
            row.update({
                "allocated_to": n,
                "batch_id": f"{cycle} {n}",
                "path_type": p["reach_type"],
                "contact_name": p["contact_name"],
                "route_score": f"{sc:.3f}",
            })
            break
        else:
            row["exception_reason"] = CAPACITY_EXHAUSTED

    sizes = Counter(r["batch_id"] for r in out.values() if r["batch_id"])
    for r in out.values():
        if r["batch_id"]:
            r["batch_size"] = sizes[r["batch_id"]]
    return out


def path_label(p: dict) -> str:
    if p["reach_type"] == "offer":
        who = p["contact_name"] or p["contact_title"]
        return "offered in Slack" + (f" (knows {who})" if who else "")
    label = f"{p['reach_type']} path via {p['contact_name']}"
    if p["contact_title"] and p["reach_type"] == "direct":
        label += f" ({p['contact_title']})"
    return label


def _looks_like_domain(s: str) -> bool:
    return "." in s and " " not in s


def request_target(rq: dict) -> tuple[str, str, bool]:
    """(company_as_written, domain_hint, parsed_from_raw_ask) for a raw request."""
    written = rq["target_company_raw"].strip()
    if written:
        return written, "", False
    written, domain_hint = company_from_ask(rq["raw_ask"])
    return written, domain_hint, bool(written or domain_hint)


def resolve_requests(reg: Registry, filed: list[dict]) -> dict[str, dict]:
    """request_id -> {company, written, method, target_title, value_usd,
    urgency, request_date, status}: the request as the file holds (or will
    hold) it. Registers every requested company, so after this the registry is
    the in-scope set.

    Scope comes from the request file as it will stand after this run: every
    row already filed in golden_requests.csv (its company_as_written, which is
    pinned to its company_id) plus the target of every raw request not yet
    filed. A filed request keeps its filed spelling and company even if the raw
    export changes; the raw row, when still present, only contributes the email
    domain parsed from raw_ask so the company keeps its domain."""
    raw = {rq["request_id"]: rq for rq in read_csv(DATASET / "intro_requests.csv")}
    out = {}
    for r in filed:
        company = None
        written = r["company_as_written"]
        if r["company_id"] and written:
            domain_hint = request_target(raw[r["request_id"]])[1] if r["request_id"] in raw else ""
            if not domain_hint and _looks_like_domain(written):
                domain_hint = written
            company, _ = reg.resolve_or_create(written, domain_hint)
        out[r["request_id"]] = {
            "company": company, "written": written, "method": r["resolved_by"],
            "target_title": r["target_title"], "value_usd": r["value_usd"], "urgency": r["urgency_declared"],
            "request_date": r["request_date"], "status": r["status_as_filed"],
        }
    for rid, rq in raw.items():
        if rid in out:
            continue
        written, domain_hint, parsed_from_ask = request_target(rq)
        if written or domain_hint:
            company, method = reg.resolve_or_create(written, domain_hint)
            if not written:
                written = domain_hint
            if parsed_from_ask:
                method = f"raw_ask:{method}"
        else:
            company, method = None, "unresolved"
        out[rid] = {
            "company": company, "written": written, "method": method,
            "target_title": rq["target_title_raw"].strip(), "value_usd": money(rq["deal_value_usd"]),
            "urgency": rq["urgency"], "request_date": rq["request_date"], "status": rq["status"],
        }
    return out


def build_requests(reg: Registry, roster: dict, rates: dict, supply_by_company: dict[str, list[dict]],
                   resolved: dict[str, dict], threads: dict[str, dict],
                   allocation: dict[str, dict]) -> list[dict]:
    outcomes = {o["request_id"]: o for o in read_csv(DATASET / "intro_outcomes.csv")}
    rows = []
    for rq in read_csv(DATASET / "intro_requests.csv"):
        rid = rq["request_id"]
        if rid not in resolved:
            continue
        company, written, method = resolved[rid]["company"], resolved[rid]["written"], resolved[rid]["method"]

        review = []
        if company is None:
            review.append("company not identifiable")
        elif not company.accounts:
            review.append("no CRM account")

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
                    route_reason = f"asked; {path_label(bp)}"
                else:
                    route_reason = "asked; no known path from this connector to the company"
                    review.append("asked with no known path")
                alt, alt_sc = best_route(paths, roster, rates, industry, exclude_connector=routed_to)
                if alt and alt_sc > (sc or 0):
                    route_reason += f"; stronger path existed via {alt['connector']} ({alt['reach_type']}, {alt_sc:.2f})"
        elif rid in allocation:
            a = allocation[rid]
            if a["allocated_to"]:
                bp = next(p for p in paths if p["connector"] == a["allocated_to"]
                          and p["reach_type"] == a["path_type"] and p["contact_name"] == a["contact_name"])
                routed_to = a["allocated_to"]
                route_score = a["route_score"]
                route_reason = f"allocated to {a['batch_id']} batch, not yet asked; {path_label(bp)}"
            else:
                route_reason = f"not asked; {a['exception_reason']}"
                if a["best_path_if_unbudgeted"]:
                    route_reason += f"; best path via {a['best_path_if_unbudgeted']}"
        else:
            bp, sc = best_route(paths, roster, rates, industry)
            if bp:
                route_reason = f"not live; best path via {path_label(bp)}"
            elif company:
                route_reason = "not asked; no path to this company in the network"
            else:
                route_reason = "not asked; company unresolved"

        th = threads.get(rid, {"replies": 0, "offer": "N", "all_noise": "no replies"})
        if not money(rq["deal_value_usd"]):
            review.append("no deal value")
        if not rq["target_title_raw"].strip():
            review.append("no target title")

        rows.append({
            "request_id": rid,
            "company_id": company.company_id if company else "",
            "company_as_written": written,
            "target_title": rq["target_title_raw"].strip(),
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
            "thread_all_noise": th["all_noise"],
            "resolved_by": method,
            "needs_review": "; ".join(review) if review else "no",
        })
    rows.sort(key=lambda r: r["request_id"])
    return rows


def append_only_write(rows: list[dict]) -> tuple[int, int, list[str], list[str]]:
    """Append rows whose request_id is new. Existing values are never touched.
    If the schema has gained columns, the file is rewritten with the same rows
    in the new column order; existing cells keep their filed value and only the
    added columns are filled in. A column that disappeared from the schema is
    refused rather than dropped.
    Returns (existing, appended, added columns, drift warnings)."""
    existing = read_csv(REQUESTS_OUT) if REQUESTS_OUT.exists() else []
    has_bom = REQUESTS_OUT.exists() and REQUESTS_OUT.read_bytes()[:3] == b"\xef\xbb\xbf"
    seen = {r["request_id"]: r for r in existing}
    filed_cols = list(existing[0].keys()) if existing else REQUEST_COLUMNS
    missing = [c for c in filed_cols if c not in REQUEST_COLUMNS]
    if missing:
        sys.exit(f"{REQUESTS_OUT} has columns not in the schema ({', '.join(missing)}); refusing to write.")
    added = [c for c in REQUEST_COLUMNS if c not in filed_cols]

    warnings = []
    new = []
    for r in rows:
        old = seen.get(r["request_id"])
        if old is None:
            new.append(r)
            continue
        for c in added:
            old[c] = r.get(c, "")
        diff = [c for c in filed_cols if str(old.get(c, "")) != str(r.get(c, ""))]
        if diff:
            warnings.append(f"{r['request_id']}: recomputed {', '.join(diff)} differ from filed row (kept filed)")

    if added or has_bom:
        write_csv(REQUESTS_OUT, REQUEST_COLUMNS, existing + new)
    else:
        write_csv(REQUESTS_OUT, REQUEST_COLUMNS, new, mode="a")
    return len(existing), len(new), added, warnings


# ---------------------------------------------------------------------------
# companies: rebuilt from golden_requests.csv every run
# ---------------------------------------------------------------------------
def build_companies(reg: Registry, supply: list[dict], requests: list[dict], today: date) -> list[dict]:
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
        if c.company_id not in by_company:
            continue
        reqs = sorted(by_company[c.company_id], key=lambda r: (r["request_date"], r["request_id"]))
        latest = reqs[-1]
        s = c.survivor
        owners = sorted({a["owner"] for a in c.accounts})
        if len(c.accounts) > 1:
            dup = "yes - owners disagree" if len(owners) > 1 else "yes - same owner"
        else:
            dup = "no"
        aka = sorted({n for n in c.names if n != c.name}, key=str.lower)
        value = str(max(int(a["arr_potential_usd"] or 0) for a in c.accounts)) if s else ""
        vals = [int(r["value_usd"]) for r in reqs if r["value_usd"]]
        open_reqs = [r for r in reqs if r["status_as_filed"] in OPEN_STATUSES]
        wanted = sorted({r["target_title"] for r in open_reqs if r["target_title"]}, key=str.lower)
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
            "also_known_as": MULTI.join(aka),
            "domain": c.domain,
            "industry": s["industry"] if s else "",
            "crm_account_ids": MULTI.join(sorted(a["account_id"] for a in c.accounts)),
            "duplicate_accounts": dup,
            "owner": MULTI.join(owners),
            "stage": s["stage"] if s else "",
            "value_usd": value,
            "largest_request_usd": str(max(vals)) if vals else "",
            "total_requests": len(reqs),
            "open_requests": len(open_reqs),
            "distinct_requesters": len({r["requested_by"] for r in reqs}),
            "targets_wanted": MULTI.join(wanted),
            "latest_request_id": latest["request_id"],
            "latest_request_date": latest["request_date"],
            "latest_request_status": latest["status_as_filed"],
            "routed_to": latest["routed_to"],
            "routed_on": latest["routed_on"],
            "route_reason": latest["route_reason"],
            "paths_available": len(paths),
            "durable_paths": sum(1 for p in paths if p["reach_type"] in DURABLE_REACH),
            "best_path_type": best["reach_type"] if best else "",
            "someone_offered": "yes" if any(r["offer_in_thread"] == "Y" for r in reqs) else "no",
            "days_since_movement": (today - max(moves)).days if moves else "",
        })
    return rows


def write_derived(supply: list[dict], allocation: list[dict], companies: list[dict]) -> None:
    """supply_reach.csv, golden_allocation.csv and golden_companies.csv are
    one derived view of the same scope and are only ever written together:
    every file is rendered to a sibling .tmp first, and the .tmp files are
    swapped in only once all three rendered, so a failure never leaves a
    company file that counts a path the supply file denies."""
    targets = [
        (SUPPLY_OUT, SUPPLY_COLUMNS, supply),
        (ALLOCATION_OUT, ALLOCATION_COLUMNS, allocation),
        (COMPANIES_OUT, COMPANY_COLUMNS, companies),
    ]
    tmps = []
    for path, cols, rows in targets:
        tmp = path.with_name(path.name + ".tmp")
        write_csv(tmp, cols, rows)
        tmps.append((tmp, path))
    for tmp, path in tmps:
        os.replace(tmp, path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=date.today().isoformat())
    args = ap.parse_args()
    today = parse_date(args.as_of) or date.today()

    # In-scope set = CRM accounts + every company in the request file (rows
    # already filed, plus raw requests about to be appended). IDs are pinned to
    # the existing golden files before any supply-side source is read.
    filed = read_csv(REQUESTS_OUT) if REQUESTS_OUT.exists() else []
    reg = Registry(read_csv(DATASET / "crm_accounts.csv"))
    resolved = resolve_requests(reg, filed)
    reg.assign_ids()

    roster = load_roster()
    outcomes = read_csv(DATASET / "intro_outcomes.csv")
    threads = load_threads()
    rates = delivery_rates(roster, outcomes, threads)

    supply = build_supply(reg, roster, rates, today, {rid: rq["company"] for rid, rq in resolved.items()}, threads)

    supply_by = defaultdict(list)
    for s in supply:
        supply_by[s["company_id"]].append(s)
    allocation = allocate(roster, rates, outcomes, supply_by, resolved, today)
    requests = build_requests(reg, roster, rates, supply_by, resolved, threads, allocation)
    existing, appended, added, warnings = append_only_write(requests)

    # Derived files: all three computed from the request file as just written,
    # then swapped in together.
    supply = finish_supply(supply, roster, rates, outcomes, allocation, threads, today)
    alloc_rows = sorted(allocation.values(), key=lambda a: (a["allocated_to"] == "", a["batch_id"], a["request_id"]))
    companies = build_companies(reg, supply, read_csv(REQUESTS_OUT), today)
    write_derived(supply, alloc_rows, companies)

    print(f"golden_requests.csv   {existing + appended} rows ({existing} kept, {appended} appended"
          + (f"; columns added: {', '.join(added)}" if added else "") + ")")
    print(f"golden_companies.csv  {len(companies)} rows (rebuilt)")
    print(f"supply_reach.csv      {len(supply)} rows (rebuilt): "
          + ", ".join(f"{k} {n}" for k, n in sorted(Counter(s['reach_type'] for s in supply).items())))
    n_alloc = sum(1 for a in alloc_rows if a["allocated_to"])
    print(f"golden_allocation.csv {len(alloc_rows)} rows (rebuilt): {n_alloc} allocated, "
          + ", ".join(f"{n} {k}" for k, n in sorted(Counter(a['exception_reason'] for a in alloc_rows if a['exception_reason']).items())))
    for w in warnings:
        print("WARN", w)


if __name__ == "__main__":
    main()
