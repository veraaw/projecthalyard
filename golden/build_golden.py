"""Build the golden datasets from the raw exports in dataset/.

    python3 golden/build_golden.py [--as-of YYYY-MM-DD] [--threads FILE.jsonl]

--threads ingests a Slack export (one {request_id, messages:[{ts,user,text}...]}
per line) alongside dataset/slack_threads.jsonl: a thread whose request_id is
not yet filed becomes a request (requested_by / request_date / raw_ask from the
first message, the company parsed from it by golden/parse.py, status Open, no
deal value or target title, so needs_review is set), and offers in its replies
become supply. The Live Priorities tab previews exactly this before it is run.

golden/completions.csv is the third fact source, next to the raw exports and
the Slack threads: one row per thing someone did from the Live Priorities tab
(action = ask_sent / nudged / chased / checked_in). The tab's Submit button
posts those rows to the Supabase `completions` table; the build pulls the
table into the CSV, and the CSV is what the build reads:

    python3 golden/build_golden.py                        # the CSV as committed; no network
    python3 golden/build_golden.py --completions supabase # pull the table into the CSV first
    python3 golden/build_golden.py --apply FILE           # merge a CSV of rows (a Supabase
                                                          # export, say) into the CSV first

The database is an input, not a dependency: with Supabase down, --apply a
file, or edit the CSV, and build. The CSV is append-only and deduplicated on
completion_id (<request_id>:<action>:<date>), so the same completion pulled,
applied or committed twice is a no-op. An `ask_sent` row is an ask that happened
with nothing logged back yet: it counts as an outcome everywhere
intro_outcomes.csv does (the request leaves the live queue, the connector's
slot is spent, asked_date is filed on the request). On a request whose intro
already fizzled, an `ask_sent` row dated after that intro is the retry going
out: it files reasked_date on the outcome, takes the request out of the queue
again and puts it back on the connector's plate. A `nudged` row (the
connector agreed and never delivered) or a `chased` row (the connector never
replied) files nudged_on on the request: the latest follow-up of either kind.
A `checked_in` row (someone touched the company: CRM account or connector)
files checked_in_on on the company. A row with an unknown action, an
unparseable completed_at or a missing key fails the build.

golden/ is the state; dataset/ is read-only input and is never written.

Writes five CSVs (UTF-8, no BOM, CRLF):

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
                               every historical row. ROUTING_COLUMNS (routed_to,
                               route_score, route_reason, ...) are provisional
                               until an ask is logged: they follow this run's
                               allocation and paths while asked_date is empty,
                               then are filed with the ask and kept. Outcome and
                               thread columns are filed once and kept, except
                               that OUTCOME_COLUMNS still empty on a filed row
                               are filled in when an ask is first logged for
                               it, and nudged_on advances to the latest nudge
                               or chase. New columns may be added to the schema.
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
                               in a Slack thread). investor_network is the
                               investor path of a person who is in
                               investor_network.csv but not on the roster: in
                               our circle, so askable (OFF_ROSTER_CAPACITY,
                               connector_type "investor network"), but scored
                               with a NETWORK_HAIRCUT on route_score and
                               ranked behind every roster path: asked only
                               when the roster has no path or no capacity.
                               Every askable person (roster, off-roster people
                               asked in intro_outcomes.csv, Slack volunteers,
                               investor_network.csv people with a portfolio
                               company in scope)
                               has at least one row: reach_type = "none" if
                               they have no in-scope path. Connector-level
                               facts (type, capacity, delivery_rate,
                               idle_capacity) are repeated on every row of
                               that connector on purpose; connector history
                               (asks, intros, last asked) is not carried here.
  golden/golden_allocation.csv the connector history: one row per (cycle,
                               request_id), every ask ever proposed. Each
                               cycle holds one row per request that was live
                               and not yet asked when the cycle was decided,
                               plus every asked request whose intro fizzled
                               (no meeting, older than INTRO_LIVE_DAYS) and
                               has not been re-asked since, back as a retry:
                               the connector it was allocated to, or an
                               exception (capacity exhausted this cycle / no
                               path / company unresolved / already proposed
                               with no outcome logged). APPEND-ONLY by cycle:
                               a run appends its cycle; a rerun in the same
                               cycle replaces only that cycle's rows; earlier
                               cycles are never touched. decided_at is the
                               build timestamp, one per cycle per run, so two
                               runs in one cycle are distinguishable - except
                               that a rerun reproducing the cycle exactly keeps
                               the filed stamp, so a rebuild that changed
                               nothing is a byte-identical no-op. The allocator reads the prior
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
  golden/network_orbit.csv     one row per (person, company) pair in
                               investor_network.csv whose portfolio_company or
                               prior_employer resolves to an in-scope company:
                               who sits around the company, on the roster or
                               not. reachable_via = "connector" when the person
                               is on the roster, else the surnames of the
                               connectors whose connections_*.csv lists them,
                               else "investor_network" when the row is their own
                               portfolio company (the supply_reach.csv path of
                               that name), else empty (no warm route). A view
                               for the Company Trace: the file itself is never
                               scored or allocated; the paths it points at are.

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
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from golden.clock import as_of  # noqa: E402
from golden.parse import extract as extract_target  # noqa: E402
from golden.resolver import Resolver, domain_stem, names_regex, normalize, normalize_strict  # noqa: E402

DATASET = ROOT / "dataset"
OUT = ROOT / "golden"

REQUESTS_OUT = OUT / "golden_requests.csv"
COMPANIES_OUT = OUT / "golden_companies.csv"
SUPPLY_OUT = OUT / "supply_reach.csv"
ALLOCATION_OUT = OUT / "golden_allocation.csv"
COMPLETIONS_OUT = OUT / "completions.csv"
NETWORK_OUT = OUT / "network_orbit.csv"

REQUEST_COLUMNS = [
    "request_id", "company_id", "company_as_written", "target_title", "requested_by", "request_date",
    "raw_ask", "value_usd", "urgency_declared", "status_as_filed", "routed_to", "routed_on",
    "route_score", "route_reason", "asked_date", "responded", "intro_sent", "meeting_booked",
    "opportunity_usd", "offer_in_thread", "thread_replies", "thread_all_noise", "resolved_by",
    "needs_review", "contradicts_log", "blocked_reason", "nudged_on",
]
# where the request stands with connectors: this run's allocation or best path until an
# ask is logged, then what the ask log says, kept
ROUTING_COLUMNS = ["routed_to", "routed_on", "route_score", "route_reason"]
# what the ask log says about a request: filed the first time an ask is logged, then kept
OUTCOME_COLUMNS = [
    *ROUTING_COLUMNS, "asked_date", "responded", "intro_sent", "meeting_booked", "opportunity_usd",
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
    "checked_in_on",
]
SUPPLY_COLUMNS = [
    "connector", "connector_type", "company_id", "company_name", "reach_type", "board_seat", "contact_name",
    "contact_title", "observed_date", "offer_age_days", "strength", "in_focus_area", "monthly_capacity",
    "delivery_rate", "idle_capacity", "evidence",
]

NETWORK_COLUMNS = [
    "company_id", "company_name", "person", "role", "fund", "board_seat", "source", "reachable_via",
]
NETWORK_SOURCES = ("portfolio_company", "prior_employer")  # the investor_network.csv columns that name a company
REACHABLE_AS_CONNECTOR = "connector"  # reachable_via for a person who is on the roster themselves

COMPLETION_COLUMNS = [
    "completion_id", "completed_at", "completed_by", "action", "request_id", "company_id", "connector", "note",
]
ASKED, NUDGED, CHASED, CHECKED_IN = "ask_sent", "nudged", "chased", "checked_in"  # the table's action check
COMPLETION_KINDS = (ASKED, NUDGED, CHASED, CHECKED_IN)
REQUEST_KINDS = (ASKED, NUDGED, CHASED)  # keyed on request_id + connector; CHECKED_IN is keyed on company_id
FOLLOW_UPS = (NUDGED, CHASED)  # both advance nudged_on
ALLOCATION_COLUMNS = [
    "cycle", "request_id", "decided_at", "company_id", "company_name", "target_title", "value_usd",
    "urgency_declared", "request_date", "status_as_filed", "allocated_to", "batch_id", "batch_size",
    "path_type", "contact_name", "route_score", "exception_reason", "best_path_if_unbudgeted",
]

MULTI = " | "  # delimiter for multi-value cells (never a comma)
OPEN_STATUSES = {"Open", "Routed", "Stalled"}
# routing stages a request moves through, in order; "closed" (Closed - no path) sits outside the strip
STAGES = ["needs data", "to be routed", "routed", "asked", "introduced", "meeting booked"]
URGENCY_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
OFF_ROSTER_CAPACITY = 2  # monthly asks assumed for anyone askable who is not on the roster
FATIGUE_DAYS = 60  # asks proposed to a connector in this trailing window count against their capacity
CAPACITY_EXHAUSTED = "capacity exhausted this cycle"
STALE_ASK = "already proposed, no outcome logged"  # exception_reason prefix: '<STALE_ASK>: <connector> in <cycle>'
INTRO_LIVE_DAYS = 60  # an intro this recent is still in play, as is a meeting until it has gone this long without an opportunity
                      # while newer requests wait on the company: nobody is asked afresh
# exception_reason prefix: '<ALREADY_INTRODUCED>: <connector> on <intro_date> (<request_id>[, meeting booked])'
ALREADY_INTRODUCED = "already introduced"
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
BLOCK_NEVER_ROUTED = "path exists, never routed"  # a path exists but the request is not live, so nobody is allocated
# a bare name shared by a fund and a customer (Thornbury, Silverbrook, Cobalt Lane,
# Meridian Peak): golden/resolver.py refuses it; the request gets no company_id
FUND_COLLISION = "fund-collision"
# an investor_network.csv person who is not on the roster, reaching their own portfolio
# company: our circle, not our roster, so the path exists but its route_score takes a haircut
INVESTOR_NETWORK = "investor_network"
NETWORK_TYPE = "investor network"  # connector_type of such a person (roster people carry their roster type)
NETWORK_HAIRCUT = 0.90  # route_score multiplier for investor_network paths
# reach types that outlast the request they were observed on; offers are request-scoped
DURABLE_REACH = {"direct", "investor", "alumni", INVESTOR_NETWORK}

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


def load_completions(path: Path = COMPLETIONS_OUT) -> list[dict]:
    """golden/completions.csv, deduplicated on completion_id (the first row with
    an id wins, so a file that repeats a row applies it once). Rows come back
    in file order with every COMPLETION_COLUMNS key present. A malformed row
    ends the build: an unknown action, a completed_at that does not start with a date,
    `ask_sent`/`nudged`/`chased` without a request_id and connector, `checked_in`
    without a company_id."""
    if not path.exists():
        return []
    rows, seen, bad = [], set(), []
    for i, raw in enumerate(read_csv(path), 2):
        r = completion_row(raw)
        if problem := completion_problem(r):
            bad.append(f"line {i}: {problem}")
        if r["completion_id"] in seen:
            continue
        seen.add(r["completion_id"])
        rows.append(r)
    if bad:
        sys.exit(f"{path}: {len(bad)} bad row(s); nothing written.\n  " + "\n  ".join(bad))
    return rows


def completion_row(raw: dict) -> dict:
    """A completion as the CSV holds it: every schema column, stripped strings,
    JSON null (Supabase's empty optional) as ""."""
    return {c: ("" if raw.get(c) is None else str(raw.get(c))).strip() for c in COMPLETION_COLUMNS}


def completion_problem(r: dict) -> str | None:
    """Why a completion row cannot be applied, or None when it can."""
    if not r["completion_id"]:
        return "no completion_id"
    who = f"({r['completion_id']})"
    if r["action"] not in COMPLETION_KINDS:
        return f"{who}: action {r['action']!r} is not one of {', '.join(COMPLETION_KINDS)}"
    if not parse_date(r["completed_at"]):
        return f"{who}: completed_at {r['completed_at']!r} does not start with YYYY-MM-DD"
    if r["action"] in REQUEST_KINDS and not (r["request_id"] and r["connector"]):
        return f"{who}: {r['action']} needs request_id and connector"
    if r["action"] == CHECKED_IN and not r["company_id"]:
        return f"{who}: {r['action']} needs company_id"
    return None


def merge_completions(rows: list[dict], path: Path = COMPLETIONS_OUT, origin: str = "") -> tuple[int, int]:
    """Add rows to golden/completions.csv: every row already on file stays, a
    completion_id already there is skipped, the rest are appended, and the file
    is written back sorted by (completed_at, completion_id) with the schema
    columns. A malformed incoming row ends the build before the file is
    touched. Returns (rows on file after, rows added)."""
    have = read_csv(path) if path.exists() else []
    seen = {r["completion_id"] for r in have}
    fresh, bad = [], []
    for i, raw in enumerate(rows, 1):
        r = completion_row(raw)
        if problem := completion_problem(r):
            bad.append(f"row {i}: {problem}")
        elif r["completion_id"] not in seen:
            seen.add(r["completion_id"])
            fresh.append(r)
    if bad:
        sys.exit(f"{origin or 'incoming completions'}: {len(bad)} bad row(s); {path.name} not touched.\n  " + "\n  ".join(bad))
    have.extend(fresh)
    have.sort(key=lambda r: (r.get("completed_at", ""), r["completion_id"]))
    if fresh or not path.exists():
        write_csv(path, COMPLETION_COLUMNS, have)
    return len(have), len(fresh)


SUPABASE_TABLE = "completions"
SUPABASE_PAGE = 1000
ENV_FILE = ROOT / ".env"


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    """The variables in .env (gitignored; KEY=value lines, # comments), also
    placed in os.environ where not already set, so SUPABASE_* work the same
    locally and under Actions secrets."""
    found: dict[str, str] = {}
    if not path.exists():
        return found
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip().removeprefix("export ").strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        found[key] = value
        os.environ.setdefault(key, value)
    return found


def supabase_rest(url: str) -> str:
    """The REST root for a project URL given with or without /rest/v1."""
    base = url.strip().rstrip("/")
    return base if base.endswith("/rest/v1") else base + "/rest/v1"


def fetch_supabase_completions(url: str, key: str, opener=None) -> list[dict]:
    """Every row of the completions table, oldest first, read with the service
    key (the anon key cannot select). Paged with Range headers. `opener`
    is urllib.request.urlopen unless a test passes its own."""
    opener = opener or urllib.request.urlopen
    endpoint = f"{supabase_rest(url)}/{SUPABASE_TABLE}?select=*&order=completed_at.asc,completion_id.asc"
    rows, start = [], 0
    while True:
        req = urllib.request.Request(endpoint, headers={
            "apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json",
            "Range-Unit": "items", "Range": f"{start}-{start + SUPABASE_PAGE - 1}",
        })
        with opener(req, timeout=30) as resp:
            page = json.loads(resp.read().decode("utf-8") or "[]")
        rows.extend(page)
        if len(page) < SUPABASE_PAGE:
            return rows
        start += SUPABASE_PAGE


def pull_completions(source: str | None, apply: Path | None, path: Path = COMPLETIONS_OUT,
                     fetch=fetch_supabase_completions) -> None:
    """Bring rows into golden/completions.csv before the build reads it:
    --completions supabase pulls the table (SUPABASE_URL + SUPABASE_SERVICE_KEY,
    from the environment or .env); --apply FILE merges a CSV. Either failing
    ends the build before anything is written."""
    if apply is not None:
        if not apply.exists():
            sys.exit(f"--apply {apply}: no such file")
        total, added = merge_completions(read_csv(apply), path, origin=f"--apply {apply}")
        print(f"completions.csv       {added} rows added from {apply.name}, {total} on file")
    if source == "supabase":
        load_env()
        url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not (url and key):
            sys.exit("--completions supabase needs SUPABASE_URL and SUPABASE_SERVICE_KEY (environment or .env)")
        try:
            rows = fetch(url, key)
        except Exception as e:  # noqa: BLE001 - any failure to read the table is one message
            sys.exit(f"could not read the Supabase {SUPABASE_TABLE} table: {e}\n"
                     f"the build still works without it: python3 golden/build_golden.py, or --apply FILE")
        total, added = merge_completions(rows, path, origin=f"supabase {SUPABASE_TABLE}")
        print(f"completions.csv       {added} rows added from supabase ({len(rows)} in the table), {total} on file")
    elif source:
        sys.exit(f"--completions {source}: only 'supabase' is known")


def completed_on(c: dict) -> str:
    """The date part of a completion's completed_at (a timestamptz from Supabase, or a date)."""
    return c["completed_at"].strip()[:10]


def completions_of(completions: list[dict], *kinds: str) -> dict[str, list[dict]]:
    """request_id (company_id for checked_in) -> that key's rows of the given actions, oldest first."""
    key = "company_id" if kinds == (CHECKED_IN,) else "request_id"
    out: dict[str, list[dict]] = defaultdict(list)
    for c in sorted((c for c in completions if c["action"] in kinds), key=lambda c: (c["completed_at"], c["completion_id"])):
        out[c[key]].append(c)
    return out


def with_completions(outcomes: list[dict], completions: list[dict]) -> list[dict]:
    """The ask log as the build reads it: intro_outcomes.csv plus one row per
    request with an `ask_sent` completion and no logged outcome (the earliest ask
    when there are several). Nothing has come back on those yet, so
    responded / intro_sent / meeting_booked are N. Every row carries
    reasked_date: on a logged row whose intro went out, the earliest `ask_sent`
    completion dated after the intro (the retry being sent), else empty."""
    asks_of = completions_of(completions, ASKED)
    rows = []
    for o in outcomes:
        reasked = ""
        if o["intro_sent"].strip() == "Y":
            after = [completed_on(c) for c in asks_of.get(o["request_id"], []) if completed_on(c) > (o["intro_date"] or "")]
            reasked = min(after) if after else ""
        rows.append({**o, "reasked_date": reasked})
    logged = {o["request_id"] for o in outcomes}
    extra = []
    for rid, asks in asks_of.items():
        if rid in logged:
            continue
        c = asks[0]
        extra.append({
            "request_id": rid, "connector_asked": c["connector"], "asked_date": completed_on(c),
            "responded": "N", "response_date": "", "intro_sent": "N", "intro_date": "",
            "meeting_booked": "N", "opportunity_created": "N", "opportunity_value_usd": "", "reasked_date": "",
            "source": "completions.csv", "completion_id": c["completion_id"],
        })
    return rows + sorted(extra, key=lambda o: (o["asked_date"], o["request_id"]))


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
    def __init__(self, accounts: list[dict], funds: list[str] = (), network_names: list[str] = ()):
        self._canon = Resolver(accounts, funds)  # the fund-collision guard lives there
        self.network_names = list(network_names)  # companies the network reaches; not in scope until requested
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

    def known_names(self) -> list[str]:
        """Every spelling on file: CRM names, funds, companies known only from requests,
        and every company someone in the network reaches (network_company_names)."""
        return [*(n for e in self._canon.entities for n in e.names),
                *(n for c in self.by_domain.values() for n in c.names),
                *self.network_names]

    def target_from_message(self, text: str) -> tuple[str, str]:
        """(company_as_written, domain_hint) named by a Slack message, via golden/parse.py."""
        t = extract_target(text, self._canon, names_regex(self.known_names())).target
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
    allocated that company to that connector with no ask logged since: an ask
    proposed and never logged as made (see logged_since).
    proposed: request_id -> the most recent prior-cycle row that allocated the
    request, again with no ask logged since."""
    fatigue: Counter
    stale: dict[tuple[str, str], dict]
    proposed: dict[str, dict]


def logged_since(outcome: dict | None, alloc: dict) -> bool:
    """Whether an ask was logged after a history row proposed it. A first ask is
    any outcome row (one dated before the decision means the row was a retry of
    an already-asked request, so only a reasked_date on or after the decision
    counts)."""
    if outcome is None:
        return False
    asked, decided = parse_date(outcome["asked_date"] or ""), decided_date(alloc)
    if asked is None or decided is None or asked >= decided:
        return True
    reasked = parse_date(outcome.get("reasked_date", "") or "")
    return reasked is not None and reasked >= decided


def history_signals(history: list[dict], outcomes: list[dict], today: date) -> HistorySignals:
    cycle = today.strftime("%Y-%m")
    outcome_of = {o["request_id"]: o for o in outcomes}
    fatigue: Counter = Counter()
    stale: dict[tuple[str, str], dict] = {}
    proposed: dict[str, dict] = {}
    for a in sorted((a for a in history if a["cycle"] < cycle and a["allocated_to"]),
                    key=lambda a: (a["cycle"], a.get("decided_at") or "")):
        d = decided_date(a)
        if d and 0 <= (today - d).days < FATIGUE_DAYS:
            fatigue[a["allocated_to"]] += 1
        if not logged_since(outcome_of.get(a["request_id"]), a):
            proposed[a["request_id"]] = a
            if a["company_id"]:
                stale[(a["allocated_to"], a["company_id"])] = a
    return HistorySignals(fatigue, stale, proposed)


def intro_of(o: dict, today: date) -> dict | None:
    """The intro an outcome row logged, or None. `live` while it booked a meeting
    or went out within INTRO_LIVE_DAYS; otherwise it has fizzled. `outcome` says
    where it stands, in words. The log has no meeting date, so a meeting's age
    is counted from the intro."""
    if o["intro_sent"].strip() != "Y":
        return None
    d = parse_date(o["intro_date"] or "")
    days = (today - d).days if d else None
    booked = o["meeting_booked"].strip() == "Y"
    opportunity = o["opportunity_created"].strip() == "Y"
    since = f"in {days} days" if days is not None else "yet"
    if opportunity:
        outcome = "opportunity created"
    elif booked:
        outcome = f"meeting booked, no opportunity {since}"
    else:
        outcome = f"no meeting {since}"
    return {
        "request_id": o["request_id"], "connector": o["connector_asked"], "intro_date": o["intro_date"],
        "days": days, "meeting_booked": booked, "opportunity": opportunity, "outcome": outcome,
        "live": booked or (days is not None and days <= INTRO_LIVE_DAYS),
    }


def retriable(o: dict, today: date) -> bool:
    """An asked request that goes back in the queue: its own intro fizzled and
    nobody has re-asked since (no reasked_date from completions.csv)."""
    i = intro_of(o, today)
    return i is not None and not i["live"] and not o.get("reasked_date", "")


def meeting_stalled(i: dict, requested_after: list[str]) -> bool:
    """A meeting that has not become an opportunity within INTRO_LIVE_DAYS while
    requests filed after the intro wait on the company: the intro no longer
    holds the company and its open requests go back in the queue."""
    return (i["meeting_booked"] and not i["opportunity"]
            and i["days"] is not None and i["days"] > INTRO_LIVE_DAYS
            and any(d > i["intro_date"] for d in requested_after))


def introductions(outcomes: list[dict], company_of: dict[str, str], today: date,
                  open_since: dict[str, list[str]] | None = None) -> dict[str, dict]:
    """company_id -> the intro that governs new asks on the company. An intro is
    `live` while it booked a meeting or went out within INTRO_LIVE_DAYS: the rep
    who received it extends it, nobody is asked afresh. A meeting stops holding
    the company once it has gone INTRO_LIVE_DAYS without an opportunity and
    `open_since` (company_id -> request_date of each open request) shows
    requests filed after it (meeting_stalled). With no live intro the newest
    one has fizzled and is named so the next ask reads as a retry. Companies
    with no intro sent are absent."""
    open_since = open_since or {}
    by_company: dict[str, list[dict]] = defaultdict(list)
    for o in outcomes:
        cid = company_of.get(o["request_id"], "")
        i = intro_of(o, today) if cid else None
        if i:
            if meeting_stalled(i, open_since.get(cid, [])):
                i = {**i, "live": False}
            by_company[cid].append(i)
    out = {}
    for cid, intros in by_company.items():
        live = [i for i in intros if i["live"]]
        out[cid] = max(live or intros, key=lambda i: (i["meeting_booked"], i["intro_date"], i["request_id"]))
    return out


def introduced_reason(intro: dict) -> str:
    return (f"{ALREADY_INTRODUCED}: {intro['connector']} on {intro['intro_date']} ({intro['request_id']}"
            + (", meeting booked)" if intro["meeting_booked"] else ")"))


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


def network_people(roster: dict) -> set[str]:
    """Everyone in investor_network.csv who is not on the roster."""
    return {inv["person"].strip() for inv in read_csv(DATASET / "investor_network.csv")} - set(roster)


def connector_type(roster: dict, network: set[str], name: str) -> str:
    r = roster.get(name)
    if r:
        return r["type"]
    return NETWORK_TYPE if name in network else "not on roster"


def network_company_names(roster: dict) -> list[str]:
    """Every company spelling the network reaches, as written in the roster's
    connections_*.csv and in investor_network.csv (portfolio_company,
    prior_employer); one entry per spelling, in file order."""
    names: dict[str, None] = {}
    for r in roster.values():
        for c in read_csv(DATASET / r["connections_file"]):
            if c["company"].strip():
                names.setdefault(c["company"].strip())
    for inv in read_csv(DATASET / "investor_network.csv"):
        for col in NETWORK_SOURCES:
            if inv[col].strip():
                names.setdefault(inv[col].strip())
    return list(names)


def network_reach(roster: dict, today: date) -> list[dict]:
    """Every path the network offers, before scope: one dict per (connector,
    company as written in the source) for direct (connections_*.csv), investor /
    investor_network (a fund's portfolio company) and alumni (a connection's prior
    employer) paths. build_supply keeps the ones into an in-scope company; the
    Live Priorities parser uses the rest to show what a company nobody has
    requested yet would get."""
    out: list[dict] = []
    person_to_connectors: dict[str, list[tuple[str, dict]]] = defaultdict(list)

    def path(connector: str, company: str, kind: str, contact: str, title: str,
             observed: str, strength: float, evidence: str, board_seat: str = "") -> None:
        out.append({"connector": connector, "company": company, "kind": kind, "contact": contact, "title": title,
                    "observed": observed, "strength": strength, "evidence": evidence, "board_seat": board_seat})

    # direct: first-degree connections of a roster connector
    for name, r in roster.items():
        for c in read_csv(DATASET / r["connections_file"]):
            person_to_connectors[c["name"]].append((name, c))
            s = PATH_BASE["direct"] * (0.55 + 0.45 * seniority(c["title"])) * freshness(c["connected_on"], today)
            path(name, c["company"], "direct", c["name"], c["title"], c["connected_on"], s,
                 f"{r['connections_file']}: {c['name']}, {c['title']} at {c['company']}, connected {c['connected_on']}")

    # investor: a roster investor's fund holds a position (board seat strengthens it);
    # investor_network: the same for a person off the roster (the haircut is applied in
    # path_score, not here, so strength reads the same as a roster investor's);
    # alumni: a connection's prior employer
    for inv in read_csv(DATASET / "investor_network.csv"):
        person = inv["person"].strip()
        if inv["portfolio_company"]:
            seat = inv["board_seat"].lower() == "true"
            path(person, inv["portfolio_company"], "investor" if person in roster else INVESTOR_NETWORK, "CEO / exec team",
                 f"{inv['fund']} {'board seat' if seat else 'portfolio company'}", "",
                 BOARD_SEAT_STRENGTH if seat else PATH_BASE["investor"],
                 f"investor_network.csv: {person} ({inv['role']}), portfolio_company={inv['portfolio_company']}, board_seat={inv['board_seat']}",
                 board_seat="yes" if seat else "no")
        if inv["prior_employer"]:
            tenure = f"{inv['prior_employer_start']}-{inv['prior_employer_end']}"
            for connector, conn in person_to_connectors.get(person, []):
                s = PATH_BASE["alumni"] * freshness(conn["connected_on"], today)
                path(connector, inv["prior_employer"], "alumni", person,
                     f"ex-{inv['prior_employer']} ({tenure}), now {conn['title']} at {conn['company']}",
                     conn["connected_on"], s,
                     f"investor_network.csv: {person} prior_employer={inv['prior_employer']} ({tenure}); "
                     f"{roster[connector]['connections_file']}: connection of {connector} since {conn['connected_on']}")
    return out


def supply_row(roster: dict, rates: dict, network: set[str], connector: str, company_id: str, company_name: str,
               industry: str, kind: str, contact: str, title: str, observed: str, strength: float, evidence: str,
               offer_age: int | None = None, board_seat: str = "") -> dict:
    """One supply_reach.csv row (before finish_supply stamps idle_capacity)."""
    r = roster.get(connector)
    if r:
        focus = "yes" if industry and industry in r["focus"] else ("unknown" if not industry else "no")
    else:
        focus = "unknown"
    return {
        "connector": connector,
        "connector_type": connector_type(roster, network, connector),
        "company_id": company_id,
        "company_name": company_name,
        "reach_type": kind,
        "board_seat": board_seat,
        "contact_name": contact,
        "contact_title": title,
        "observed_date": observed,
        "offer_age_days": "" if offer_age is None else offer_age,
        "strength": f"{strength:.3f}",
        "in_focus_area": focus,
        "monthly_capacity": capacity(roster, connector),
        "delivery_rate": f"{rates.get(connector, PRIOR_RATE):.3f}",
        "evidence": evidence,
    }


def build_supply(reg: Registry, roster: dict, rates: dict, today: date,
                 request_company: dict[str, Company | None], threads: dict[str, dict]) -> list[dict]:
    """One row per way into an in-scope company. Sources that name a company
    outside the CRM + requested set produce no row."""
    rows: list[dict] = []
    network = network_people(roster)

    def emit(connector: str, company: Company, kind: str, contact: str, title: str,
             observed: str, strength: float, evidence: str, offer_age: int | None = None,
             board_seat: str = ""):
        s = company.survivor
        rows.append(supply_row(roster, rates, network, connector, company.company_id, company.name,
                               s["industry"] if s else "", kind, contact, title, observed, strength, evidence,
                               offer_age, board_seat))

    for p in network_reach(roster, today):
        company, _ = reg.resolve_in_scope(p["company"])
        if company is None:
            continue
        emit(p["connector"], company, p["kind"], p["contact"], p["title"], p["observed"], p["strength"], p["evidence"],
             board_seat=p["board_seat"])

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

    network = network_people(roster)
    askable = set(roster) | {o["connector_asked"] for o in outcomes if o["connector_asked"]}
    askable |= {m["user"] for th in threads.values() for m in th["offers"]}
    for name in sorted(askable - set(paths)):
        rows.append({
            "connector": name,
            "connector_type": connector_type(roster, network, name),
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
# network orbit: who else sits around a company, from investor_network.csv
# ---------------------------------------------------------------------------
def build_network_orbit(reg: Registry, roster: dict) -> list[dict]:
    """One row per (person, company) pair in investor_network.csv, for every
    person in the file (on the roster or not), through the same resolver the
    supply side uses. Rows naming a company outside the in-scope set are
    dropped. A view, not a source: nothing here feeds supply_reach.csv or the
    allocator; reachable_via = investor_network names the supply row build_supply
    already emitted for an off-roster person's own portfolio company."""
    known_to: dict[str, set[str]] = defaultdict(set)  # person -> connector surnames whose export lists them
    for name, r in roster.items():
        surname = name.split()[-1]
        for c in read_csv(DATASET / r["connections_file"]):
            known_to[c["name"]].add(surname)
    rows = []
    for inv in read_csv(DATASET / "investor_network.csv"):
        person = inv["person"].strip()
        for source in NETWORK_SOURCES:
            if not inv[source]:
                continue
            company, _ = reg.resolve(inv[source])
            if company is None:
                continue
            if person in roster:
                via = REACHABLE_AS_CONNECTOR
            elif known_to.get(person):
                via = MULTI.join(sorted(known_to[person]))
            elif source == "portfolio_company" and reg.resolve_in_scope(inv[source])[0] is not None:
                via = INVESTOR_NETWORK
            else:
                via = ""
            rows.append({
                "company_id": company.company_id,
                "company_name": company.name,
                "person": person,
                "role": inv["role"],
                "fund": inv["fund"],
                "board_seat": "yes" if source == "portfolio_company" and inv["board_seat"].strip().lower() == "true" else "no",
                "source": source,
                "reachable_via": via,
            })
    rows.sort(key=lambda r: (r["company_id"], r["board_seat"] != "yes", r["reachable_via"] == "", r["person"], r["source"]))
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
    best, best_rank, best_score = None, None, 0.0
    for p in paths:
        if p["connector"] == exclude_connector:
            continue
        rank = path_rank(p, roster, rates, industry)
        if rank[1] < 0 and (best_rank is None or rank < best_rank):
            best, best_rank, best_score = p, rank, -rank[1]
    return best, best_score


def path_score(p: dict, roster: dict, rates: dict, industry: str) -> float:
    """strength x focus fit x delivery rate, the allocator's sort key; an
    investor_network path (our circle, not our roster) then takes NETWORK_HAIRCUT."""
    r = roster.get(p["connector"])
    f = fit(r, industry) if r else 0.7
    score = float(p["strength"]) * f * rates.get(p["connector"], PRIOR_RATE)
    return score * NETWORK_HAIRCUT if p["reach_type"] == INVESTOR_NETWORK else score


def path_rank(p: dict, roster: dict, rates: dict, industry: str) -> tuple[int, float]:
    """The allocator's sort key, ascending: roster paths before investor_network
    ones, then by route score. The roster is asked first; our wider network fills
    in only when no roster path exists or every one is out of capacity."""
    return (int(p["reach_type"] == INVESTOR_NETWORK), -path_score(p, roster, rates, industry))


def allocate(roster: dict, rates: dict, outcomes: list[dict], supply_by_company: dict[str, list[dict]],
             resolved: dict[str, dict], today: date, decided_at: str, signals: HistorySignals) -> dict[str, dict]:
    """request_id -> allocation row for every live request not yet asked,
    taken from the request file (filed rows plus the ones about to be appended),
    and for every asked request whose own intro fizzled with nobody re-asked
    since (retriable): the intro went nowhere, so the request is back in the
    queue as a retry rather than left in limbo behind a logged ask.

    Each connector has a budget for the cycle (cycle_budget): stated monthly
    capacity (OFF_ROSTER_CAPACITY off the roster) less the asks the history
    says were proposed to them in the trailing FATIGUE_DAYS beyond one month's
    capacity. Requests are taken in priority order (urgency, value, age) and
    each goes to its best-scoring connector that still has budget. An ask the
    history already holds with no outcome logged since is not proposed again:
    a request allocated in a prior cycle, or a connector already proposed this
    company in a prior cycle, is flagged (STALE_ASK, naming that connector and
    cycle) instead of being allocated or falling through to the next
    connector. A request on a company whose intro is still live
    (introductions) is parked (ALREADY_INTRODUCED, naming the intro) rather
    than asked afresh: the rep who received the intro extends it. A meeting
    that has gone INTRO_LIVE_DAYS without an opportunity stops parking the
    company once requests are filed after it (meeting_stalled): its open
    requests are routed again, as retries.
    Roster paths are tried before investor_network ones whatever their scores
    (path_rank). Once every connector with a path is spent the request becomes
    an exception. Requests
    allocated to the same connector share a batch_id: one consolidated ask."""
    cycle = today.strftime("%Y-%m")
    fatigue, stale, proposed = signals
    budget: dict[str, int] = defaultdict(int)
    for n in set(roster) | {p["connector"] for paths in supply_by_company.values() for p in paths}:
        budget[n] = cycle_budget(roster, fatigue, n)

    asked = {o["request_id"] for o in outcomes}
    retry = {o["request_id"] for o in outcomes if retriable(o, today)}
    open_since: dict[str, list[str]] = defaultdict(list)
    for rq in resolved.values():
        if rq["company"] and rq["facts"]["status_as_filed"] in OPEN_STATUSES:
            open_since[rq["company"].company_id].append(rq["facts"]["request_date"])
    introduced = introductions(outcomes, {rid: rq["company"].company_id for rid, rq in resolved.items() if rq["company"]},
                               today, open_since)
    live = [(rid, rq) for rid, rq in resolved.items()
            if rq["facts"]["status_as_filed"] in OPEN_STATUSES and (rid not in asked or rid in retry)]
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
        scored = [(-rank[1], p) for rank, p in sorted(((path_rank(p, roster, rates, industry), p) for p in paths),
                                                       key=lambda t: t[0]) if rank[1] < 0]
        if scored:
            best_sc, best = scored[0]
            row["best_path_if_unbudgeted"] = f"{best['connector']} ({best['reach_type']}, {best_sc:.2f})"
        intro = introduced.get(company.company_id)
        if intro and intro["live"]:
            row["exception_reason"] = introduced_reason(intro)
            continue
        if not scored:
            row["exception_reason"] = "no path to this company in the network"
            continue
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


def stage_of(request: dict, outcome: dict | None, alloc: dict | None) -> str:
    """Point in time: each request sits in exactly one stage; 'closed' is excluded from the strip.
    `outcome` is the request's intro_outcomes.csv row (with completions applied),
    `alloc` its row in the current allocation cycle; either may be None."""
    r, o, a = request, outcome, alloc
    if (o and o["meeting_booked"] == "Y") or r["meeting_booked"] == "Y":
        return "meeting booked"
    if (o and o["intro_sent"] == "Y") or r["intro_sent"] == "Y" or r["status_as_filed"] == "Intro sent":
        return "introduced"
    if r["status_as_filed"] == "Closed - no path":
        return "closed"
    if o or r["asked_date"]:
        return "asked"
    if r["routed_to"] or (a and a["allocated_to"]):
        return "routed"
    if not r["company_id"] or not r["value_usd"]:
        return "needs data"
    return "to be routed"


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
    if alloc and alloc["exception_reason"].startswith(ALREADY_INTRODUCED):
        return ALREADY_INTRODUCED
    if not any(p["connector"] in roster for p in paths):
        return BLOCK_NO_ROSTER_PATH
    return BLOCK_NEVER_ROUTED


def build_requests(reg: Registry, roster: dict, rates: dict, supply_by_company: dict[str, list[dict]],
                   resolved: dict[str, dict], threads: dict[str, dict],
                   allocation: dict[str, dict], filed: list[dict], outcomes: list[dict],
                   completions: list[dict] | None = None) -> list[dict]:
    outcomes = {o["request_id"]: o for o in outcomes}
    nudges = completions_of(completions or [], *FOLLOW_UPS)
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
                if alt and (bp is None or path_rank(alt, roster, rates, industry) < path_rank(bp, roster, rates, industry)):
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

        # an asked row keeps its filed routing, so judge its block against that
        filed_row = filed_by.get(rid)
        effective_routed_to = filed_row["routed_to"] if filed_row and filed_row["asked_date"] else routed_to
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
            "nudged_on": max((completed_on(n) for n in nudges.get(rid, [])),
                             default=filed_by.get(rid, {}).get("nudged_on", "")),
        })
    rows.sort(key=lambda r: r["request_id"])
    return rows


def merge_write(rows: list[dict], source: dict[str, dict | None]) -> tuple[int, int, int, list[str], list[str]]:
    """Merge the recomputed rows into golden_requests.csv. Every filed row is
    kept. Rows whose request_id is new are appended. On a filed row,
    RECOMPUTED_COLUMNS take the recomputed value; ROUTING_COLUMNS take it too
    while the row has no asked_date (the allocation they describe is redone
    every run); OUTCOME_COLUMNS are filled in once, when the row has no
    asked_date yet and the ask log now has one, and from then on the routing
    is kept as filed with the ask;
    nudged_on advances to the latest nudge; every other column keeps its filed
    value. source is FACT_COLUMNS as the raw export states them now (None
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
        if not old["asked_date"]:
            if r["asked_date"]:
                diff += [c for c in OUTCOME_COLUMNS if str(old[c]) != str(r[c])]
                warnings.append(f"{old['request_id']}: ask logged, {r['routed_to']} on {r['asked_date']}")
            else:
                diff += [c for c in ROUTING_COLUMNS if str(old[c]) != str(r[c])]
        if r["nudged_on"] > old["nudged_on"]:
            diff.append("nudged_on")
        if diff:
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
def build_companies(reg: Registry, supply: list[dict], requests: list[dict], today: date,
                    outcomes: list[dict] | None = None, completions: list[dict] | None = None) -> list[dict]:
    checkins = completions_of(completions or [], CHECKED_IN)
    by_company = defaultdict(list)
    for r in requests:
        if r["company_id"]:
            by_company[r["company_id"]].append(r)
    supply_by = defaultdict(list)
    for s in supply:
        supply_by[s["company_id"]].append(s)
    outcomes = {o["request_id"]: o for o in (read_csv(DATASET / "intro_outcomes.csv") if outcomes is None else outcomes)}

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
            "checked_in_on": completed_on(checkins[c.company_id][-1]) if c.company_id in checkins else "",
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
    # a rerun that reaches exactly the decision already filed for this cycle keeps
    # its decided_at (so an unchanged rebuild is a no-op); any difference restamps
    # the whole cycle, so a cycle still carries one decided_at per run
    filed = {a["request_id"]: a for a in history if a["cycle"] == cycle}
    same = [c for c in ALLOCATION_COLUMNS if c != "decided_at"]
    unchanged = (
        len(filed) == len(current) and all(a.get("decided_at") for a in filed.values())
        and all(a["request_id"] in filed
                and all(str(filed[a["request_id"]].get(c, "")) == str(a.get(c, "")) for c in same)
                for a in current)
    )
    if unchanged:
        for a in current:
            a["decided_at"] = filed[a["request_id"]]["decided_at"]
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
    ap.add_argument("--as-of", default=as_of().isoformat(), help="the build clock (default: HALYARD_AS_OF, else today, UTC)")
    ap.add_argument("--threads", type=Path, help="a Slack export (.jsonl) to ingest alongside dataset/slack_threads.jsonl")
    ap.add_argument("--completions", choices=["supabase"], help="pull the Supabase completions table into golden/completions.csv first")
    ap.add_argument("--apply", type=Path, metavar="FILE", help="merge a CSV of completions into golden/completions.csv first")
    args = ap.parse_args()
    pull_completions(args.completions, args.apply)
    today = parse_date(args.as_of) or as_of()
    cycle = today.strftime("%Y-%m")
    # the build clock: the as-of date, at the wall-clock time the run started
    decided_at = datetime.combine(today, datetime.now(timezone.utc).time()).strftime("%Y-%m-%dT%H:%M:%SZ")

    # In-scope set = CRM accounts + every company in the request file (rows
    # already filed, plus raw requests about to be appended). IDs are pinned to
    # the existing golden files before any supply-side source is read.
    filed = read_csv(REQUESTS_OUT) if REQUESTS_OUT.exists() else []
    roster = load_roster()
    reg = Registry(read_csv(DATASET / "crm_accounts.csv"),
                   [inv["fund"] for inv in read_csv(DATASET / "investor_network.csv")],
                   network_company_names(roster))
    threads = load_threads(args.threads)
    resolved = resolve_requests(reg, filed, {rid: th for rid, th in threads.items() if th["ingested"]})
    reg.assign_ids()

    completions = load_completions()
    outcomes = with_completions(read_csv(DATASET / "intro_outcomes.csv"), completions)
    rates = delivery_rates(roster, outcomes, threads)
    history = read_allocation()
    signals = history_signals(history, outcomes, today)

    supply = build_supply(reg, roster, rates, today, {rid: rq["company"] for rid, rq in resolved.items()}, threads)

    supply_by = defaultdict(list)
    for s in supply:
        supply_by[s["company_id"]].append(s)
    allocation = allocate(roster, rates, outcomes, supply_by, resolved, today, decided_at, signals)
    requests = build_requests(reg, roster, rates, supply_by, resolved, threads, allocation, filed, outcomes, completions)
    kept, appended, changed, added, warnings = merge_write(
        requests, {rid: rq["source"] for rid, rq in resolved.items()})
    carried = sum(1 for rq in resolved.values() if rq["source"] is None)

    # Derived files: all three computed from the request file as just written,
    # then swapped in together.
    supply = finish_supply(supply, roster, rates, outcomes, allocation, threads, signals.fatigue)
    alloc_rows = sorted(allocation.values(), key=lambda a: (a["allocated_to"] == "", a["batch_id"], a["request_id"]))
    all_alloc, prior_cycles, prior_rows, replaced = merge_allocation(history, alloc_rows, cycle)
    companies = build_companies(reg, supply, read_csv(REQUESTS_OUT), today, outcomes, completions)
    write_derived(supply, all_alloc, companies)
    orbit = build_network_orbit(reg, roster)
    write_csv(NETWORK_OUT, NETWORK_COLUMNS, orbit)

    if completions:
        kinds = Counter(c["action"] for c in completions)
        print(f"completions.csv       {len(completions)} rows applied: "
              + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items())))

    print(f"golden_requests.csv   {kept + appended} rows ({kept} kept, of which {carried} not in "
          f"dataset/intro_requests.csv and carried forward; {appended} appended; "
          f"{changed} with recomputed {'/'.join(RECOMPUTED_COLUMNS[:3])}/... changed"
          + (f"; columns added: {', '.join(added)}" if added else "") + ")")
    print(f"golden_companies.csv  {len(companies)} rows (rebuilt)")
    print(f"supply_reach.csv      {len(supply)} rows (rebuilt): "
          + ", ".join(f"{k} {n}" for k, n in sorted(Counter(s['reach_type'] for s in supply).items())))
    print(f"network_orbit.csv     {len(orbit)} rows (rebuilt) across {len({r['company_id'] for r in orbit})} companies: "
          + ", ".join(f"{k} {n}" for k, n in sorted(Counter(r['source'] for r in orbit).items()))
          + f"; {sum(1 for r in orbit if not r['reachable_via'])} with no warm route")
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
