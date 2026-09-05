"""Build the golden datasets from the raw exports in dataset/.

    python3 golden/build_golden.py [--as-of YYYY-MM-DD] [--threads FILE.jsonl]

--threads ingests a Slack export (one {request_id, messages:[{ts,user,text}...]}
per line) alongside dataset/slack_threads.jsonl: a thread whose request_id is
not yet filed becomes a request (requested_by / request_date / raw_ask from the
first message, the company parsed from it by golden/parse.py, status Open, no
deal value or target title, so needs_review is set), and offers in its replies
become supply. The Live Priorities tab previews exactly this before it is run.

golden/ is the state; dataset/ is read-only input and is never written.

Writes four CSVs (UTF-8, no BOM, CRLF):

  golden/golden_requests.csv   one row per intro request. A rebuild MERGES,
                               it never replaces: the file is read first and
                               every request_id already in it is kept, whether
                               or not the source export still has it (live
                               routes and ingested threads exist only here).
                               Only request_ids not yet present are appended.
                               Per column, FACT_COLUMNS (what someone said:
                               requested_by, raw_ask, company_as_written,
                               status_as_filed, ...) are written once and never
                               rewritten, even if the source now says otherwise;
                               RECOMPUTED_COLUMNS (what we concluded: company_id,
                               resolved_by, target_title, needs_review, ...)
                               are recomputed from the facts on every run, so a
                               better resolver or a new CRM account corrects
                               every historical row. Routing, outcome and
                               thread columns are filed once and kept. New
                               columns may be added to the schema.
                               contradicts_log flags a filed status the outcome
                               log disagrees with; blocked_reason says what
                               would unblock a request nobody is routed to.
  golden/golden_companies.csv  one row per in-scope company (grouped by
                               domain), including CRM accounts nobody has
                               requested (total_requests = 0). Always rebuilt
                               from golden_requests.csv plus crm_accounts.csv
                               and supply_reach.csv.
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
                               facts (type, capacity, delivery_rate,
                               idle_capacity) are repeated on every row of
                               that connector on purpose; connector history
                               (asks, intros, last asked) is not carried here.
  golden/golden_allocation.csv the connector history: one row per (cycle,
                               request_id), every ask ever proposed. Each
                               cycle holds one row per request that was live
                               and not yet asked when the cycle was decided:
                               the connector it was allocated to, or an
                               exception (capacity exhausted this cycle / no
                               path / company unresolved / already proposed
                               with no outcome logged). APPEND-ONLY by cycle:
                               a run appends its cycle; a rerun in the same
                               cycle replaces only that cycle's rows; earlier
                               cycles are never touched. decided_at is the
                               build timestamp, so two runs in one cycle are
                               distinguishable. The allocator reads the prior
                               cycles back: asks decided in the trailing
                               FATIGUE_DAYS count against a connector's
                               capacity (asks beyond one month's stated
                               capacity carry over as debt into this cycle),
                               and an ask proposed in a prior cycle with no
                               outcome logged since (the same request, or the
                               same (connector, company)) is flagged rather
                               than proposed again. Everything
                               allocated to one connector in a cycle shares
                               one batch_id (one consolidated ask per
                               connector per cycle).

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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from golden.parse import extract as extract_target  # noqa: E402
from golden.resolver import Resolver, domain_stem, normalize, normalize_strict  # noqa: E402

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
    "needs_review", "contradicts_log", "blocked_reason",
]
# what someone said or filed: written once, never rewritten
FACT_COLUMNS = [
    "request_id", "requested_by", "request_date", "raw_ask", "company_as_written", "value_usd",
    "urgency_declared", "status_as_filed",
]
# what the build concluded from the facts: recomputed on every run
RECOMPUTED_COLUMNS = [
    "company_id", "resolved_by", "target_title", "needs_review", "contradicts_log", "blocked_reason",
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
    "delivery_rate", "idle_capacity", "evidence",
]

ALLOCATION_COLUMNS = [
    "cycle", "request_id", "decided_at", "company_id", "company_name", "target_title", "value_usd",
    "urgency_declared", "request_date", "status_as_filed", "allocated_to", "batch_id", "batch_size",
    "path_type", "contact_name", "route_score", "exception_reason", "best_path_if_unbudgeted",
]

MULTI = " | "  # delimiter for multi-value cells (never a comma)
OPEN_STATUSES = {"Open", "Routed", "Stalled"}
URGENCY_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
OFF_ROSTER_CAPACITY = 2  # monthly asks assumed for anyone askable who is not on the roster
FATIGUE_DAYS = 60  # asks proposed to a connector in this trailing window count against their capacity
CAPACITY_EXHAUSTED = "capacity exhausted this cycle"
STALE_ASK = "already proposed, no outcome logged"  # exception_reason prefix: '<STALE_ASK>: <connector> in <cycle>'
# contradicts_log: status_as_filed vs intro_outcomes.csv
INTRO_CLAIMED_NOT_LOGGED = "intro claimed, none logged"
INTRO_LOGGED_FILED_STALLED = "intro logged, filed as stalled"
CLOSED_NO_PATH_BUT_PATH = "closed as no-path, path exists"
# blocked_reason: what would unblock a request nobody is routed to
BLOCK_NO_COMPANY = "no company named in the ask"
BLOCK_NO_CRM = "company has no CRM record"
BLOCK_FUND_OR_OPCO = "fund or operating company \u2014 ask the requester"
BLOCK_NO_ROSTER_PATH = "no path on the roster"
BLOCK_CLOSED_LOST = "account is Closed Lost"
BLOCK_NEVER_ROUTED = "path exists, never routed"  # filed with no routed_to before the path was known
# a bare name shared by a fund and a customer (Thornbury, Silverbrook, Cobalt Lane,
# Meridian Peak): golden/resolver.py refuses it; the request gets no company_id
FUND_COLLISION = "fund-collision"
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
    if DATASET in path.resolve().parents:
        sys.exit(f"refusing to write {path}: dataset/ is read-only input")
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


def read_allocation(path: Path = ALLOCATION_OUT) -> list[dict]:
    """The whole connector history, every cycle, in file order."""
    return read_csv(path) if path.exists() else []


def latest_cycle(history: list[dict]) -> list[dict]:
    """The rows of the most recent cycle in the history: the current allocation."""
    if not history:
        return []
    cycle = max(a["cycle"] for a in history)
    return [a for a in history if a["cycle"] == cycle]


def decided_date(a: dict) -> date | None:
    """When a history row was decided: decided_at, or the first of its cycle
    for rows filed before the column existed."""
    return parse_date(a.get("decided_at") or "") or parse_date(f"{a['cycle']}-01")


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
    def __init__(self, accounts: list[dict], funds: list[str] = ()):
        self._canon = Resolver(accounts, funds)  # the fund-collision guard lives there
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
        """Return (company, method). Never creates. A bare name the canonical
        resolver refuses as fund-or-customer is refused here too."""
        if self._canon.resolve(raw, domain_hint).method == "fund-or-customer":
            return None, FUND_COLLISION
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

    def target_from_message(self, text: str) -> tuple[str, str]:
        """(company_as_written, domain_hint) named by a Slack message, via golden/parse.py."""
        t = extract_target(text, self._canon).target
        if t is None:
            return "", ""
        return ("", t.text) if t.is_domain else (t.text, "")

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

    def resolve_or_create(self, raw: str, domain_hint: str = "") -> tuple[Company | None, str]:
        c, method = self.resolve(raw, domain_hint)
        if method == FUND_COLLISION:
            return None, method
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


class HistorySignals(NamedTuple):
    """What the prior cycles of golden_allocation.csv say about each connector.

    fatigue: connector -> asks allocated to them in a cycle before this one and
    decided in the trailing FATIGUE_DAYS (rows of the current cycle are about
    to be replaced and are not counted).
    stale: (connector, company_id) -> the most recent prior-cycle row that
    allocated that company to that connector whose request has no row in
    intro_outcomes.csv: an ask proposed and never logged as made.
    proposed: request_id -> the most recent prior-cycle row that allocated the
    request, again with no outcome logged since."""
    fatigue: Counter
    stale: dict[tuple[str, str], dict]
    proposed: dict[str, dict]


def history_signals(history: list[dict], outcomes: list[dict], today: date) -> HistorySignals:
    cycle = today.strftime("%Y-%m")
    asked = {o["request_id"] for o in outcomes}
    fatigue: Counter = Counter()
    stale: dict[tuple[str, str], dict] = {}
    proposed: dict[str, dict] = {}
    for a in sorted((a for a in history if a["cycle"] < cycle and a["allocated_to"]),
                    key=lambda a: (a["cycle"], a.get("decided_at") or "")):
        d = decided_date(a)
        if d and 0 <= (today - d).days < FATIGUE_DAYS:
            fatigue[a["allocated_to"]] += 1
        if a["request_id"] not in asked:
            proposed[a["request_id"]] = a
            if a["company_id"]:
                stale[(a["allocated_to"], a["company_id"])] = a
    return HistorySignals(fatigue, stale, proposed)


def cycle_budget(roster: dict, fatigue: Counter, name: str) -> int:
    """Asks a connector can take this cycle: stated_monthly_capacity, less the
    asks in the trailing FATIGUE_DAYS beyond one month's capacity. A connector
    who was over-allocated last cycle starts this one with less headroom."""
    cap = capacity(roster, name)
    return max(0, cap - max(0, fatigue[name] - cap))


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
                  allocation: dict[str, dict], threads: dict[str, dict], fatigue: Counter) -> list[dict]:
    """Add a placeholder row for every askable person with no in-scope path,
    then stamp idle_capacity on every row.

    idle_capacity = the connector's budget for the cycle (cycle_budget: stated
    capacity less fatigue debt carried over from prior cycles) minus requests
    the allocator assigned to them this cycle; never negative because the
    allocator stops at the budget."""
    paths = Counter(r["connector"] for r in rows)
    allocated = Counter()
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
        r["idle_capacity"] = cycle_budget(roster, fatigue, r["connector"]) - allocated[r["connector"]]
    return rows


# ---------------------------------------------------------------------------
# demand side
# ---------------------------------------------------------------------------
def load_threads(extra: Path | None = None) -> dict[str, dict]:
    """request_id -> thread facts from dataset/slack_threads.jsonl, plus the
    threads in `extra` (--threads), which are marked ingested=True."""
    out = {}
    for path, ingested in ((DATASET / "slack_threads.jsonl", False), (extra, True)):
        if path is None:
            continue
        with open(path, encoding="utf-8") as f:
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
                    "first": t["messages"][0],
                    "ingested": ingested,
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
             resolved: dict[str, dict], today: date, decided_at: str, signals: HistorySignals) -> dict[str, dict]:
    """request_id -> allocation row for every live request not yet asked,
    taken from the request file (filed rows plus the ones about to be appended).

    Each connector has a budget for the cycle (cycle_budget): stated monthly
    capacity (OFF_ROSTER_CAPACITY off the roster) less the asks the history
    says were proposed to them in the trailing FATIGUE_DAYS beyond one month's
    capacity. Requests are taken in priority order (urgency, value, age) and
    each goes to its best-scoring connector that still has budget. An ask the
    history already holds with no outcome logged since is not proposed again:
    a request allocated in a prior cycle, or a connector already proposed this
    company in a prior cycle, is flagged (STALE_ASK, naming that connector and
    cycle) instead of being allocated or falling through to the next
    connector. Once every connector with a path is spent the request becomes
    an exception. Requests allocated to the same connector share a batch_id:
    one consolidated ask."""
    cycle = today.strftime("%Y-%m")
    fatigue, stale, proposed = signals
    budget: dict[str, int] = defaultdict(int)
    for n in set(roster) | {p["connector"] for paths in supply_by_company.values() for p in paths}:
        budget[n] = cycle_budget(roster, fatigue, n)

    asked = {o["request_id"] for o in outcomes}
    live = [(rid, rq) for rid, rq in resolved.items()
            if rq["facts"]["status_as_filed"] in OPEN_STATUSES and rid not in asked]
    live.sort(key=lambda t: (URGENCY_RANK.get(t[1]["facts"]["urgency_declared"], 9),
                             -float(t[1]["facts"]["value_usd"] or 0), t[1]["facts"]["request_date"], t[0]))

    out: dict[str, dict] = {}
    for rid, rq in live:
        company, facts = rq["company"], rq["facts"]
        s = company.survivor if company else None
        industry = s["industry"] if s else ""
        paths = supply_by_company.get(company.company_id, []) if company else []
        row = {
            "cycle": cycle,
            "request_id": rid,
            "decided_at": decided_at,
            "company_id": company.company_id if company else "",
            "company_name": company.name if company else "",
            "target_title": rq["target_title"],
            "value_usd": facts["value_usd"],
            "urgency_declared": facts["urgency_declared"],
            "request_date": facts["request_date"],
            "status_as_filed": facts["status_as_filed"],
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
            prior = proposed.get(rid) or stale.get((n, company.company_id))
            if prior is not None:
                row["exception_reason"] = f"{STALE_ASK}: {prior['allocated_to']} in {prior['cycle']}"
                break
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


def resolve_target(reg: Registry, written: str, domain_hint: str,
                   parsed_from_ask: bool) -> tuple[Company | None, str]:
    """-> (company, resolved_by). Registers the company."""
    if not (written or domain_hint):
        return None, "unresolved"
    company, method = reg.resolve_or_create(written, domain_hint)
    if parsed_from_ask and method != FUND_COLLISION:
        method = f"raw_ask:{method}"
    return company, method


def source_facts(rq: dict) -> dict:
    """FACT_COLUMNS as a raw intro_requests.csv row states them."""
    written, domain_hint, _ = request_target(rq)
    return {
        "request_id": rq["request_id"], "requested_by": rq["requested_by"], "request_date": rq["request_date"],
        "raw_ask": rq["raw_ask"], "company_as_written": written or domain_hint,
        "value_usd": money(rq["deal_value_usd"]), "urgency_declared": rq["urgency"], "status_as_filed": rq["status"],
    }


def thread_facts(rid: str, first: dict) -> dict:
    """FACT_COLUMNS as the first message of an ingested Slack thread states them."""
    return {
        "request_id": rid, "requested_by": first["user"], "request_date": first["ts"][:10],
        "raw_ask": first["text"], "company_as_written": "",
        "value_usd": "", "urgency_declared": "", "status_as_filed": "Open",
    }


def resolve_requests(reg: Registry, filed: list[dict], ingest: dict[str, dict] | None = None) -> dict[str, dict]:
    """request_id -> {company, method, target_title, facts, source}: every
    request the file will hold after this run. Registers every requested
    company, so after this the registry is the in-scope set.

    ingest (--threads) adds Slack threads whose request_id is neither filed
    nor in the raw export: facts come from the first message, the company
    from golden/parse.py on its text.

    facts (FACT_COLUMNS) come from the filed row when there is one (a filed
    request keeps its filed spelling even if the raw export changes or no
    longer has it) and from the raw export otherwise; source is what the raw
    export states now, or None when it no longer has the request. The company
    is re-resolved from the facts on every run, filed or not; the raw row, when
    still present, contributes the email domain parsed from raw_ask and the
    current target_title."""
    raw = {rq["request_id"]: rq for rq in read_csv(DATASET / "intro_requests.csv")}
    out = {}
    for r in filed:
        rid = r["request_id"]
        rq = raw.get(rid)
        written = r["company_as_written"]
        domain_hint = request_target(rq)[1] if rq else ""
        if not domain_hint and _looks_like_domain(written):
            domain_hint = written
        company, method = resolve_target(reg, "" if written == domain_hint else written, domain_hint,
                                         r["resolved_by"].startswith("raw_ask:"))
        out[rid] = {
            "company": company, "method": method,
            "target_title": rq["target_title_raw"].strip() if rq else r["target_title"],
            "facts": {c: r[c] for c in FACT_COLUMNS}, "source": source_facts(rq) if rq else None,
        }
    for rid, rq in raw.items():
        if rid in out:
            continue
        company, method = resolve_target(reg, *request_target(rq))
        facts = source_facts(rq)
        out[rid] = {"company": company, "method": method, "target_title": rq["target_title_raw"].strip(),
                    "facts": facts, "source": facts}
    for rid, th in (ingest or {}).items():
        if rid in out:
            continue
        written, domain_hint = reg.target_from_message(th["first"]["text"])
        company, method = resolve_target(reg, written, domain_hint, bool(written or domain_hint))
        facts = thread_facts(rid, th["first"])
        facts["company_as_written"] = written or domain_hint
        out[rid] = {"company": company, "method": method, "target_title": "", "facts": facts, "source": facts}
    return out


def contradicts_log(status: str, outcome: dict | None) -> str:
    """Where status_as_filed and intro_outcomes.csv disagree about the intro."""
    intro_logged = outcome is not None and outcome["intro_sent"] == "Y"
    if status == "Intro sent" and not intro_logged:
        return INTRO_CLAIMED_NOT_LOGGED
    if status == "Stalled" and intro_logged:
        return INTRO_LOGGED_FILED_STALLED
    if status == "Closed - no path" and intro_logged:
        return CLOSED_NO_PATH_BUT_PATH
    return ""


def blocked_reason(company: Company | None, paths: list[dict], roster: dict, alloc: dict | None) -> str:
    """For a request nobody is routed to: the first thing an operator would
    have to fix, in the order they would fix it. Identity first (no company,
    no CRM record), then whether the account is worth a connector (Closed
    Lost), then supply. Fund collisions are decided before this is called."""
    if company is None:
        return BLOCK_NO_COMPANY
    if not company.accounts:
        return BLOCK_NO_CRM
    if company.survivor["stage"] == "Closed Lost":
        return BLOCK_CLOSED_LOST
    if alloc and alloc["exception_reason"] == CAPACITY_EXHAUSTED:
        return CAPACITY_EXHAUSTED
    if alloc and alloc["exception_reason"].startswith(STALE_ASK):
        return STALE_ASK
    if not any(p["connector"] in roster for p in paths):
        return BLOCK_NO_ROSTER_PATH
    return BLOCK_NEVER_ROUTED


def build_requests(reg: Registry, roster: dict, rates: dict, supply_by_company: dict[str, list[dict]],
                   resolved: dict[str, dict], threads: dict[str, dict],
                   allocation: dict[str, dict], filed: list[dict]) -> list[dict]:
    outcomes = {o["request_id"]: o for o in read_csv(DATASET / "intro_outcomes.csv")}
    filed_by = {r["request_id"]: r for r in filed}
    rows = []
    for rid, rq in resolved.items():
        company, method, facts = rq["company"], rq["method"], rq["facts"]

        review = []
        if method == FUND_COLLISION:
            review.append("bare name is a fund and a customer")
        elif company is None:
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

        # a filed row keeps its filed routing, so judge its block against that
        effective_routed_to = filed_by[rid]["routed_to"] if rid in filed_by else routed_to
        if method == FUND_COLLISION:
            blocked = BLOCK_FUND_OR_OPCO
        elif effective_routed_to:
            blocked = ""
        else:
            blocked = blocked_reason(company, paths, roster, allocation.get(rid))

        th = threads.get(rid, {"replies": 0, "offer": "N", "all_noise": "no replies"})
        if not facts["value_usd"]:
            review.append("no deal value")
        if not rq["target_title"]:
            review.append("no target title")

        rows.append({
            **facts,
            "company_id": company.company_id if company else "",
            "target_title": rq["target_title"],
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
            "contradicts_log": contradicts_log(facts["status_as_filed"], o),
            "blocked_reason": blocked,
        })
    rows.sort(key=lambda r: r["request_id"])
    return rows


def merge_write(rows: list[dict], source: dict[str, dict | None]) -> tuple[int, int, int, list[str], list[str]]:
    """Merge the recomputed rows into golden_requests.csv. Every filed row is
    kept. Rows whose request_id is new are appended. On a filed row,
    RECOMPUTED_COLUMNS take the recomputed value; every other column keeps its
    filed value. source is FACT_COLUMNS as the raw export states them now (None
    when it no longer has the request): a fact it states differently from the
    filed row is reported and kept. If the schema has gained columns, the file
    is rewritten with the same rows in the new column order and only the added
    columns filled in. A column that disappeared from the schema is refused
    rather than dropped.
    Returns (kept, appended, rows whose conclusions changed, added columns,
    warnings)."""
    existing = read_csv(REQUESTS_OUT) if REQUESTS_OUT.exists() else []
    has_bom = REQUESTS_OUT.exists() and REQUESTS_OUT.read_bytes()[:3] == b"\xef\xbb\xbf"
    filed_cols = list(existing[0].keys()) if existing else REQUEST_COLUMNS
    missing = [c for c in filed_cols if c not in REQUEST_COLUMNS]
    if missing:
        sys.exit(f"{REQUESTS_OUT} has columns not in the schema ({', '.join(missing)}); refusing to write.")
    added = [c for c in REQUEST_COLUMNS if c not in filed_cols]
    computed = {r["request_id"]: r for r in rows}
    gone = [r["request_id"] for r in existing if r["request_id"] not in computed]
    if gone:
        sys.exit(f"{len(gone)} filed requests were not recomputed ({', '.join(gone[:5])}); refusing to write.")

    warnings = []
    changed = 0
    for old in existing:
        r = computed[old["request_id"]]
        for c in added:
            old[c] = r.get(c, "")
        src = source[old["request_id"]]
        drift = [c for c in FACT_COLUMNS if src and c in filed_cols and str(old[c]) != str(src[c])]
        if drift:
            warnings.append(f"{old['request_id']}: source now differs on {', '.join(drift)} (kept filed)")
        diff = [c for c in RECOMPUTED_COLUMNS if c in filed_cols and str(old[c]) != str(r[c])]
        if diff:
            warnings.append(f"{old['request_id']}: recomputed "
                            + "; ".join(f"{c} {old[c]!r} -> {r[c]!r}" for c in diff))
            old.update({c: r[c] for c in diff})
            changed += 1
    filed_ids = {e["request_id"] for e in existing}
    new = [r for r in rows if r["request_id"] not in filed_ids]

    if added or has_bom or changed:
        write_csv(REQUESTS_OUT, REQUEST_COLUMNS, existing + new)
    else:
        write_csv(REQUESTS_OUT, REQUEST_COLUMNS, new, mode="a")
    return len(existing), len(new), changed, added, warnings


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
        reqs = sorted(by_company.get(c.company_id, []), key=lambda r: (r["request_date"], r["request_id"]))
        latest = reqs[-1] if reqs else {k: "" for k in REQUEST_COLUMNS}
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


def merge_allocation(history: list[dict], current: list[dict], cycle: str) -> tuple[list[dict], int, int, int]:
    """The connector history as it will be written: every row of every other
    cycle exactly as filed, in file order, with this cycle's rows in place of
    the ones it had (at the end when it is new). A column that disappeared from
    the schema is refused rather than dropped; a column the schema gained is
    left empty on the filed rows.
    Returns (rows, prior cycles kept, prior rows kept, rows of this cycle replaced)."""
    if history:
        missing = [c for c in history[0] if c not in ALLOCATION_COLUMNS]
        if missing:
            sys.exit(f"{ALLOCATION_OUT} has columns not in the schema ({', '.join(missing)}); refusing to write.")
    before = [a for a in history if a["cycle"] < cycle]
    after = [a for a in history if a["cycle"] > cycle]
    kept = len(before) + len(after)
    return before + current + after, len({a["cycle"] for a in before + after}), kept, len(history) - kept


def write_derived(supply: list[dict], allocation: list[dict], companies: list[dict]) -> None:
    """supply_reach.csv, golden_allocation.csv and golden_companies.csv are
    one derived view of the same scope and are only ever written together:
    every file is rendered to a sibling .tmp first, and the .tmp files are
    swapped in only once all three rendered, so a failure never leaves a
    company file that counts a path the supply file denies. The allocation
    rows are the whole history (merge_allocation), not just this cycle."""
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
    ap.add_argument("--threads", type=Path, help="a Slack export (.jsonl) to ingest alongside dataset/slack_threads.jsonl")
    args = ap.parse_args()
    today = parse_date(args.as_of) or date.today()
    cycle = today.strftime("%Y-%m")
    # the build clock: the as-of date, at the wall-clock time the run started
    decided_at = datetime.combine(today, datetime.now(timezone.utc).time()).strftime("%Y-%m-%dT%H:%M:%SZ")

    # In-scope set = CRM accounts + every company in the request file (rows
    # already filed, plus raw requests about to be appended). IDs are pinned to
    # the existing golden files before any supply-side source is read.
    filed = read_csv(REQUESTS_OUT) if REQUESTS_OUT.exists() else []
    reg = Registry(read_csv(DATASET / "crm_accounts.csv"),
                   [inv["fund"] for inv in read_csv(DATASET / "investor_network.csv")])
    threads = load_threads(args.threads)
    resolved = resolve_requests(reg, filed, {rid: th for rid, th in threads.items() if th["ingested"]})
    reg.assign_ids()

    roster = load_roster()
    outcomes = read_csv(DATASET / "intro_outcomes.csv")
    rates = delivery_rates(roster, outcomes, threads)
    history = read_allocation()
    signals = history_signals(history, outcomes, today)

    supply = build_supply(reg, roster, rates, today, {rid: rq["company"] for rid, rq in resolved.items()}, threads)

    supply_by = defaultdict(list)
    for s in supply:
        supply_by[s["company_id"]].append(s)
    allocation = allocate(roster, rates, outcomes, supply_by, resolved, today, decided_at, signals)
    requests = build_requests(reg, roster, rates, supply_by, resolved, threads, allocation, filed)
    kept, appended, changed, added, warnings = merge_write(
        requests, {rid: rq["source"] for rid, rq in resolved.items()})
    carried = sum(1 for rq in resolved.values() if rq["source"] is None)

    # Derived files: all three computed from the request file as just written,
    # then swapped in together.
    supply = finish_supply(supply, roster, rates, outcomes, allocation, threads, signals.fatigue)
    alloc_rows = sorted(allocation.values(), key=lambda a: (a["allocated_to"] == "", a["batch_id"], a["request_id"]))
    all_alloc, prior_cycles, prior_rows, replaced = merge_allocation(history, alloc_rows, cycle)
    companies = build_companies(reg, supply, read_csv(REQUESTS_OUT), today)
    write_derived(supply, all_alloc, companies)

    print(f"golden_requests.csv   {kept + appended} rows ({kept} kept, of which {carried} not in "
          f"dataset/intro_requests.csv and carried forward; {appended} appended; "
          f"{changed} with recomputed {'/'.join(RECOMPUTED_COLUMNS[:3])}/... changed"
          + (f"; columns added: {', '.join(added)}" if added else "") + ")")
    print(f"golden_companies.csv  {len(companies)} rows (rebuilt)")
    print(f"supply_reach.csv      {len(supply)} rows (rebuilt): "
          + ", ".join(f"{k} {n}" for k, n in sorted(Counter(s['reach_type'] for s in supply).items())))
    n_alloc = sum(1 for a in alloc_rows if a["allocated_to"])
    reasons = Counter(a["exception_reason"].split(":")[0] for a in alloc_rows if a["exception_reason"])
    print(f"golden_allocation.csv {len(all_alloc)} rows in {prior_cycles + 1} cycles ({prior_rows} rows from "
          f"{prior_cycles} prior cycles carried forward; cycle {cycle}: {len(alloc_rows)} rows written, "
          f"{replaced} replaced): {n_alloc} allocated, "
          + ", ".join(f"{n} {k}" for k, n in sorted(reasons.items())))
    fatigue = signals.fatigue
    fatigued = {n: k for n, k in fatigue.items() if cycle_budget(roster, fatigue, n) < capacity(roster, n)}
    if fatigued:
        print(f"  fatigue: {len(fatigued)} connectors start with less headroom: "
              + ", ".join(f"{n} ({k} asks in {FATIGUE_DAYS}d)" for n, k in sorted(fatigued.items())))
    for w in warnings:
        print("WARN", w)


if __name__ == "__main__":
    main()
