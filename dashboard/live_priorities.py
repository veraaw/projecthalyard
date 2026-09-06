"""The "Live Priorities" tab, docs/livepriorities.html (built by dashboard/build_dashboard.py).

    from dashboard.live_priorities import fragment, payload
    data = payload()           # every section as plain dicts/lists: the browser only renders this
    html = fragment()          # <div> with the JSON payload embedded + dashboard/live_priorities.js

Everything on the tab is computed here, from golden/ and dataset/, and written
into one JSON payload; the JavaScript renders it and never derives a number.
Two things the page does with user input. The upload preview: the parser
rules (golden/parse.py cues, golden/build_golden.py OFFER_RE, and the
golden/resolver.py lookup tables) are exported into the payload and applied
verbatim by the browser, so a dropped .jsonl previews exactly what
`python3 golden/build_golden.py --threads FILE` would file. And Submit: the
tick-boxes on Top priorities (an ask sent), Core bottlenecks (a nudge sent) and
the connector pages' "already sitting on" (a nudge or a chase sent) are posted,
one row each, to the Supabase
`completions` table with the anon key (insert-only; the
URL and key come from SUPABASE_URL / SUPABASE_ANON_KEY at build time, never
from this file). The scheduled rebuild (.github/workflows/rebuild.yml) pulls
the table into golden/completions.csv, a fact source of the build, and the
ticked items leave the queue. docs/build_stamp.json says when that last
happened; the page shows it.

    python3 -m dashboard.live_priorities     # prints the payload summary
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime
from os.path import commonprefix

from analysis.crm import writeback as wb
from analysis.trace import all_traces
from dashboard import batch_ask
from golden import build_golden as bg
from golden import parse as gp
from golden import resolver as gr
from golden.resolve_cli import load_resolver
from paths import DASHBOARD, DATASET, DOCS, GOLDEN, ROOT

# ---------------------------------------------------------------------------
# constants the ranking uses; every one is shown on the tab
# ---------------------------------------------------------------------------
STAGES = bg.STAGES  # routing stages, in order; stage_of() lives in build_golden
# CRM stage -> probability weight on the deal value (pipeline weighting)
STAGE_WEIGHT = {
    "Negotiation": 0.9, "Pilot": 0.75, "Evaluation": 0.55, "Discovery": 0.35, "Prospect": 0.25,
    "Closed Lost": 0.1,
}
NO_CRM_WEIGHT = 0.25   # a requested company with no CRM account
AGE_CAP_DAYS = 365     # age factor = 1 + min(days waiting, cap) / cap  (1.0 .. 2.0)
CHECKIN_DAYS = 60
TOP_N = 5
NUDGE_QUIET_DAYS = 14  # a bottleneck nudged this recently is off the list until the quiet period passes
BUILD_STAMP = DOCS / "build_stamp.json"  # when the site was last generated; the page shows it
WORKFLOW_FILE = "rebuild.yml"  # .github/workflows/, the scheduled rebuild the page reports the last run of

PAGE = "livepriorities.html"
BATCH_PAGE = "batchask.html"
TRACE_PAGE = "companytrace.html"
CONNECTOR_PAGE = "connector-{slug}.html"
# the page reads top to bottom in five bands: (id, title, membership test, sections). Each band's
# sections are (section id, nav label) as rendered by live_priorities.js boot(), in page order.
BANDS = [
    ("intake", "Intake: Preview a Routed Request Summary",
     "Does it accept input the build doesn't have yet?",
     [("route", "Route a request"), ("upload", "Preview an export")]),
    ("orientation", "Orientation: Deal Value by Stage",
     "Is it a single aggregate with no rows?",
     [("stages", "Deal value by stage")]),
    ("now", "Actionable Routing Steps",
     "Does ticking it change what the queue proposes tomorrow?",
     [("top", "Top priorities"), ("offers", "Already offered"), ("bottlenecks", "Core bottlenecks"), ("crm", "CRM Updates")]),
    ("cycle", "Current Cycle Overview",
     "Does it describe a decision the allocator already made?",
     [("asks", "Current asks"), ("introduced", "Already introduced"), ("connectors", "Roster Connectors")]),
    ("stuck", "Not Moving",
     "Does the action belong to someone who isn't reading this page?",
     [("unrouted", "Unrouted"), ("checkins", "Check-ins")]),
]
# every section in page order; drives the header nav
SECTIONS = [s for _, _, _, sections in BANDS for s in sections]
THREADS_COMMAND = "python3 golden/build_golden.py --threads {file} && python3 build.py"

# "Route a live request" presets: real message shapes, one per thing the router must get right
ROUTE_PRESETS = [
    {"label": "Distractor", "text": "Calderon Aerospace introduced us to Kestrel Airlines, but the account I actually need is Ironvale Steel"},
    {"label": "Bridge", "text": "trying to reach COO at Apex Logistics. I know we sell into Larkhall Software and Cindermill Mining"},
    {"label": "Domain only", "text": "email domain is bexleybio.com"},
    {"label": "No path", "text": "any connections into Halcyon Grid?"},
    {"label": "Fund or customer", "text": "who do we know at Thornbury?"},
    {"label": "No CRM record", "text": "any connections into Kingsmere Retail Group? we're up against a renewal window"},
]


def parse_date(s: str) -> date | None:
    try:
        return datetime.strptime((s or "").strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def money(v: int | float | str) -> str:
    """$3.8M / $400K / $0 — one decimal, no trailing .0"""
    try:
        n = float(v or 0)
    except (TypeError, ValueError):
        n = 0.0
    if n >= 1e6:
        s = f"{n / 1e6:.1f}".rstrip("0").rstrip(".")
        return f"${s}M"
    if n >= 1e3:
        return f"${n / 1e3:.0f}K"
    return f"${n:,.0f}"


def usd(v: str) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def bar(s: str) -> list[str]:
    return [p.strip() for p in (s or "").split("|") if p.strip()]


def js_regex(p: re.Pattern) -> dict:
    """A Python pattern as {source, flags} for `new RegExp`. Only the named-group
    syntax differs between the two engines for the patterns exported here."""
    return {"source": p.pattern.replace("(?P<", "(?<"), "flags": "i" if p.flags & re.I else ""}


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def repo_url() -> str:
    """https://github.com/<owner>/<repo> for the checkout, from GITHUB_REPOSITORY
    (Actions) or the origin remote; '' when neither is available."""
    if os.environ.get("GITHUB_REPOSITORY"):
        return f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ['GITHUB_REPOSITORY']}"
    try:
        origin = subprocess.run(["git", "config", "--get", "remote.origin.url"], capture_output=True, text=True,
                                cwd=DASHBOARD, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    m = re.match(r"^(?:https?://|git@)([^/:]+)[/:](.+?)(?:\.git)?/?$", origin)
    return f"https://{m.group(1)}/{m.group(2)}" if m else ""


def csv_text(columns: list[str], rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\r\n", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in columns})
    return buf.getvalue()


# ---------------------------------------------------------------------------
class Live:
    def __init__(self, today: date):
        self.today = today
        self.requests = bg.read_csv(GOLDEN / "golden_requests.csv")
        self.by_rid = {r["request_id"]: r for r in self.requests}
        self.companies = {c["company_id"]: c for c in bg.read_csv(GOLDEN / "golden_companies.csv")}
        self.supply = bg.read_csv(GOLDEN / "supply_reach.csv")
        self.history = bg.read_allocation(GOLDEN / "golden_allocation.csv")
        self.allocation = bg.latest_cycle(self.history)
        self.alloc_by_rid = {a["request_id"]: a for a in self.allocation}
        self.completions = bg.load_completions()
        self.outcomes = bg.with_completions(bg.read_csv(DATASET / "intro_outcomes.csv"), self.completions)
        self.outcome_by_rid = {o["request_id"]: o for o in self.outcomes}
        self.raw = {r["request_id"]: r for r in bg.read_csv(DATASET / "intro_requests.csv")}
        self.accounts = {a["account_id"]: a for a in bg.read_csv(DATASET / "crm_accounts.csv")}
        self.roster = bg.load_roster()
        self.threads = bg.load_threads()
        self.rates = bg.delivery_rates(self.roster, self.outcomes, self.threads)
        self.cycle = self.allocation[0]["cycle"] if self.allocation else today.strftime("%Y-%m")
        self.fatigue = bg.history_signals(self.history, self.outcomes, today).fatigue
        self.intro_state = bg.introductions(self.outcomes, {r["request_id"]: r["company_id"] for r in self.requests}, today)
        self.batch_asks = batch_ask.compose(self.history, self.requests, self.roster, outcomes=self.outcomes)
        self.traceable = {t["company_id"] for t in all_traces(today)}
        self._ranked: list[dict] | None = None

        self.paths: dict[str, list[dict]] = defaultdict(list)
        self.connector_facts: dict[str, dict] = {}
        for s in self.supply:
            if s["company_id"]:
                self.paths[s["company_id"]].append(s)
            self.connector_facts.setdefault(s["connector"], {
                "connector": s["connector"], "type": s["connector_type"],
                "capacity": int(s["monthly_capacity"]), "idle": int(s["idle_capacity"]),
                "rate": float(s["delivery_rate"]), "on_roster": s["connector"] in self.roster,
            })
        self.by_company: dict[str, list[dict]] = defaultdict(list)
        for r in self.requests:
            if r["company_id"]:
                self.by_company[r["company_id"]].append(r)

    # -- helpers --------------------------------------------------------------
    def industry(self, cid: str) -> str:
        return self.companies.get(cid, {}).get("industry", "")

    def fit(self, connector: str, industry: str) -> float:
        r = self.roster.get(connector)
        return bg.fit(r, industry) if r else 0.7

    def rate(self, connector: str) -> float:
        return self.rates.get(connector, bg.PRIOR_RATE)

    def ranked_paths(self, cid: str) -> list[dict]:
        """Every path into a company from supply_reach.csv, best first, scored as the
        build scores them (strength x focus fit x delivery rate), each with the one
        line of reasoning the route panel shows."""
        ind = self.industry(cid)
        out = []
        for p in self.paths.get(cid, []):
            n = p["connector"]
            fit, rate = self.fit(n, ind), self.rate(n)
            r = self.roster.get(n)
            when = (p["observed_date"] or "")[:7]
            if p["reach_type"] == "offer":
                via = "Offered in Slack" + (f" (knows {p['contact_title']})" if p["contact_title"] else "")
                via += f" · {p['offer_age_days']} days ago" if p["offer_age_days"] else ""
            elif p["reach_type"] == "investor":
                via = f"{'Board seat' if p['board_seat'] == 'yes' else 'Investor'} · {p['contact_title']}" if p["contact_title"] else "Investor path"
            elif p["reach_type"] == "alumni":
                via = f"Via {p['contact_name']} ({p['contact_title']})" if p["contact_title"] else f"Via {p['contact_name']}"
                via += f" · alumni link {when}" if when else ""
            else:
                via = f"Via {p['contact_name']}" + (f" ({p['contact_title']})" if p["contact_title"] else "") + (f" · connected {when}" if when else "")
            if r is None:
                focus = "not on the roster, no stated focus"
            elif not ind:
                focus = "industry unknown"
            elif fit >= 1.0:
                focus = "in their focus area"
            elif fit <= 0.0:
                focus = "outside their focus, and they decline anything outside"
            else:
                focus = "outside their focus area"
            cap = bg.capacity(self.roster, n)
            idle = self.connector_facts.get(n, {}).get("idle", cap)
            capacity_left = max(0, idle) / cap if cap else 0.0
            score = float(p["strength"]) * fit * rate
            out.append({
                "connector": n, "connector_type": p["connector_type"], "on_roster": r is not None, "reach_type": p["reach_type"],
                "contact": p["contact_name"], "title": p["contact_title"], "connected": when, "board_seat": p["board_seat"] == "yes",
                "strength": round(float(p["strength"]), 3), "fit": round(fit, 2), "rate": round(rate, 3),
                "score": round(score, 3), "in_focus": p["in_focus_area"], "idle": idle, "capacity": cap,
                "capacity_left": round(capacity_left, 3), "connector_score": round(score * capacity_left, 3),
                "evidence": p["evidence"], "label": bg.path_label(p),
                "reason": f"{via} · delivers {round(rate * 100)}% of asks · {focus}",
            })
        out.sort(key=lambda p: -p["score"])
        return out

    def route_priority(self, cid: str) -> dict:
        """Request priority for a message about this company pasted today: deal value is
        the CRM's ARR potential (a Slack message carries none), else the largest live
        request on the company; age is 1.0 (posted today); reps waiting counts the
        requesters already live on the company, at least one (the poster)."""
        c = self.companies[cid]
        acct = next((self.accounts[a] for a in bar(c["crm_account_ids"]) if a in self.accounts), None)
        live = [usd(r["value_usd"]) for r in self.by_company.get(cid, []) if r["status_as_filed"] in bg.OPEN_STATUSES]
        if acct and usd(acct["arr_potential_usd"]):
            deal, source = usd(acct["arr_potential_usd"]), "CRM ARR potential"
        elif live and max(live):
            deal, source = max(live), "largest live request on the company"
        else:
            deal, source = 0, "no deal value on file"
        comp = {
            "deal_value_musd": deal / 1e6,
            "stage_weight": STAGE_WEIGHT.get(c["stage"], NO_CRM_WEIGHT) if c["crm_account_ids"] else NO_CRM_WEIGHT,
            "age": 1.0,
            "reps_waiting": max(1, len(self.live_requesters(cid))),
        }
        return {"request_priority": round(comp["deal_value_musd"] * comp["stage_weight"] * comp["age"] * comp["reps_waiting"], 3),
                "components": {k: round(v, 3) for k, v in comp.items()}, "deal_source": source}

    def crm_stage(self, cid: str) -> str:
        """The company's CRM stage (golden_companies.stage) or 'no CRM account'."""
        return self.companies.get(cid, {}).get("stage", "") or "no CRM account"

    def sector_cover(self, cid: str) -> dict:
        """Who on the roster covers the company's industry (it is in their focus
        areas), in roster order, each with whether they were ever asked about this
        company. The named person to go to when nobody in the network has a path."""
        ind = self.industry(cid)
        rids = {r["request_id"] for r in self.by_company.get(cid, [])}
        asked = defaultdict(list)
        for o in self.outcomes:
            if o["request_id"] in rids and o["connector_asked"]:
                asked[o["connector_asked"]].append(o["asked_date"])
        who = [{"connector": n, "asked": sorted(asked[n])[-1] if asked[n] else ""}
               for n, r in self.roster.items() if ind and ind in r["focus"]]
        return {"industry": ind, "connectors": who,
                "note": "" if who else (f"nobody on the roster covers {ind}" if ind else "industry unknown")}

    def company_ref(self, cid: str, name: str = "") -> dict:
        c = self.companies.get(cid)
        return {
            "company_id": cid,
            "company_name": (c["company_name"] if c else name) or name or "(unresolved)",
            "href": f"{TRACE_PAGE}#{cid}" if cid in self.traceable else "",
        }

    def wanted(self, rows: list[dict]) -> list[str]:
        """Every person wanted: 'Name (Title)' from the raw export where it names a person, else the title."""
        out, seen = [], set()
        for r in rows:
            raw = self.raw.get(r["request_id"], {})
            person, title = raw.get("target_person_raw", "").strip(), r["target_title"] or raw.get("target_title_raw", "").strip()
            label = f"{person} ({title})" if person and title else person or title or "(no title given)"
            if label not in seen:
                seen.add(label)
                out.append(label)
        return out

    def prior_intro(self, cid: str) -> dict | None:
        """The intro that governs new asks on the company (build_golden.introductions),
        with who it reached: the rep who filed that request owns any follow-up on it."""
        i = self.intro_state.get(cid)
        if not i:
            return None
        r = self.by_rid.get(i["request_id"], {})
        return {**i, "requested_by": r.get("requested_by", ""), "target_title": r.get("target_title", "")}

    def retry_of(self, cid: str) -> dict | None:
        """Set when the company's last intro fizzled (no meeting, older than
        INTRO_LIVE_DAYS): a fresh ask on it is a retry and is labelled as one."""
        i = self.prior_intro(cid)
        if not i or i["live"]:
            return None
        when = i["intro_date"] or "an undated"
        age = f"{i['days']} days" if i["days"] is not None else "since"
        return {**i, "note": f"{i['connector'].split()[0]}'s {when} intro to {i['requested_by'] or 'the requester'} went nowhere: no meeting in {age}"}

    def live_requesters(self, cid: str) -> list[str]:
        return sorted({r["requested_by"] for r in self.by_company.get(cid, [])
                       if r["status_as_filed"] in bg.OPEN_STATUSES})

    def asks_this_cycle(self, connector: str) -> int:
        return sum(1 for o in self.outcomes if o["connector_asked"] == connector and o["asked_date"].startswith(self.cycle))

    def cycle_list(self) -> list[str]:
        """Every calendar month from the first ask on file through the current cycle."""
        first = min((o["asked_date"][:7] for o in self.outcomes if o["asked_date"]), default=self.cycle)
        y, m = int(first[:4]), int(first[5:7])
        out = []
        while f"{y:04d}-{m:02d}" <= self.cycle:
            out.append(f"{y:04d}-{m:02d}")
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return out

    def cycle_rows(self, names: list[str]) -> list[dict]:
        """Per cycle (a calendar month, the allocator's unit): asks made, slots used
        against stated capacity, intros made (by intro_date) and the running total
        of intros. One connector, or several summed. Capacity is the stated monthly
        capacity of whoever in `names` is on the roster, and only their asks count
        against it; the current cycle counts this build's allocation as slots used,
        since those asks are about to go out."""
        names = set(names)
        on_roster = {n for n in names if n in self.roster}
        cap = sum(int(self.roster[n]["stated_monthly_capacity"] or 0) for n in on_roster)
        mine = [o for o in self.outcomes if o["connector_asked"] in names]
        allocated = sum(1 for a in self.allocation if a["allocated_to"] in names)
        allocated_roster = sum(1 for a in self.allocation if a["allocated_to"] in on_roster)
        rows, cum = [], 0
        for cyc in self.cycle_list():
            asks = sum(1 for o in mine if o["asked_date"].startswith(cyc))
            asks_roster = sum(1 for o in mine if o["asked_date"].startswith(cyc) and o["connector_asked"] in on_roster)
            intros = sum(1 for o in mine if o["intro_sent"] == "Y" and o["intro_date"].startswith(cyc))
            current = cyc == self.cycle
            used = asks_roster + (allocated_roster if current else 0)
            cum += intros
            rows.append({
                "cycle": cyc, "current": current, "asks": asks, "allocated": allocated if current else 0,
                "allocated_off_roster": allocated - allocated_roster if current else 0, "used": used, "capacity": cap,
                "capacity_pct": round(used / cap, 3) if cap else None,
                "intros": intros, "intros_cumulative": cum,
            })
        return rows

    def cycles(self) -> dict:
        """The roster's cycle-by-cycle record, summed, for the Live Data tab."""
        names = sorted({o["connector_asked"] for o in self.outcomes} | set(self.roster)
                       | {a["allocated_to"] for a in self.allocation if a["allocated_to"]})
        rows = self.cycle_rows(names)
        cur = rows[-1]
        return {
            "cycle": self.cycle, "rows": rows, "current": cur,
            "roster_capacity": cur["capacity"], "off_roster": sorted(n for n in names if n not in self.roster),
            "intros_total": cur["intros_cumulative"], "asks_total": sum(r["asks"] for r in rows),
            "best": max(rows, key=lambda r: (r["intros"], r["cycle"])),
            "per_connector": [{"connector": n, "rows": self.cycle_rows([n])} for n in self.roster],
        }

    def path_for(self, a: dict) -> dict | None:
        return next((p for p in self.paths.get(a["company_id"], [])
                     if p["connector"] == a["allocated_to"] and p["reach_type"] == a["path_type"]
                     and p["contact_name"] == a["contact_name"]), None)

    # -- 1. stages ------------------------------------------------------------
    def stage_of(self, r: dict) -> str:
        """Point in time: each request sits in exactly one stage; 'closed' is excluded from the strip."""
        return bg.stage_of(r, self.outcome_by_rid.get(r["request_id"]), self.alloc_by_rid.get(r["request_id"]))

    def company_value(self, cid: str) -> tuple[int, str]:
        """One $ per company: CRM ARR potential (golden_companies.value_usd, the max
        across its accounts) when the company has one, else the deal value on its
        most recent request that carries one. Returns (usd, source)."""
        c = self.companies.get(cid, {})
        if c.get("crm_account_ids") and usd(c.get("value_usd")):
            return usd(c["value_usd"]), "crm"
        for r in sorted(self.by_company.get(cid, []), key=lambda r: (r["request_date"], r["request_id"]), reverse=True):
            if usd(r["value_usd"]):
                return usd(r["value_usd"]), "deal"
        return 0, "none"

    def company_stage(self, cid: str) -> str:
        """The furthest stage any of the company's requests has reached: a company
        already won stays won however many fresh asks are open on it. 'closed'
        only when every request is Closed - no path."""
        stages = {self.stage_of(r) for r in self.by_company.get(cid, [])}
        return max((s for s in stages if s != "closed"), key=STAGES.index, default="closed")

    def stages(self) -> dict:
        """Each company counted once, at its furthest stage, at one $ value. A
        request that resolved to no company cannot be tied to a CRM account or to
        its sibling requests, so it stands on its own at its own deal value."""
        count, dollars, unresolved, unresolved_usd, source = Counter(), Counter(), Counter(), Counter(), Counter()
        for cid in self.by_company:
            s = self.company_stage(cid)
            v, src = self.company_value(cid)
            count[s] += 1
            dollars[s] += v
            if s != "closed":
                source[src] += 1
        for r in self.requests:
            if not r["company_id"]:
                s = self.stage_of(r)
                count[s] += 1
                unresolved[s] += 1
                dollars[s] += usd(r["value_usd"])
                unresolved_usd[s] += usd(r["value_usd"])
        return {
            "as_of": self.today.isoformat(),
            "stages": [{"stage": s, "count": count[s], "unresolved": unresolved[s], "usd": dollars[s], "usd_fmt": money(dollars[s])}
                       for s in STAGES],
            "excluded": {"stage": "closed", "count": count["closed"], "unresolved": unresolved["closed"], "usd_fmt": money(dollars["closed"])},
            "total": {"count": sum(count[s] for s in STAGES), "usd_fmt": money(sum(dollars[s] for s in STAGES)),
                      "companies": sum(count[s] - unresolved[s] for s in STAGES),
                      "unresolved": sum(unresolved[s] for s in STAGES),
                      "unresolved_usd_fmt": money(sum(unresolved_usd[s] for s in STAGES))},
            "value_source": {"crm": source["crm"], "deal": source["deal"], "none": source["none"]},
        }

    # -- 2. top priorities ----------------------------------------------------
    def ranked(self) -> list[dict]:
        """Every live not-yet-asked request (golden_allocation.csv) with a connector
        to act on, scored expected value = request priority x connector score and
        sorted best first. Computed once; priorities() and connector_pages() slice it."""
        if self._ranked is not None:
            return self._ranked
        allocated = [a for a in self.allocation if a["allocated_to"]]
        allocated.sort(key=lambda a: (bg.URGENCY_RANK.get(a["urgency_declared"], 9), -usd(a["value_usd"]),
                                      a["request_date"], a["request_id"]))
        order_in_batch: dict[str, int] = {}
        seen = Counter()
        for a in allocated:
            order_in_batch[a["request_id"]] = seen[a["allocated_to"]]
            seen[a["allocated_to"]] += 1

        rows = []
        for a in self.allocation:
            cid = a["company_id"]
            if not cid or a["exception_reason"].startswith(bg.ALREADY_INTRODUCED):
                continue
            if a["allocated_to"]:
                connector, p = a["allocated_to"], self.path_for(a)
                cap = bg.capacity(self.roster, connector)
                budget = bg.cycle_budget(self.roster, self.fatigue, connector)
                capacity_left = max(0, budget - order_in_batch[a["request_id"]]) / cap if cap else 0.0
                capacity_note = f"{max(0, budget - order_in_batch[a['request_id']])} of {cap} slots left when reached"
            elif a["best_path_if_unbudgeted"]:
                connector = a["best_path_if_unbudgeted"].split(" (")[0]
                p = max((x for x in self.paths.get(cid, []) if x["connector"] == connector),
                        key=lambda x: float(x["strength"]), default=None)
                capacity_left, capacity_note = 0.0, "capacity exhausted this cycle"
            else:
                continue
            if p is None:
                continue
            company = self.companies.get(cid, {})
            stage = company.get("stage", "")
            days = (self.today - (parse_date(a["request_date"]) or self.today)).days
            reps = self.live_requesters(cid) or [self.by_rid[a["request_id"]]["requested_by"]]
            comp = {
                "deal_value_musd": usd(a["value_usd"]) / 1e6,
                "stage_weight": STAGE_WEIGHT.get(stage, NO_CRM_WEIGHT) if company.get("crm_account_ids") else NO_CRM_WEIGHT,
                "age": 1 + min(days, AGE_CAP_DAYS) / AGE_CAP_DAYS,
                "reps_waiting": len(reps),
                "path_strength": float(p["strength"]),
                "focus_fit": self.fit(connector, self.industry(cid)),
                "delivery_rate": self.rate(connector),
                "capacity_left": capacity_left,
            }
            request_priority = comp["deal_value_musd"] * comp["stage_weight"] * comp["age"] * comp["reps_waiting"]
            connector_score = comp["path_strength"] * comp["focus_fit"] * comp["delivery_rate"] * comp["capacity_left"]
            rows.append({
                "request_id": a["request_id"],
                **self.company_ref(cid, a["company_name"]),
                "target_title": a["target_title"],
                "requested_by": self.by_rid[a["request_id"]]["requested_by"],
                "connector": connector,
                "path": bg.path_label(p),
                "value_fmt": money(a["value_usd"]),
                "crm_stage": self.crm_stage(cid),
                "days_waiting": days,
                "reps": reps,
                "capacity_note": capacity_note,
                "components": {k: round(v, 3) for k, v in comp.items()},
                "request_priority": round(request_priority, 3),
                "connector_score": round(connector_score, 3),
                "expected_value": round(request_priority * connector_score, 4),
                "allocated": bool(a["allocated_to"]),
                "retry": self.retry_of(cid),
            })
        rows.sort(key=lambda r: (-r["expected_value"], r["request_id"]))
        for i, r in enumerate(rows, 1):
            r["rank"] = i
        self._ranked = rows
        return rows

    def formula(self) -> dict:
        return {
            "expected_value": "expected value = request priority × connector score",
            "request_priority": "request priority = deal value ($M) × stage weight × age × reps waiting",
            "connector_score": "connector score = path strength × focus fit × delivery rate × capacity left",
            "stage_weight": {**STAGE_WEIGHT, "no CRM account": NO_CRM_WEIGHT},
            "age": f"1 + min(days since request, {AGE_CAP_DAYS}) / {AGE_CAP_DAYS}",
            "reps_waiting": "distinct requesters with a live request on the same company",
            "path_strength": "supply_reach.csv strength of the path used",
            "focus_fit": "1.0 in the connector's focus areas, 0.45 outside, 0 if they decline outside, 0.7 when the industry or the connector is unknown",
            "delivery_rate": "intros / asks, shrunk toward the prior (supply_reach.csv delivery_rate)",
            "capacity_left": "share of stated monthly capacity still unspent when the allocator reached this request; 0 when the cycle's slots were gone",
        }

    def priorities(self) -> dict:
        rows = self.ranked()
        return {"top": rows[:TOP_N], "considered": len(rows), "formula": self.formula()}

    # -- 3. current asks ------------------------------------------------------
    def asks(self) -> dict:
        batches: dict[str, list[dict]] = defaultdict(list)
        for a in self.allocation:
            if a["allocated_to"]:
                batches[a["batch_id"]].append(a)

        out = []
        for batch_id, rows in sorted(batches.items()):
            connector = rows[0]["allocated_to"]
            by_co: dict[str, list[dict]] = defaultdict(list)
            for a in rows:
                by_co[a["company_id"]].append(a)
            companies = []
            for cid, group in by_co.items():
                a = group[0]
                p = self.path_for(a)
                industry = self.industry(cid)
                why = [f"best-scoring path with a slot left this cycle: {a['path_type']} via {p['contact_name'] or p['contact_title'] or connector}"
                       f" (strength {float(p['strength']):.2f} × fit {self.fit(connector, industry):.2f} × rate {self.rate(connector):.2f} = {a['route_score']})"]
                if p["in_focus_area"] == "yes":
                    why.append(f"{industry} is in {connector.split()[0]}'s focus areas")
                elif p["in_focus_area"] == "no":
                    why.append(f"{industry or 'industry'} is outside their focus areas")
                if a["best_path_if_unbudgeted"] and not a["best_path_if_unbudgeted"].startswith(connector):
                    why.append(f"stronger path via {a['best_path_if_unbudgeted']} had no slot left")
                companies.append({
                    **self.company_ref(cid, a["company_name"]),
                    "request_ids": [g["request_id"] for g in group],
                    "wanted": self.wanted([self.by_rid[g["request_id"]] for g in group]),
                    "waiting": sorted({self.by_rid[g["request_id"]]["requested_by"] for g in group}),
                    "path_type": a["path_type"],
                    "contact": p["contact_name"] or p["contact_title"],
                    "why": "; ".join(why),
                    "value_usd": sum(usd(g["value_usd"]) for g in group),
                    "value_fmt": money(sum(usd(g["value_usd"]) for g in group)),
                    "urgency": sorted({g["urgency_declared"] for g in group}, key=lambda u: bg.URGENCY_RANK.get(u, 9))[0],
                    "retry": self.retry_of(cid),
                })
            out.append({
                "batch_id": batch_id, "connector": connector, "slug": slug(connector),
                "connector_type": self.connector_facts.get(connector, {}).get("type", ""),
                "size": len(rows), "value_fmt": money(sum(usd(a["value_usd"]) for a in rows)),
                "companies": companies,
            })

        exceptions: dict[str, list[dict]] = defaultdict(list)
        for a in self.allocation:
            if a["exception_reason"]:
                reason, _, detail = a["exception_reason"].partition(": ")
                exceptions[reason].append({
                    "request_id": a["request_id"], **self.company_ref(a["company_id"], a["company_name"]),
                    "detail": detail,
                    "target_title": a["target_title"], "requested_by": self.by_rid[a["request_id"]]["requested_by"],
                    "value_fmt": money(a["value_usd"]), "urgency": a["urgency_declared"],
                    "status": a["status_as_filed"], "best_path": a["best_path_if_unbudgeted"],
                    "crm_stage": self.crm_stage(a["company_id"]) if a["company_id"] else "",
                    "sector_cover": self.sector_cover(a["company_id"]) if a["company_id"] else None,
                    "company_as_written": self.by_rid[a["request_id"]]["company_as_written"],
                })
        n_exc = sum(len(v) for v in exceptions.values())
        # every allocated company across all batches, biggest first: the Aggregate tab
        everything = sorted(({**c, "connector": b["connector"], "slug": b["slug"], "batch_id": b["batch_id"]}
                             for b in out for c in b["companies"]),
                            key=lambda c: (-c["value_usd"], c["company_name"]))
        return {
            "cycle": self.cycle, "allocated": sum(b["size"] for b in out), "batches": out,
            "all": everything, "value_fmt": money(sum(c["value_usd"] for c in everything)),
            "exceptions": [{"reason": k, "count": len(v), "value_fmt": money(sum(usd(self.by_rid[r["request_id"]]["value_usd"]) for r in v)),
                            "rows": v} for k, v in sorted(exceptions.items(), key=lambda kv: -len(kv[1]))],
            "exception_count": n_exc,
        }

    # -- 3b. already introduced: extend the intro, don't ask afresh -------------
    def introduced(self) -> dict:
        """Live requests the allocator parked because the company already has a live
        intro (build_golden.ALREADY_INTRODUCED: a meeting booked, or sent within
        INTRO_LIVE_DAYS). One row per company; the action is the rep who received
        that intro asking their contact for the other names, not a connector ask.
        `retries` are the companies whose last intro fizzled and are back in the
        queue this cycle, labelled so the ask reads as a second attempt."""
        by_co: dict[str, list[dict]] = defaultdict(list)
        for a in self.allocation:
            if a["company_id"] and a["exception_reason"].startswith(bg.ALREADY_INTRODUCED):
                by_co[a["company_id"]].append(a)
        rows = []
        for cid, group in by_co.items():
            intro = self.prior_intro(cid)
            who = intro["requested_by"] or "the rep introduced"
            wanted = self.wanted([self.by_rid[g["request_id"]] for g in group])
            rows.append({
                **self.company_ref(cid, group[0]["company_name"]),
                "request_ids": sorted(g["request_id"] for g in group),
                "wanted": wanted,
                "waiting": sorted({self.by_rid[g["request_id"]]["requested_by"] for g in group}),
                "value_usd": sum(usd(g["value_usd"]) for g in group),
                "value_fmt": money(sum(usd(g["value_usd"]) for g in group)),
                "urgency": sorted({g["urgency_declared"] for g in group}, key=lambda u: bg.URGENCY_RANK.get(u, 9))[0],
                "crm_stage": self.crm_stage(cid),
                "intro": intro,
                "owner": intro["requested_by"],
                "action": f"{who.split()[0]} asks the {intro['target_title'] or 'contact'} {intro['connector'].split()[0]} introduced"
                          f" {'(meeting booked) ' if intro['meeting_booked'] else ''}for {', '.join(wanted)}",
                "best_path": group[0]["best_path_if_unbudgeted"],
            })
        rows.sort(key=lambda r: (-r["value_usd"], r["company_name"]))

        retries = []
        seen: set[str] = set()
        for a in self.allocation:
            cid = a["company_id"]
            if not a["allocated_to"] or cid in seen or not self.retry_of(cid):
                continue
            seen.add(cid)
            group = [g for g in self.allocation if g["company_id"] == cid and g["allocated_to"]]
            retries.append({
                **self.company_ref(cid, a["company_name"]),
                "request_ids": sorted(g["request_id"] for g in group),
                "wanted": self.wanted([self.by_rid[g["request_id"]] for g in group]),
                "connectors": sorted({g["allocated_to"] for g in group}),
                "value_usd": sum(usd(g["value_usd"]) for g in group),
                "value_fmt": money(sum(usd(g["value_usd"]) for g in group)),
                "retry": self.retry_of(cid),
            })
        retries.sort(key=lambda r: (-r["value_usd"], r["company_name"]))
        return {
            "days": bg.INTRO_LIVE_DAYS, "rows": rows, "count": len(rows),
            "requests": sum(len(r["request_ids"]) for r in rows),
            "value_fmt": money(sum(r["value_usd"] for r in rows)),
            "retries": retries, "retry_requests": sum(len(r["request_ids"]) for r in retries),
        }

    # -- 4. already offered, needs response -----------------------------------
    def offer_gaps(self) -> dict:
        rows = []
        for r in self.requests:
            rid = r["request_id"]
            if r["offer_in_thread"] != "Y" or rid in self.outcome_by_rid:
                continue
            th = self.threads.get(rid, {"offers": []})
            rows.append({
                "request_id": rid, **self.company_ref(r["company_id"], r["company_as_written"]),
                "target_title": r["target_title"], "requested_by": r["requested_by"],
                "value_usd": usd(r["value_usd"]), "value_fmt": money(r["value_usd"]),
                "status": r["status_as_filed"], "routed_to": r["routed_to"],
                "offers": [{"who": m["user"], "text": m["text"], "date": m["ts"][:10],
                            "on_roster": m["user"] in self.roster,
                            "days_ago": (self.today - (parse_date(m["ts"]) or self.today)).days} for m in th["offers"]],
                "note": ("filed as Closed - no path with an offer sitting in the thread" if r["status_as_filed"] == "Closed - no path"
                         else "filed as Intro sent but no ask or intro was ever logged" if r["status_as_filed"] == "Intro sent"
                         else f"routed to {r['routed_to']} on paper, never asked" if r["routed_to"] else "open, nobody asked"),
            })
        rows.sort(key=lambda r: -r["value_usd"])
        return {"rows": rows, "count": len(rows), "value_fmt": money(sum(r["value_usd"] for r in rows))}

    # -- 5. core bottlenecks --------------------------------------------------
    def bottlenecks(self) -> dict:
        """Asks the connector agreed to and never delivered. One nudged in the last
        NUDGE_QUIET_DAYS (golden_requests.nudged_on, from completions.csv) is
        listed under `nudged` instead and comes back when the quiet period ends."""
        rows, nudged = [], []
        for o in self.outcomes:
            if o["responded"] != "Y" or o["intro_sent"] == "Y":
                continue
            r = self.by_rid.get(o["request_id"], {})
            agreed = parse_date(o["response_date"]) or parse_date(o["asked_date"]) or self.today
            last_nudge = parse_date(r.get("nudged_on", ""))
            row = {
                "request_id": o["request_id"], **self.company_ref(r.get("company_id", ""), r.get("company_as_written", "")),
                "connector": o["connector_asked"], "on_roster": o["connector_asked"] in self.roster,
                "target_title": r.get("target_title", ""), "requested_by": r.get("requested_by", ""),
                "asked_date": o["asked_date"], "agreed_date": o["response_date"],
                "days_since_agreed": (self.today - agreed).days,
                "value_fmt": money(r.get("value_usd", "")), "value_usd": usd(r.get("value_usd", "")),
                "status": r.get("status_as_filed", ""), "action": "nudge",
                "nudged_on": r.get("nudged_on", ""),
                "days_since_nudged": (self.today - last_nudge).days if last_nudge else None,
            }
            (nudged if last_nudge and 0 <= (self.today - last_nudge).days < NUDGE_QUIET_DAYS else rows).append(row)
        rows.sort(key=lambda r: -r["days_since_agreed"])
        nudged.sort(key=lambda r: (r["nudged_on"], r["request_id"]))
        by_connector = Counter(r["connector"] for r in rows)
        return {"rows": rows, "count": len(rows), "value_fmt": money(sum(r["value_usd"] for r in rows)),
                "nudged": nudged, "quiet_days": NUDGE_QUIET_DAYS,
                "by_connector": [{"connector": k, "count": n, "on_roster": k in self.roster,
                                  "value_fmt": money(sum(r["value_usd"] for r in rows if r["connector"] == k))}
                                 for k, n in by_connector.most_common()]}

    # -- 6. per-connector -----------------------------------------------------
    def connector_card(self, name: str) -> dict:
        """One connector's facts: capacity used against stated, delivery rate, what
        they are sitting on, their queue this cycle. Works for people off the roster
        too (no stated capacity, no focus list)."""
        r = self.roster.get(name)
        cap = int(r["stated_monthly_capacity"] or 0) if r else 0
        asked_cycle = self.asks_this_cycle(name)
        queue = [a for a in self.allocation if a["allocated_to"] == name]
        sitting = [o for o in self.outcomes if o["connector_asked"] == name and o["intro_sent"] != "Y"
                   and self.by_rid.get(o["request_id"], {}).get("status_as_filed") in bg.OPEN_STATUSES]

        def sitting_row(o: dict) -> dict:
            """An ask with no intro yet: `nudge` it if they replied, `chase` if they
            never did. One followed up in the last NUDGE_QUIET_DAYS (nudged_on, from
            completions.csv) is `quiet`: listed, not actionable, until the period ends."""
            r = self.by_rid.get(o["request_id"], {})
            last = parse_date(r.get("nudged_on", ""))
            since = (self.today - last).days if last else None
            return {
                "request_id": o["request_id"], **self.company_ref(r.get("company_id", "")),
                "target_title": r.get("target_title", ""), "requested_by": r.get("requested_by", ""),
                "connector": name, "asked_date": o["asked_date"], "responded": o["responded"] == "Y",
                "days_since_asked": (self.today - (parse_date(o["asked_date"]) or self.today)).days,
                "value_fmt": money(r.get("value_usd", "")),
                "action": "nudge" if o["responded"] == "Y" else "chase",
                "nudged_on": r.get("nudged_on", ""), "days_since_nudged": since,
                "quiet": since is not None and 0 <= since < NUDGE_QUIET_DAYS,
            }
        asks = [o for o in self.outcomes if o["connector_asked"] == name]
        intros = [o for o in asks if o["intro_sent"] == "Y"]
        cycles = self.cycle_rows([name])
        facts = self.connector_facts.get(name, {})
        return {
            "connector": name, "slug": slug(name), "page": CONNECTOR_PAGE.format(slug=slug(name)),
            "on_roster": r is not None,
            "role": r["role"] if r else "", "type": r["type"] if r else facts.get("type", "not on roster"),
            "focus": sorted(r["focus"]) if r else [],
            "hard_decline": r["hard_decline"] if r else False, "notes": r["notes"] if r else "",
            "capacity": cap, "asked_this_cycle": asked_cycle, "allocated_this_cycle": len(queue),
            "used": asked_cycle + len(queue), "idle": max(0, cap - asked_cycle - len(queue)),
            "delivery_rate": round(self.rate(name), 3), "asks_all_time": len(asks), "intros_all_time": len(intros),
            "intros_this_cycle": cycles[-1]["intros"], "cycles": cycles,
            "batch_ask": self.batch_ask(name),
            # actionable rows first (oldest ask first), then the ones followed up recently
            "sitting_on": sorted((sitting_row(o) for o in sitting), key=lambda s: (s["quiet"], s["asked_date"], s["request_id"])),
            "quiet_days": NUDGE_QUIET_DAYS,
            "queue": [{
                "request_id": a["request_id"], **self.company_ref(a["company_id"], a["company_name"]),
                "target_title": a["target_title"], "requested_by": self.by_rid[a["request_id"]]["requested_by"],
                "path_type": a["path_type"], "contact": a["contact_name"], "route_score": a["route_score"],
                "value_fmt": money(a["value_usd"]), "urgency": a["urgency_declared"],
                "retry": self.retry_of(a["company_id"]),
            } for a in queue],
        }

    def strongest_elsewhere(self, name: str) -> list[dict]:
        """Read-only: companies where this connector holds the strongest raw path
        in supply_reach.csv yet none of the company's live requests routed to
        them this cycle. Nothing here was asked of them (that is `sitting_on`,
        from intro_outcomes.csv), so there is nothing to tick; it says where a
        volunteered or strong path went unused and why: capacity, or a focus
        area they decline outside of."""
        cap = bg.capacity(self.roster, name)
        used = cap - self.connector_facts.get(name, {}).get("idle", cap)
        live: dict[str, list[dict]] = defaultdict(list)
        for a in self.allocation:
            live[a["company_id"]].append(a)
        out = []
        for cid, rows in live.items():
            paths = [p for p in self.paths.get(cid, []) if p["reach_type"] != "none"]
            if not paths:
                continue
            top = max(paths, key=lambda p: float(p["strength"]))
            if top["connector"] != name or any(a["allocated_to"] == name for a in rows):
                continue
            fit = self.fit(name, self.industry(cid))
            out.append({
                **self.company_ref(cid, top["company_name"]), "reach_type": top["reach_type"],
                "strength": round(float(top["strength"]), 3), "route_score": round(float(top["strength"]) * fit * self.rate(name), 3),
                "outside_focus": fit <= 0, "industry": self.industry(cid), "used": used, "capacity": cap,
                "requests": sorted(a["request_id"] for a in rows),
                "routed_to": sorted({a["allocated_to"] for a in rows if a["allocated_to"]}),
                "unrouted": sum(1 for a in rows if not a["allocated_to"]),
            })
        return sorted(out, key=lambda x: (-x["strength"], x["company_name"]))

    def batch_ask(self, name: str) -> dict | None:
        """The connector's drafted message for the current cycle, or None when
        nothing routes to them."""
        return next((m for m in self.batch_asks if m["cycle"] == self.cycle and m["connector"] == name), None)

    def batch_page(self) -> dict:
        """The Batched-Ask tab: every drafted message, current cycle first, each
        with the structured rows the message itself may not spell out."""
        order = self.connector_names()
        rank = {n: i for i, n in enumerate(order)}
        messages = sorted(self.batch_asks, key=lambda m: (m["cycle"] != self.cycle, m["cycle"], rank.get(m["connector"], len(rank)), m["connector"]))
        pages = {c["connector"]: c["page"] for c in self.connector_pages()}
        return {
            "as_of": self.today.isoformat(), "cycle": self.cycle, "trace_page": TRACE_PAGE,
            "messages": [{**m, "page": pages.get(m["connector"], ""),
                          "requests": [{**q, **self.company_ref(q["company_id"], q["company_name"]), "value_fmt": money(q["value_usd"])}
                                       for q in m["requests"]]} for m in messages],
            "templates": batch_ask.TEMPLATES.relative_to(ROOT).as_posix(),
        }

    def connector_names(self) -> list[str]:
        """Roster first, in roster order; then anyone off the roster who holds an
        allocation this cycle, largest batch first."""
        extra = Counter()
        for a in self.allocation:
            if a["allocated_to"] and a["allocated_to"] not in self.roster:
                extra[a["allocated_to"]] += usd(a["value_usd"])
        return list(self.roster) + [n for n, _ in sorted(extra.items(), key=lambda kv: (-kv[1], kv[0]))]

    def connectors(self) -> list[dict]:
        return [self.connector_card(name) for name in self.roster]

    def connector_pages(self) -> list[dict]:
        """One page per connector: their top 5 by expected value, then the rest of
        their ranked list, what they are already sitting on, and (read-only) the
        companies where their path is the strongest but did not route to them."""
        out = []
        for name in self.connector_names():
            mine = [dict(r, rank_here=i) for i, r in enumerate((r for r in self.ranked() if r["connector"] == name), 1)]
            out.append({
                **self.connector_card(name),
                "top": mine[:TOP_N], "rest": mine[TOP_N:], "ranked_count": len(mine),
                "ranked_value_fmt": money(sum(usd(self.by_rid[r["request_id"]]["value_usd"]) for r in mine)),
                "no_slot": sum(1 for r in mine if not r["allocated"]),
                "strongest_elsewhere": self.strongest_elsewhere(name),
                "formula": self.formula(), "completions": self.completion_export(), "as_of": self.today.isoformat(),
            })
        return out

    # -- 7. overdue a check-in ------------------------------------------------
    def owned_elsewhere(self) -> dict[str, str]:
        """company_id -> the first section, in page order, that already holds an
        action on the company: an ask to send (Top priorities, Current asks), an
        offer to answer, a nudge, a connector's follow-up, an unrouted ask to
        place, a CRM fix. A company in none of them is this section's alone."""
        listed = {
            "top": [r["company_id"] for r in self.priorities()["top"]],
            "asks": [c["company_id"] for b in self.asks()["batches"] for c in b["companies"]],
            "introduced": [r["company_id"] for r in self.introduced()["rows"]],
            "offers": [r["company_id"] for r in self.offer_gaps()["rows"]],
            "bottlenecks": [r["company_id"] for r in self.bottlenecks()["rows"]],
            "connectors": [s["company_id"] for c in self.connectors() for s in c["sitting_on"]],
            "unrouted": [x["company_id"] for c in self.unrouted()["per_connector"] for x in c["companies"]],
            "crm": [r["company_id"] for g in self.crm()["groups"] for r in g["rows"]],
        }
        out: dict[str, str] = {}
        for section, _ in SECTIONS:
            for cid in listed.get(section, []):
                if cid:
                    out.setdefault(cid, section)
        return out

    def checkins(self) -> dict:
        """Companies with live requests and a CRM account nobody has touched (CRM
        last_touch_date) in CHECKIN_DAYS; `both` of them have had no connector asked
        about them in that window either. Every row already listed in another
        section carries `owned_by`, the section that owns the action on it; the rows
        nothing else owns sort first, so the page's sections stay mutually exclusive."""
        titles = dict(SECTIONS)
        owned = self.owned_elsewhere()
        rows = []
        for cid, c in self.companies.items():
            accts = [self.accounts[a] for a in bar(c["crm_account_ids"]) if a in self.accounts]
            live = [r for r in self.by_company.get(cid, []) if r["status_as_filed"] in bg.OPEN_STATUSES]
            if not accts or not live:
                continue
            touch = max((parse_date(a["last_touch_date"]) for a in accts if a["last_touch_date"]), default=None)
            asks = [parse_date(self.outcome_by_rid[r["request_id"]]["asked_date"]) for r in self.by_company.get(cid, [])
                    if r["request_id"] in self.outcome_by_rid]
            last_ask = max((d for d in asks if d), default=None)
            touch_days = (self.today - touch).days if touch else None
            ask_days = (self.today - last_ask).days if last_ask else None
            if touch_days is not None and touch_days <= CHECKIN_DAYS:
                continue
            ask_failed = ask_days is None or ask_days > CHECKIN_DAYS
            rows.append({
                **self.company_ref(cid), "owner": c["owner"], "stage": c["stage"],
                "last_touch_date": touch.isoformat() if touch else "", "touch_days": touch_days,
                "last_ask_date": last_ask.isoformat() if last_ask else "", "ask_days": ask_days,
                "failed": ["CRM touch", "intro ask"] if ask_failed else ["CRM touch"],
                "live_requests": len(live), "live_value_fmt": money(sum(usd(r["value_usd"]) for r in live)),
                "live_value_usd": sum(usd(r["value_usd"]) for r in live),
                "owned_by": owned.get(cid, ""), "owned_by_title": titles.get(owned.get(cid, ""), ""),
            })
        rows.sort(key=lambda r: (bool(r["owned_by"]), -len(r["failed"]), -r["live_value_usd"], r["company_name"]))
        return {"days": CHECKIN_DAYS, "rows": rows, "count": len(rows),
                "both": sum(1 for r in rows if len(r["failed"]) == 2),
                "unique": sum(1 for r in rows if not r["owned_by"]),
                "owned": sum(1 for r in rows if r["owned_by"])}

    # -- 8. unrouted company asks, per connector -------------------------------
    def unrouted(self) -> dict:
        asks_in, asks_out, intros_in, intros_out = 0, 0, 0, 0
        for o in self.outcomes:
            r = self.roster.get(o["connector_asked"])
            ind = self.industry(self.by_rid.get(o["request_id"], {}).get("company_id", ""))
            if r and ind and ind in r["focus"]:
                asks_in += 1
                intros_in += o["intro_sent"] == "Y"
            else:
                asks_out += 1
                intros_out += o["intro_sent"] == "Y"

        unrouted = [a for a in self.allocation if a["exception_reason"] and a["company_id"]
                    and not a["exception_reason"].startswith(bg.ALREADY_INTRODUCED)]
        per = []
        for name, r in self.roster.items():
            by_co: dict[str, list[dict]] = defaultdict(list)
            for a in unrouted:
                if self.industry(a["company_id"]) in r["focus"]:
                    by_co[a["company_id"]].append(a)
            companies = []
            for cid, group in by_co.items():
                own = [p for p in self.paths.get(cid, []) if p["connector"] == name]
                companies.append({
                    **self.company_ref(cid), "industry": self.industry(cid),
                    "request_ids": [g["request_id"] for g in group],
                    "reasons": sorted({g["exception_reason"] for g in group}),
                    "wanted": self.wanted([self.by_rid[g["request_id"]] for g in group]),
                    "waiting": sorted({self.by_rid[g["request_id"]]["requested_by"] for g in group}),
                    "value_usd": sum(usd(g["value_usd"]) for g in group),
                    "value_fmt": money(sum(usd(g["value_usd"]) for g in group)),
                    "has_path": bool(own),
                    "path": bg.path_label(max(own, key=lambda p: float(p["strength"]))) if own else "no known path; ask them if they know anyone",
                })
            companies.sort(key=lambda c: (not c["has_path"], -c["value_usd"]))
            per.append({"connector": name, "page": CONNECTOR_PAGE.format(slug=slug(name)), "focus": sorted(r["focus"]),
                        "idle": self.connector_facts.get(name, {}).get("idle", 0),
                        "companies": companies, "count": len(companies),
                        "value_fmt": money(sum(c["value_usd"] for c in companies))})
        return {
            "finding": {
                "in_focus_asks": asks_in, "out_focus_asks": asks_out, "total_asks": asks_in + asks_out,
                "in_focus_rate": round(intros_in / asks_in, 2) if asks_in else 0,
                "out_focus_rate": round(intros_out / asks_out, 2) if asks_out else 0,
                "in_focus_pct": f"{round(100 * intros_in / asks_in) if asks_in else 0}%",
                "out_focus_pct": f"{round(100 * intros_out / asks_out) if asks_out else 0}%",
            },
            "unrouted_companies": len({a["company_id"] for a in unrouted}),
            "per_connector": per,
        }

    # -- 9. what the CRM is missing --------------------------------------------
    def crm(self) -> dict:
        w = wb.Writeback(self.today)
        review = w.review_rows()
        imports = w.import_rows()

        def rows(group: str) -> list[dict]:
            return [{**asdict(r), "value_fmt": money(r.value_at_stake_usd), "href": self.company_ref(r.company_id)["href"],
                     "request_ids": bar(r.request_ids)} for r in review if r.group == group]

        groups = [{"group": g, "title": wb.GROUP_TITLES[g], "rows": rows(g), "count": len(rows(g)),
                   "value_fmt": money(sum(r["value_at_stake_usd"] for r in rows(g)))}
                  for g in (wb.CREATE, wb.MERGE, wb.OWNERS, wb.REOPEN)]
        return {
            "groups": groups,
            "import": {"filename": wb.IMPORT_OUT.name, "columns": wb.IMPORT_COLUMNS, "count": len(imports),
                       "csv": csv_text(wb.IMPORT_COLUMNS, imports)},
            "review": {"filename": wb.REVIEW_OUT.name, "columns": wb.REVIEW_COLUMNS, "count": len(review),
                       "csv": csv_text(wb.REVIEW_COLUMNS, [asdict(r) for r in review]),
                       "groups": [{"group": g, "count": sum(1 for r in review if r.group == g)} for g in wb.GROUPS]},
            "status": wb.STATUS,
        }

    # -- 9b. what Submit writes ---------------------------------------------------
    def completion_export(self) -> dict:
        """Everything the browser needs to post completions: the Supabase REST
        endpoint and the anon (publishable) key, the row columns, the action per
        section, and the completion_ids already on file. Only SUPABASE_URL and
        SUPABASE_ANON_KEY are read; the service key is never in the payload."""
        bg.load_env()
        url = os.environ.get("SUPABASE_URL", "").strip()
        return {
            "supabase_url": bg.supabase_rest(url) if url else "",
            "anon_key": os.environ.get("SUPABASE_ANON_KEY", "").strip(),
            "table": bg.SUPABASE_TABLE, "columns": bg.COMPLETION_COLUMNS,
            "actions": {"top": bg.ASKED, "bottlenecks": bg.NUDGED, "nudge": bg.NUDGED, "chase": bg.CHASED},
            "ids": sorted(c["completion_id"] for c in self.completions), "count": len(self.completions),
            "quiet_days": NUDGE_QUIET_DAYS,
            "stamp": BUILD_STAMP.name, "repo_url": repo_url(), "workflow": WORKFLOW_FILE,
            "path": bg.COMPLETIONS_OUT.relative_to(bg.ROOT).as_posix(),
        }

    # -- 10. upload preview rules ----------------------------------------------
    def parser(self) -> dict:
        """The build's parser, as data. The browser applies these tables with the
        same layer order as golden/parse.py + golden/resolver.py; a test runs
        the JavaScript under node against the Python on every thread."""
        res = load_resolver()
        ents = {e.entity_id: {"id": e.entity_id, "name": e.name, "kind": e.kind, "domain": e.domain, "names": e.names}
                for e in res.entities}
        strict = defaultdict(list)
        loose = defaultdict(list)
        for e in res.entities:
            for n in e.names:
                strict[gr.normalize_strict(n)].append(e.entity_id)
                loose[gr.normalize(n)].append(e.entity_id)
            if e.domain:
                strict[gr.domain_stem(e.domain)].append(e.entity_id)
        known_no_crm = {}
        for cid, c in self.companies.items():
            if c["crm_account_ids"]:
                continue
            for n in [c["company_name"], *bar(c["also_known_as"])]:
                known_no_crm.setdefault(gr.normalize_strict(n), cid)
                known_no_crm.setdefault(gr.normalize(n), cid)

        # fund-or-customer collisions: a stem (8+ chars) that is a prefix of both a fund's
        # and a customer's name — "Thornbury" for Thornbury Financial + Thornbury Equity.
        # The resolver refuses these; the panel shows both candidates.
        keys = {k: set(v) for k, v in loose.items()}
        for e in res.entities:
            if e.domain:
                keys.setdefault(gr.domain_stem(e.domain), set()).add(e.entity_id)
        collisions = defaultdict(set)
        for a, ids_a in keys.items():
            for b, ids_b in keys.items():
                if a >= b or {ents[i]["kind"] for i in ids_a | ids_b} != {"company", "fund"}:
                    continue
                stem = commonprefix([a, b])
                if len(stem) >= gr.MIN_PREFIX_STEM:
                    collisions[stem] |= ids_a | ids_b
        # only stems the resolver really refuses: "blackwood" is a customer's whole name, so it resolves
        collisions = {k: sorted(v) for k, v in collisions.items() if res.resolve(k).method == "fund-or-customer"}

        askable = sorted(set(self.rates))
        companies = {}
        for cid, c in self.companies.items():
            ind = c["industry"]
            paths = self.ranked_paths(cid)
            best = paths[0] if paths else None
            acct = next((self.accounts[a] for a in bar(c["crm_account_ids"]) if a in self.accounts), None)
            companies[cid] = {
                **self.company_ref(cid), "industry": ind, "stage": c["stage"], "crm": bool(c["crm_account_ids"]),
                "owner": c["owner"], "arr_fmt": money(usd(acct["arr_potential_usd"])) if acct else "",
                "paths": paths, "priority": self.route_priority(cid),
                "best": {"connector": best["connector"], "reach_type": best["reach_type"], "contact": best["contact"],
                         "score": best["score"], "label": best["label"]} if best else None,
                "offer_score": {n: round(bg.PATH_BASE["offer"] * self.fit(n, ind) * self.rate(n), 3) for n in askable},
                "offer_score_unknown": round(bg.PATH_BASE["offer"] * 0.7 * bg.PRIOR_RATE, 3),
            }
        return {
            "cues": [{"label": label, **js_regex(pat), "score": score} for label, pat, score in gp._CUES],
            "split": js_regex(gp._SPLIT), "domain": js_regex(gp._DOMAIN), "title": js_regex(gp.TITLE_RE),
            "domain_cue": gp.DOMAIN_CUE, "domain_score": gp.DOMAIN_SCORE,
            "known": js_regex(res.names_regex()), "known_cue": gp.KNOWN_CUE, "known_score": gp.KNOWN_SCORE,
            "offer": js_regex(bg.OFFER_RE), "noise": js_regex(bg.NOISE_RE),
            "offer_title": js_regex(bg._OFFER_TITLE_RE), "offer_person": js_regex(bg._OFFER_PERSON_RE),
            "resolver": {
                "entities": ents, "strict": dict(strict), "loose": dict(loose),
                "stem": {gr.domain_stem(e.domain): e.entity_id for e in res.entities if e.domain},
                "by_domain": {e.domain: e.entity_id for e in res.entities if e.domain},
                "noise": {"source": gr._NOISE, "flags": "g"},
                "min_prefix_stem": gr.MIN_PREFIX_STEM, "confidence": gr.CONFIDENCE, "review_threshold": gr.REVIEW_THRESHOLD,
                "fund_or_customer": collisions,
            },
            "route_presets": ROUTE_PRESETS,
            "known_no_crm": known_no_crm,
            # an offer on a company the build has never seen: no industry, so fit is 0.7 for everyone
            "offer_score_no_industry": {n: round(bg.PATH_BASE["offer"] * 0.7 * self.rate(n), 3) for n in askable},
            "offer_score_unknown": round(bg.PATH_BASE["offer"] * 0.7 * bg.PRIOR_RATE, 3),
            "filed": {r["request_id"]: {**self.company_ref(r["company_id"], r["company_as_written"]), "status": r["status_as_filed"],
                                        "asked": r["request_id"] in self.outcome_by_rid} for r in self.requests},
            "companies": companies,
            "connectors": {n: {"connector": n, "on_roster": n in self.roster,
                               "type": self.roster[n]["type"] if n in self.roster else "not on roster",
                               "capacity": bg.capacity(self.roster, n),
                               "idle": self.connector_facts.get(n, {}).get("idle", bg.capacity(self.roster, n)),
                               "rate": round(self.rate(n), 3)} for n in askable},
            "command": THREADS_COMMAND,
            "preview_columns": ["request_id", "posted", "requested_by", "company_as_written", "company_id", "company_name",
                                "resolved_by", "offer_by", "offer_text", "route_to", "path", "needs_human", "raw_ask"],
        }

    # -- everything ---------------------------------------------------------------
    def payload(self) -> dict:
        return {
            "as_of": self.today.isoformat(), "cycle": self.cycle, "trace_page": TRACE_PAGE, "batch_page": BATCH_PAGE,
            "bands": [{"id": bid, "title": title, "test": test, "sections": [sid for sid, _ in sections]}
                      for bid, title, test, sections in BANDS],
            "stages": self.stages(), "priorities": self.priorities(), "asks": self.asks(), "introduced": self.introduced(),
            "offer_gaps": self.offer_gaps(), "bottlenecks": self.bottlenecks(), "connectors": self.connectors(),
            "checkins": self.checkins(), "unrouted": self.unrouted(), "crm": self.crm(), "parser": self.parser(),
            "completions": self.completion_export(),
            "connector_pages": [{"connector": c["connector"], "page": c["page"], "on_roster": c["on_roster"]}
                                for c in self.connector_pages()],
        }


def payload(today: date | None = None) -> dict:
    return Live(today or date.today()).payload()


def _fragment(data: dict, entry: str) -> str:
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    js = (DASHBOARD / "live_priorities.js").read_text(encoding="utf-8")
    return f"""
<div id="lp"></div>
<script id="lp-data" type="application/json">{blob}</script>
<script>
{js}
LP.{entry}(JSON.parse(document.getElementById('lp-data').textContent), document.getElementById('lp'));
</script>
"""


def fragment(today: date | None = None) -> str:
    return _fragment(payload(today), "boot")


def cycles(today: date | None = None) -> dict:
    return Live(today or date.today()).cycles()


def connector_fragments(today: date | None = None) -> list[tuple[dict, str]]:
    """(card, html) per connector page; card["page"] is the file name under docs/."""
    return [(c, _fragment(c, "bootConnector")) for c in Live(today or date.today()).connector_pages()]


def batch_fragment(today: date | None = None) -> str:
    return _fragment(Live(today or date.today()).batch_page(), "bootBatch")


if __name__ == "__main__":
    p = payload()
    print(f"as of {p['as_of']}, cycle {p['cycle']}")
    print("stages     ", ", ".join(f"{s['stage']} {s['count']} ({s['usd_fmt']})" for s in p["stages"]["stages"]))
    print("top 5      ", ", ".join(f"{r['request_id']} {r['company_name']} -> {r['connector']} EV {r['expected_value']}" for r in p["priorities"]["top"]))
    print(f"asks        {p['asks']['allocated']} allocated in {len(p['asks']['batches'])} batches; "
          + ", ".join(f"{e['count']} {e['reason']}" for e in p["asks"]["exceptions"]))
    print(f"offer gaps  {p['offer_gaps']['count']} ({p['offer_gaps']['value_fmt']}): "
          + ", ".join(r["request_id"] for r in p["offer_gaps"]["rows"]))
    print(f"bottlenecks {p['bottlenecks']['count']} nudges" + (f", {len(p['bottlenecks']['nudged'])} nudged recently" if p['bottlenecks']['nudged'] else ""))
    print(f"completions {p['completions']['count']} on file")
    print(f"check-ins   {p['checkins']['count']} overdue ({p['checkins']['both']} failed both, {p['checkins']['unique']} owned by no other section)")
    print("unrouted   ", ", ".join(f"{c['connector'].split()[0]} {c['count']}" for c in p["unrouted"]["per_connector"]))
    print("crm        ", ", ".join(f"{g['count']} {g['group']}" for g in p["crm"]["groups"]))
