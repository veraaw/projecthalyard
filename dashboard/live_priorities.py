"""The "Live Priorities" tab, docs/livepriorities.html (built by dashboard/build_dashboard.py).

    from dashboard.live_priorities import fragment, payload
    data = payload()           # every section as plain dicts/lists: the browser only renders this
    html = fragment()          # <div> with the JSON payload embedded + dashboard/live_priorities.js

Everything on the tab is computed here, from golden/ (including golden/current/,
dataset/ with the accepted uploads applied), and written into one JSON payload;
the JavaScript renders it and never derives a number. Three things the page
does with user input. The intake preview: the parser
rules (golden/parse.py cues, golden/build_golden.py OFFER_RE, and the
golden/resolver.py lookup tables) are exported into the payload and applied
verbatim by the browser, so a pasted message or a dropped .jsonl previews
exactly what `python3 golden/build_golden.py --threads FILE` would file. And
Submit: the tick-boxes on Top Priorities (an ask sent), Follow-Ups Owed and
the connector pages' "already sitting on" (a nudge or a chase sent) are posted,
one row each, to the Supabase
`completions` table with the anon key (insert-only; the
URL and key come from SUPABASE_URL / SUPABASE_ANON_KEY at build time, never
from this file). The scheduled rebuild (.github/workflows/rebuild.yml) pulls
the table into golden/completions.csv, a fact source of the build, and the
ticked items leave the queue. docs/build_stamp.json says when that last
happened; the page shows it. And "Intake: Add More Live Data": a CSV of any
dataset/ file, or a Slack export, dropped on the page is diffed in the browser
against the file as it stands (the payload carries every file of
golden/current/) with golden/intake.py's merge rules ported to JavaScript; the
summary (new rows, new columns, every value it would override) is shown, and
Accept posts the file to the Supabase `intake_uploads` table. The rebuild pulls
it into intake/ and every reader sees the new data. dataset/ is never written.

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
from dashboard import company_value as cv
from dashboard import request_state as rs
from golden import build_golden as bg
from golden import intake
from golden import parse as gp
from golden import resolver as gr
from golden.clock import as_of
from golden.resolve_cli import load_resolver
from paths import CURRENT, DASHBOARD, DOCS, GOLDEN, ROOT

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
NETWORK_PATHS_SHOWN = 20  # paths exported per network-only company (they can have hundreds; the panel ranks the best)
AGE_CAP_DAYS = 365     # age factor = 1 + min(days waiting, cap) / cap  (1.0 .. 2.0)
TOP_N = 5
NUDGE_QUIET_DAYS = 14  # a bottleneck nudged this recently is off the list until the quiet period passes
BUILD_STAMP = DOCS / "build_stamp.json"  # when the site was last generated; the page shows it
WORKFLOW_FILE = "rebuild.yml"  # .github/workflows/, the scheduled rebuild the page reports the last run of

PAGE = "livepriorities.html"
BATCH_PAGE = "batchask.html"
TRACE_PAGE = "companytrace.html"
CONNECTOR_PAGE = "connector-{slug}.html"
# the page reads top to bottom in five bands: (id, title, sections). Each band's sections are
# (section id, nav label) as rendered by live_priorities.js boot(), in page order.
BANDS = [
    ("intake", "Intake: Preview a Routed Request Summary",
     [("route", "Route a Request")]),
    ("upload", "Intake: Add More Live Data",
     [("upload", "Add Live Data")]),
    ("orientation", "Orientation: Deal Value by Stage",
     [("stages", "Deal Value by Stage")]),
    ("now", "Actionable Routing Steps",
     [("top", "Top Priorities")]),
    ("cycle", "Current Cycle Overview",
     [("connectors", "This Cycle, by Connector"), ("introduced", "Already Introduced"),
      ("exceptions", "Unrouted Exceptions"), ("followups", "Follow-Ups Owed")]),
    ("other", "Other",
     [("crm", "CRM Updates")]),
]
# every section in page order; drives the header nav
SECTIONS = [s for _, _, sections in BANDS for s in sections]
# the states an open request can be in, in flight order: (key, group, label, what happens next,
# the section of this tab that owns it). Live.in_flight() puts every open request in exactly one.
IN_FLIGHT_STATES = [
    ("queued", "Not yet asked", "Queued this cycle, ask not sent", "the connector's batch goes out; tick ask sent", "top"),
    ("no_slot", "Not yet asked", "Routed, no slot this cycle", "waits for the connector's next cycle", "top"),
    ("no_path", "Not yet asked", "No path to the company in the network", "a path has to be found or the request closed", "exceptions"),
    ("unresolved", "Not yet asked", "Company unresolved", "the requester names the company", "exceptions"),
    ("held", "Not yet asked", "Unresolved ask on every path", "waits on the follow-up owed at the company", "exceptions"),
    ("repair", "Not yet asked", "Filed Intro sent, no intro logged: repair queue", "the requester logs the intro or corrects the status", "exceptions"),
    ("chase", "Asked, waiting on the connector", "Asked, no reply: chase owed", "chase the connector", "followups"),
    ("nudge", "Asked, waiting on the connector", "Agreed, no intro yet: nudge owed", "nudge the connector", "followups"),
    ("quiet", "Asked, waiting on the connector", "Nudged or chased recently", "wait out the quiet period", "followups"),
    ("parked", "Introduced", "Parked behind a live intro at the company", "the rep introduced asks for the other names", "introduced"),
    ("introduced", "Introduced", "Intro sent, no meeting yet", "the rep books the meeting", "stages"),
    ("meeting", "Introduced", "Meeting booked", "the rep logs the opportunity", "stages"),
    ("other", "Not yet asked", "Open, nothing on file", "", ""),
]
# why a request is in the ranked queue, in the order the Top Priorities header lists them
CONSIDERED_BY = [("allocated", "allocated a slot this cycle"), ("no_slot", "routed, no slot this cycle"),
                 ("held", "held on an unresolved ask"), ("asked", "asked already, no slot for the retry"),
                 ("other", "ranked on a best path")]
THREADS_COMMAND = "python3 golden/build_golden.py --threads {file} && python3 build.py"
# the heads-up to the account owner behind an allocation row's notify_owner (build_golden.NOTIFY_STAGES);
# drafted here so it can be copied, never sent
OWNER_HEADS_UP = ("Heads up: {requester} asked for an intro to the {title} at {company}, queued to {connector}. "
                  "You own the account and it's in {stage}. Say if you'd rather I hold it.")

# "Route a live request" presets: real message shapes, one per thing the router must get right
ROUTE_PRESETS = [
    {"label": "Distractor", "text": "Calderon Aerospace introduced us to Kestrel Airlines, but the account I actually need is Ironvale Steel"},
    {"label": "Bridge", "text": "trying to reach COO at Apex Logistics. I know we sell into Larkhall Software and Cindermill Mining"},
    {"label": "Domain only", "text": "email domain is bexleybio.com"},
    {"label": "No path", "text": "any connections into Halcyon Grid?"},
    {"label": "Fund or customer", "text": "who do we know at Thornbury?"},
    {"label": "No CRM record", "text": "any connections into Kingsmere Retail Group? we're up against a renewal window"},
    {"label": "Network only", "text": "any way into Zenner Foods?"},
]


def parse_date(s: str) -> date | None:
    try:
        return datetime.strptime((s or "").strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def ask_dates(o: dict) -> list[str]:
    """Every ask an outcome row records: the first, plus the retry sent after its intro fizzled."""
    return [d for d in (o["asked_date"], o.get("reasked_date", "")) if d]


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
        self.alloc_by_rid = rs.current_allocation(self.history)
        self.completions = bg.load_completions()
        self.outcomes = bg.with_completions(bg.read_csv(CURRENT / "intro_outcomes.csv"), self.completions)
        self.outcome_by_rid = {o["request_id"]: o for o in self.outcomes}
        # one state per request, the classifier Live Data's cuts use (dashboard/request_state.py)
        self.states = rs.classify(self.requests, self.outcome_by_rid, self.alloc_by_rid)
        self.raw = {r["request_id"]: r for r in bg.read_csv(CURRENT / "intro_requests.csv")}
        self.accounts = {a["account_id"]: a for a in bg.read_csv(CURRENT / "crm_accounts.csv")}
        self.roster = bg.load_roster()
        self.threads = bg.load_threads()
        self.rates = bg.delivery_rates(self.roster, self.outcomes, self.threads)
        self.cycle = self.allocation[0]["cycle"] if self.allocation else today.strftime("%Y-%m")
        self.fatigue = bg.history_signals(self.history, self.outcomes, today).fatigue
        open_since: dict[str, list[str]] = defaultdict(list)
        for r in self.requests:
            if r["company_id"] and r["status_as_filed"] in bg.OPEN_STATUSES:
                open_since[r["company_id"]].append(r["request_date"])
        company_of = {r["request_id"]: r["company_id"] for r in self.requests}
        self.intro_state = bg.introductions(self.outcomes, company_of, today, open_since)
        self.held = bg.unresolved_asks(self.outcomes, company_of, today)
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
        self.network_only = self.network_only_companies()

    def network_only_companies(self) -> dict[str, dict]:
        """Companies the network reaches (connections_*.csv, investor_network.csv)
        that are on nobody's file: not in the CRM, never requested. The build keeps
        them out of supply_reach.csv until a request names one; then the next
        rebuild creates the company (no CRM account) and every one of these paths
        lands. Keyed 'network:<strict name>', each with the spellings seen and its
        paths as supply_reach.csv rows, so the front page can show the routing a
        request about the company would get today."""
        funds = [inv["fund"] for inv in bg.read_csv(CURRENT / "investor_network.csv")]
        on_file = bg.Registry(list(self.accounts.values()), funds)
        for c in self.companies.values():
            for n in [c["company_name"], *bar(c["also_known_as"])]:
                on_file.resolve_or_create(n, c["domain"])
        fresh = bg.Registry([], funds)  # merges the spellings of one unrequested company as the build would
        people = bg.network_people(self.roster)
        by_company: dict[bg.Company, list[dict]] = defaultdict(list)
        for p in bg.network_reach(self.roster, self.today):
            if on_file.resolve(p["company"])[1] != "unmatched":
                continue
            c, _ = fresh.resolve_or_create(p["company"])
            if c is not None:
                by_company[c].append(p)
        out = {}
        for c, paths in by_company.items():
            rows = [bg.supply_row(self.roster, self.rates, people, p["connector"], "", c.name, "", p["kind"], p["contact"],
                                  p["title"], p["observed"], p["strength"], p["evidence"], board_seat=p["board_seat"])
                    for p in paths]
            rows.sort(key=lambda r: (r["reach_type"], r["connector"], r["contact_name"], r["evidence"]))
            out[f"network:{gr.normalize_strict(c.name)}"] = {"name": c.name, "names": sorted(c.names, key=str.lower), "paths": rows}
        return out

    # -- helpers --------------------------------------------------------------
    def industry(self, cid: str) -> str:
        return self.companies.get(cid, {}).get("industry", "")

    def fit(self, connector: str, industry: str) -> float:
        r = self.roster.get(connector)
        return bg.fit(r, industry) if r else 0.7

    def rate(self, connector: str) -> float:
        return self.rates.get(connector, bg.PRIOR_RATE)

    def ranked_paths(self, cid: str) -> list[dict]:
        """Every path into a company from supply_reach.csv, in the allocator's order
        (bg.path_rank: roster before investor_network, then route score = strength x
        focus fit x delivery rate; then bg.hold_paths: a connector who never
        answered an ask here more than UNANSWERED_ASK_DAYS ago behind everyone,
        and one who agreed and sent no intro, or has not answered yet, last of
        all and not askable), each with the one line of reasoning the route
        panel shows."""
        return self.rank_paths(self.paths.get(cid, []), self.industry(cid), cid)

    def hold_of(self, connector: str, cid: str) -> dict | None:
        """The unresolved ask that holds a connector's paths into a company, as the
        page shows it: {hold, reason, request_id, days}; None when nothing does."""
        u = self.held.get((connector, cid)) if cid else None
        if u is None:
            return None
        return {"hold": u["hold"], "reason": bg.hold_reason(u), "request_id": u["request_id"], "days": u["days"],
                "askable": u["hold"] == bg.HOLD_LAST}

    def holds(self, cid: str) -> dict[str, dict]:
        """connector -> hold_of for everyone sitting on an unresolved ask at the
        company, path or no path (an offer in a thread is a path too)."""
        return {n: self.hold_of(n, c) for (n, c) in self.held if c == cid}

    def rank_paths(self, rows: list[dict], ind: str, cid: str = "") -> list[dict]:
        """ranked_paths for any supply_reach.csv-shaped rows (a company's, or a
        network-only company's from network_only_companies). Askable paths first,
        in the order the allocator tries them; the paths of a connector whose
        unresolved ask here rules them out follow, flagged askable = False."""
        ordered = sorted(rows, key=lambda p: bg.path_rank(p, self.roster, self.rates, ind))
        askable, skipped = bg.hold_paths(ordered, self.held, cid) if cid else (ordered, [])
        out_of_play = {u["connector"] for u in skipped}
        out = []
        for p in askable + [p for p in ordered if p["connector"] in out_of_play]:
            n = p["connector"]
            hold = self.hold_of(n, cid)
            fit, rate = self.fit(n, ind), self.rate(n)
            r = self.roster.get(n)
            when = (p["observed_date"] or "")[:7]
            if p["reach_type"] == "offer":
                via = "Offered in Slack" + (f" (knows {p['contact_title']})" if p["contact_title"] else "")
                via += f" · {p['offer_age_days']} days ago" if p["offer_age_days"] else ""
            elif p["reach_type"] in ("investor", bg.INVESTOR_NETWORK):
                via = f"{'Board seat' if p['board_seat'] == 'yes' else 'Investor'} · {p['contact_title']}" if p["contact_title"] else "Investor path"
                if p["reach_type"] == bg.INVESTOR_NETWORK:
                    via += f" · in our network, not on the roster ({round((1 - bg.NETWORK_HAIRCUT) * 100)}% haircut, asked after the roster)"
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
            score = bg.path_score(p, self.roster, self.rates, ind)
            out.append({
                "connector": n, "connector_type": p["connector_type"], "on_roster": r is not None, "reach_type": p["reach_type"],
                "contact": p["contact_name"], "title": p["contact_title"], "connected": when, "board_seat": p["board_seat"] == "yes",
                "strength": round(float(p["strength"]), 3), "fit": round(fit, 2), "rate": round(rate, 3),
                "score": round(score, 3), "in_focus": p["in_focus_area"], "idle": idle, "capacity": cap,
                "capacity_left": round(capacity_left, 3), "connector_score": round(score * capacity_left, 3),
                "evidence": p["evidence"], "label": bg.path_label(p),
                "reason": f"{via} · delivers {round(rate * 100)}% of asks · {focus}" + (f" · {hold['reason']}" if hold else ""),
                "hold": hold["hold"] if hold else "", "askable": hold is None or hold["askable"],
            })
        return out

    def route_priority(self, cid: str) -> dict:
        """Request priority for a message about this company pasted today: deal value is
        the company's one $ (company_value: CRM ARR potential, else the latest request
        with one; a Slack message carries none); age is 1.0 (posted today); reps waiting
        counts the requesters already live on the company, at least one (the poster)."""
        c = self.companies.get(cid)
        deal, src = self.company_value(cid) if c else (0.0, "")
        source = {"crm": "CRM ARR potential", "deal": "latest request on the company with a deal value"}.get(src, "no deal value on file")
        comp = {
            "deal_value_musd": deal / 1e6,
            "stage_weight": STAGE_WEIGHT.get(c["stage"], NO_CRM_WEIGHT) if c and c["crm_account_ids"] else NO_CRM_WEIGHT,
            "age": 1.0,
            "reps_waiting": max(1, len(self.live_requesters(cid))),
        }
        return {"request_priority": round(comp["deal_value_musd"] * comp["stage_weight"] * comp["age"] * comp["reps_waiting"], 3),
                "components": {k: round(v, 3) for k, v in comp.items()}, "deal_source": source}

    def crm_stage(self, cid: str) -> str:
        """The company's CRM stage (golden_companies.stage) or 'no CRM account'."""
        return self.companies.get(cid, {}).get("stage", "") or "no CRM account"

    def owner_notice(self, a: dict) -> dict | None:
        """The heads-up owed to the account owner(s) an allocation row flags
        (notify_owner), with the message drafted; None when the row is not flagged."""
        if not a["notify_owner"]:
            return None
        stage = self.crm_stage(a["company_id"])
        requester = self.by_rid[a["request_id"]]["requested_by"]
        return {
            "request_id": a["request_id"], "requester": requester,
            "owner": a["notify_owner"], "owners": a["notify_owner"].split(bg.MULTI), "stage": stage,
            "message": OWNER_HEADS_UP.format(requester=requester, title=a["target_title"] or "contact",
                                             company=a["company_name"], connector=a["allocated_to"], stage=stage),
        }

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
        return self.with_parties(i)

    def with_parties(self, i: dict) -> dict:
        """The intro plus the rep it was for and who at the company it was meant to
        reach: the person named in the raw ask, else the title asked for."""
        r = self.by_rid.get(i["request_id"], {})
        return {**i, "requested_by": r.get("requested_by", ""), "target_title": r.get("target_title", ""),
                "target_person": self.raw.get(i["request_id"], {}).get("target_person_raw", "").strip()}

    def retry_note(self, i: dict) -> dict:
        when = i["intro_date"] or "an undated"
        target = i["target_person"] or (f"their {i['target_title']}" if i["target_title"] else "someone there")
        return {**i, "note": f"{i['connector'].split()[0]}'s {when} intro of {i['requested_by'] or 'the requester'} to {target} went nowhere: {i['outcome']}"}

    def retry_of(self, cid: str) -> dict | None:
        """Set when the company's last intro fizzled (no meeting after INTRO_LIVE_DAYS,
        or a meeting with no opportunity after as long while newer requests wait):
        a fresh ask on it is a retry and is labelled as one."""
        i = self.prior_intro(cid)
        if not i or i["live"]:
            return None
        return self.retry_note(i)

    def own_retry(self, o: dict) -> dict | None:
        """The fizzled intro an outcome row itself logged, when the request is
        being asked again (build_golden.retriable, or reasked_date already set)."""
        i = bg.intro_of(o, self.today)
        if not i or i["live"]:
            return None
        return self.retry_note(self.with_parties(i))

    def live_requesters(self, cid: str) -> list[str]:
        return sorted({r["requested_by"] for r in self.by_company.get(cid, [])
                       if r["status_as_filed"] in bg.OPEN_STATUSES})

    def asks_this_cycle(self, connector: str) -> int:
        return sum(1 for o in self.outcomes if o["connector_asked"] == connector
                   for d in ask_dates(o) if d.startswith(self.cycle))

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
            asks = sum(1 for o in mine for d in ask_dates(o) if d.startswith(cyc))
            asks_roster = sum(1 for o in mine if o["connector_asked"] in on_roster for d in ask_dates(o) if d.startswith(cyc))
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
        """One $ per company (dashboard/company_value.py): CRM ARR potential when the
        company has one, else the deal value on its most recent request that carries
        one. Returns (usd, source)."""
        return cv.company_value(self.companies.get(cid, {}), self.by_company.get(cid, []))

    def dollars(self, cid: str, request_value: str = "") -> int:
        """The one $ shown for a row: company_value() when the row has a company;
        a request that resolved to no company stands at its own deal value."""
        return self.company_value(cid)[0] if cid else usd(request_value)

    def dollars_total(self, rows: list[dict]) -> int:
        """Sum of one $ per distinct company across rows carrying company_id (and
        value_usd for the unresolved ones), so a company on two rows counts once."""
        return cv.total(rows, self.companies, self.by_company)

    def company_stage(self, cid: str) -> str:
        """The furthest stage any of the company's requests has reached: a company
        with a meeting booked stays there however many fresh asks are open on it. 'closed'
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
            "excluded": {"stage": "closed", "count": count["closed"], "unresolved": unresolved["closed"], "usd": dollars["closed"], "usd_fmt": money(dollars["closed"])},
            "total": {"count": sum(count[s] for s in STAGES), "usd": sum(dollars[s] for s in STAGES), "usd_fmt": money(sum(dollars[s] for s in STAGES)),
                      "companies": sum(count[s] - unresolved[s] for s in STAGES),
                      "unresolved": sum(unresolved[s] for s in STAGES),
                      "unresolved_usd_fmt": money(sum(unresolved_usd[s] for s in STAGES))},
            "value_source": {"crm": source["crm"], "deal": source["deal"], "none": source["none"]},
        }

    # -- 2. top priorities ----------------------------------------------------
    def ranked(self) -> list[dict]:
        """Every live not-yet-asked request (golden_allocation.csv) with a connector
        to act on, scored expected value = request priority x connector score and
        sorted best first. Requests parked on a live intro or in the repair queue
        are not askable and stay off the list. Computed once; priorities() and
        connector_pages() slice it."""
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
            if not cid or a["exception_reason"].startswith((bg.ALREADY_INTRODUCED, bg.INTRO_CLAIMED_NOT_LOGGED)):
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
                capacity_left, capacity_note = 0.0, a["exception_reason"].partition(": ")[0]
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
                "on_roster": connector in self.roster,
                "path": bg.path_label(p),
                "value_fmt": money(self.dollars(cid)),
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
                "reopened": bg.reopened(a),
                "notify": self.owner_notice(a),
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
            "delivery_rate": f"(intros + {bg.PRIOR_RATE} × {bg.PRIOR_WEIGHT:g}) / (asks + {bg.PRIOR_WEIGHT:g}): intros / asks shrunk toward the {round(100 * bg.PRIOR_RATE)}% network average, "
                             f"which is all a connector never asked has (supply_reach.csv delivery_rate)",
            "capacity_left": "share of stated monthly capacity still unspent when the allocator reached this request; 0 when the cycle's slots were gone",
        }

    def priorities(self) -> dict:
        """The top TOP_N, then the rest of the ranked queue (folded on the page) with
        its deal value and how many of it wait only for a slot."""
        rows = self.ranked()
        rest = rows[TOP_N:]
        return {"top": rows[:TOP_N], "rest": rest, "considered": len(rows), "formula": self.formula(),
                "considered_by": self.considered_by(rows),
                "rest_value_fmt": money(self.dollars_total([self.by_rid[r["request_id"]] for r in rest])),
                "rest_no_slot": sum(1 for r in rest if not r["allocated"])}

    def considered_by(self, rows: list[dict]) -> list[dict]:
        """The ranked queue split by why each request is in it: allocated a slot this
        cycle, routed but out of slots, or held on an unresolved ask (the allocator's
        exception, still ranked on its best path). Each split says how many of its
        requests are a retry after a fizzled intro; a retry is allocated like any
        first ask, but one left without a slot stays in the request_state it already
        has (asked) rather than counting as routed-but-out-of-slots twice."""
        def why(r: dict) -> str:
            if r["allocated"]:
                return "allocated"
            state = self.states[r["request_id"]]
            if state == bg.CAPACITY_EXHAUSTED:
                return "no_slot"
            if state == bg.UNRESOLVED_ASK:
                return "held"
            if state == rs.ASKED:
                return "asked"
            return "other"
        groups = defaultdict(list)
        for r in rows:
            groups[why(r)].append(r)
        return [{"key": key, "label": label, "count": len(groups[key]),
                 "retries": sum(1 for r in groups[key] if r["retry"]),
                 "request_ids": sorted(r["request_id"] for r in groups[key])}
                for key, label in CONSIDERED_BY if groups[key]]

    # -- 3. current asks ------------------------------------------------------
    def batch_companies(self, rows: list[dict]) -> list[dict]:
        """One connector's allocation rows this cycle grouped by company: everyone
        wanted there, who is waiting, the path taken and why it won, the owner
        heads-up owed. Batch order (the allocator's) is kept."""
        if not rows:
            return []
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
                "value_usd": self.dollars_total(group),
                "value_fmt": money(self.dollars_total(group)),
                "urgency": sorted({g["urgency_declared"] for g in group}, key=lambda u: bg.URGENCY_RANK.get(u, 9))[0],
                "retry": self.retry_of(cid),
                "reopened": "; ".join(f"{g['request_id']} {bg.reopened(g)}" for g in group if bg.reopened(g)),
                "notify": [n for n in (self.owner_notice(g) for g in group) if n],
            })
        return companies

    def focus_finding(self) -> dict:
        """Every ask on file split by whether the company's industry was in the
        asked connector's focus areas, with the intro rate of each half."""
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
        return {
            "in_focus_asks": asks_in, "out_focus_asks": asks_out, "total_asks": asks_in + asks_out,
            "in_focus_rate": round(intros_in / asks_in, 2) if asks_in else 0,
            "out_focus_rate": round(intros_out / asks_out, 2) if asks_out else 0,
            "in_focus_pct": f"{round(100 * intros_in / asks_in) if asks_in else 0}%",
            "out_focus_pct": f"{round(100 * intros_out / asks_out) if asks_out else 0}%",
        }

    def asks(self) -> dict:
        """What is going out this cycle (one batch per connector, the Aggregate
        across them) and what the allocator could not place, by reason. A request
        whose only fault is that its connector's slots are gone is not an exception
        here: it keeps its connector and its expected value on the ranked list.
        An Intro sent request with no intro logged (build_golden.INTRO_CLAIMED_NOT_LOGGED)
        is the repair queue: the requester logs the intro or corrects the status,
        else it routes as Stalled after REPAIR_DAYS. A batch row's box is the ask_sent tick of every request in it (the same
        tick as Top Priorities and the connector's page); a no-path exception can
        be ticked with whoever was actually asked, `roster` being the picker's list."""
        batches: dict[str, list[dict]] = defaultdict(list)
        for a in self.allocation:
            if a["allocated_to"]:
                batches[a["batch_id"]].append(a)

        out = []
        for batch_id, rows in sorted(batches.items()):
            connector = rows[0]["allocated_to"]
            out.append({
                "batch_id": batch_id, "connector": connector, "slug": slug(connector),
                "connector_type": self.connector_facts.get(connector, {}).get("type", ""),
                "size": len(rows), "value_fmt": money(self.dollars_total(rows)),
                "companies": self.batch_companies(rows),
            })

        routed_at: dict[str, list[dict]] = defaultdict(list)
        for a in self.allocation:
            if a["allocated_to"] and a["company_id"]:
                routed_at[a["company_id"]].append({"request_id": a["request_id"], "connector": a["allocated_to"]})
        # the allocator's exceptions, grouped by the request's state: the classified table filtered to the
        # states an exception_reason names (asked, allocated and status-gated requests are not here)
        exceptions: dict[str, list[dict]] = defaultdict(list)
        no_slot = 0
        for a in self.allocation:
            state = self.states[a["request_id"]]
            if state in (rs.ASKED, rs.ALLOCATED) or state.startswith(rs.STATUS_GATE):
                continue
            if state == bg.CAPACITY_EXHAUSTED:
                no_slot += 1
            else:
                detail = a["exception_reason"].partition(": ")[2]
                exceptions[state].append({
                    "request_id": a["request_id"], **self.company_ref(a["company_id"], a["company_name"]),
                    "detail": detail,
                    "routed_here": sorted(routed_at.get(a["company_id"], []), key=lambda r: r["request_id"]),
                    "target_title": a["target_title"], "requested_by": self.by_rid[a["request_id"]]["requested_by"],
                    "value_fmt": money(self.dollars(a["company_id"], a["value_usd"])), "urgency": a["urgency_declared"],
                    "status": a["status_as_filed"], "best_path": a["best_path_if_unbudgeted"],
                    "reopened": bg.reopened(a),
                    "blocked_reason": self.by_rid[a["request_id"]]["blocked_reason"],
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
            "cycle": self.cycle, "on_file": len(self.requests), "cycle_size": len(self.alloc_by_rid),
            "allocated": sum(b["size"] for b in out), "batches": out,
            "all": everything, "notify_count": sum(len(c["notify"]) for c in everything), "value_fmt": money(self.dollars_total([self.by_rid[a["request_id"]] for b in batches.values() for a in b])),
            "exceptions": [{"reason": k, "count": len(v), "value_fmt": money(self.dollars_total([self.by_rid[r["request_id"]] for r in v])),
                            "rows": v} for k, v in sorted(exceptions.items(), key=lambda kv: -len(kv[1]))],
            "exception_count": n_exc, "no_slot": no_slot, "focus": self.focus_finding(),
            "roster": list(self.roster), "repair_days": bg.REPAIR_DAYS,
        }

    # -- 3b. already introduced: extend the intro, don't ask afresh -------------
    def introduced(self) -> dict:
        """Live requests the allocator parked because the company already has a live
        intro (build_golden.ALREADY_INTRODUCED: sent within INTRO_LIVE_DAYS, or a
        meeting booked that has not stalled). One row per company; the action is the rep who received
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
                "value_usd": self.dollars(cid),
                "value_fmt": money(self.dollars(cid)),
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
                "value_usd": self.dollars(cid),
                "value_fmt": money(self.dollars(cid)),
                "retry": self.retry_of(cid),
            })
        retries.sort(key=lambda r: (-r["value_usd"], r["company_name"]))
        return {
            "days": bg.INTRO_LIVE_DAYS, "rows": rows, "count": len(rows),
            "requests": sum(len(r["request_ids"]) for r in rows),
            "value_fmt": money(sum(r["value_usd"] for r in rows)),
            "retries": retries, "retry_requests": sum(len(r["request_ids"]) for r in retries),
        }

    # -- 4. follow-ups owed -----------------------------------------------------
    def sitting_on(self, name: str) -> list[dict]:
        """Every live ask on this connector with no intro yet: `nudge` it if they
        replied, `chase` if they never did. A retry sent after a fizzled intro
        (reasked_date) is a fresh ask nobody has answered: `chase`, counted from
        the re-ask. One followed up in the last NUDGE_QUIET_DAYS (nudged_on, from
        completions.csv) is `quiet`: listed, not actionable, until the period ends.
        `blocking` lists the live requests at the company this ask left with no
        askable path (the requests in the unresolved-ask state, as the exceptions
        section lists them). Actionable rows first, oldest ask first; the quiet
        ones last."""
        blocked = defaultdict(list)
        for a in self.allocation:
            if self.states[a["request_id"]] == bg.UNRESOLVED_ASK:
                blocked[a["company_id"]].append(a["request_id"])
        rows = []
        for o in self.outcomes:
            if o["connector_asked"] != name or (o["intro_sent"] == "Y" and not o["reasked_date"]):
                continue
            r = self.by_rid.get(o["request_id"], {})
            if r.get("status_as_filed") not in bg.OPEN_STATUSES:
                continue
            last = parse_date(r.get("nudged_on", ""))
            since = (self.today - last).days if last else None
            asked_on = o["reasked_date"] or o["asked_date"]
            responded = o["responded"] == "Y" and not o["reasked_date"]
            value, source = self.company_value(r["company_id"]) if r.get("company_id") else (usd(r.get("value_usd", "")), "request")
            rows.append({
                "request_id": o["request_id"], **self.company_ref(r.get("company_id", ""), r.get("company_as_written", "")),
                "target_title": r.get("target_title", ""), "requested_by": r.get("requested_by", ""),
                "connector": name, "on_roster": name in self.roster,
                "asked_date": asked_on, "responded": responded, "agreed_date": o["response_date"] if responded else "",
                "days_since_asked": (self.today - (parse_date(asked_on) or self.today)).days,
                "value_fmt": money(value), "value_usd": value, "value_source": source,
                "status": r.get("status_as_filed", ""),
                "action": "nudge" if responded else "chase",
                "retry": self.own_retry(o) if o["reasked_date"] else None,
                "nudged_on": r.get("nudged_on", ""), "days_since_nudged": since,
                "quiet": since is not None and 0 <= since < NUDGE_QUIET_DAYS,
                "blocking": sorted(blocked.get(r.get("company_id", ""), [])),
            })
        return sorted(rows, key=lambda s: (s["quiet"], s["asked_date"], s["request_id"]))

    def followups(self) -> dict:
        """Every ask anyone is sitting on, across every connector (roster, off-roster
        batch holders, and anyone else in intro_outcomes.csv), oldest first; then
        the same rows per connector. No slot is spent here: a nudge or a chase,
        never a fresh ask, and while a row stands its connector is not routed a
        new ask at that company."""
        names = self.connector_names()
        names += sorted({o["connector_asked"] for o in self.outcomes if o["connector_asked"] and o["connector_asked"] not in names})
        per = [{"connector": n, "slug": slug(n), "page": CONNECTOR_PAGE.format(slug=slug(n)), "on_roster": n in self.roster, "rows": rows,
                "count": sum(1 for s in rows if not s["quiet"]),
                "nudge": sum(1 for s in rows if s["action"] == "nudge" and not s["quiet"]),
                "chase": sum(1 for s in rows if s["action"] == "chase" and not s["quiet"])}
               for n in names for rows in [self.sitting_on(n)] if rows]
        rows = sorted((s for c in per for s in c["rows"]), key=lambda s: (s["quiet"], s["asked_date"], s["request_id"]))
        return {
            "rows": rows, "count": sum(1 for s in rows if not s["quiet"]),
            "nudge": sum(1 for s in rows if s["action"] == "nudge" and not s["quiet"]),
            "chase": sum(1 for s in rows if s["action"] == "chase" and not s["quiet"]),
            "quiet": [s for s in rows if s["quiet"]], "quiet_days": NUDGE_QUIET_DAYS,
            "by_connector": per,
        }

    # -- 5. requests in flight ---------------------------------------------------
    def in_flight(self) -> dict:
        """Every request in flight (filed open, or in the allocator's current
        cycle: the set every section of this tab works from), each in exactly one
        state, with the section that owns it, so the Live Data tab can show the
        same counts. A request filed finished with nothing in the ask log is in
        the allocator (build_golden.in_queue), so it is in flight; one filed
        finished and asked is not, and is counted outside by status.
        Follow-Ups Owed owns an ask nobody has resolved (nudge, chase, or quiet
        after a recent follow-up); the allocation owns the rest of the
        not-yet-asked (queued, no slot this cycle, and each exception reason);
        what is left sits on its own intro or meeting."""
        sitting = {s["request_id"]: s for s in self.followups()["rows"]}
        by_state: dict[str, list[dict]] = defaultdict(list)
        outside = Counter()
        for r in self.requests:
            rid = r["request_id"]
            o, a, state = self.outcome_by_rid.get(rid), self.alloc_by_rid.get(rid), self.states[rid]
            if r["status_as_filed"] not in bg.OPEN_STATUSES and a is None:
                outside[r["status_as_filed"]] += 1
                continue
            if rid in sitting:
                s = "quiet" if sitting[rid]["quiet"] else sitting[rid]["action"]
            elif a and a["allocated_to"]:
                s = "queued"
            elif state == bg.CAPACITY_EXHAUSTED:
                s = "no_slot"
            elif a and a["exception_reason"].startswith(bg.ALREADY_INTRODUCED):
                s = "parked"
            elif state == bg.NO_PATH:
                s = "no_path"
            elif state == bg.UNRESOLVED_ASK:
                s = "held"
            elif state == bg.INTRO_CLAIMED_NOT_LOGGED:
                s = "repair"
            elif a and state != rs.ASKED:
                s = "unresolved"
            elif (o and o["meeting_booked"] == "Y") or r["meeting_booked"] == "Y":
                s = "meeting"
            elif (o and o["intro_sent"] == "Y") or r["intro_sent"] == "Y":
                s = "introduced"
            else:
                s = "other"
            by_state[s].append(r)

        def note(key: str, rows: list[dict]) -> str:
            if key == "queued":
                retries = sum(1 for r in rows if r["company_id"] and self.retry_of(r["company_id"]))
                return f"{retries} of them a retry after a fizzled intro" if retries else ""
            if key == "meeting":
                opp = sum(1 for r in rows if self.outcome_by_rid.get(r["request_id"], {}).get("opportunity_created") == "Y")
                return f"{opp} already have an opportunity logged, still filed open" if opp else ""
            if key == "quiet":
                return f"followed up within the last {NUDGE_QUIET_DAYS} days, so not owed yet"
            return ""

        rows = [{
            "key": key, "group": group, "label": label, "next": nxt, "section": section,
            "count": len(by_state[key]), "value_usd": self.dollars_total(by_state[key]),
            "value_fmt": money(self.dollars_total(by_state[key])), "note": note(key, by_state[key]),
            "request_ids": sorted(r["request_id"] for r in by_state[key]),
        } for key, group, label, nxt, section in IN_FLIGHT_STATES if by_state[key] or key not in ("quiet", "other")]
        every = [r for v in by_state.values() for r in v]
        return {
            "open": len(every), "rows": rows,
            "value_usd": self.dollars_total(every), "value_fmt": money(self.dollars_total(every)),
            "groups": [{"group": g, "count": sum(r["count"] for r in rows if r["group"] == g)}
                       for g in dict.fromkeys(g for _, g, *_ in IN_FLIGHT_STATES)],
            "outside": [{"status": s, "count": n} for s, n in sorted(outside.items())],
            "quiet_days": NUDGE_QUIET_DAYS, "intro_live_days": bg.INTRO_LIVE_DAYS,
        }

    # -- 6. per-connector -----------------------------------------------------
    def connector_card(self, name: str) -> dict:
        """One connector's facts: capacity used against stated, delivery rate, what
        they are sitting on, their batch this cycle (grouped by company, with why
        each landed on them) and its drafted message. Works for people off the
        roster too (no stated capacity, no focus list)."""
        r = self.roster.get(name)
        cap = int(r["stated_monthly_capacity"] or 0) if r else 0
        asked_cycle = self.asks_this_cycle(name)
        queue = [a for a in self.allocation if a["allocated_to"] == name]
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
            # an ask recorded outside the allocation (a path not on file) counts, so used can pass stated capacity
            "over_capacity": max(0, asked_cycle + len(queue) - cap) if cap else 0,
            "delivery_rate": round(self.rate(name), 3), "asks_all_time": len(asks), "intros_all_time": len(intros),
            "prior_rate": bg.PRIOR_RATE,
            "intros_this_cycle": cycles[-1]["intros"], "cycles": cycles,
            "batch_ask": self.batch_ask(name),
            "sitting_on": self.sitting_on(name),
            "quiet_days": NUDGE_QUIET_DAYS,
            "batch_id": queue[0]["batch_id"] if queue else "",
            "batch_value_fmt": money(self.dollars_total(queue)),
            "companies": self.batch_companies(queue),
            "queue": [{
                "request_id": a["request_id"], **self.company_ref(a["company_id"], a["company_name"]),
                "connector": name,
                "target_title": a["target_title"], "requested_by": self.by_rid[a["request_id"]]["requested_by"],
                "path_type": a["path_type"], "contact": a["contact_name"], "route_score": a["route_score"],
                "value_fmt": money(self.dollars(a["company_id"], a["value_usd"])), "urgency": a["urgency_declared"],
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
            "cycle_size": len(self.alloc_by_rid),
            "messages": [{**m, "page": pages.get(m["connector"], ""),
                          "requests": [{**q, **self.company_ref(q["company_id"], q["company_name"]), "value_fmt": money(self.dollars(q["company_id"], q["value_usd"]))}
                                       for q in m["requests"]]} for m in messages],
            "templates": batch_ask.TEMPLATES.relative_to(ROOT).as_posix(),
        }

    def connector_names(self) -> list[str]:
        """Roster first, in roster order; then anyone off the roster who holds an
        allocation this cycle, largest batch first."""
        held = defaultdict(list)
        for a in self.allocation:
            if a["allocated_to"] and a["allocated_to"] not in self.roster:
                held[a["allocated_to"]].append(self.by_rid[a["request_id"]])
        extra = {n: self.dollars_total(rows) for n, rows in held.items()}
        return list(self.roster) + [n for n, _ in sorted(extra.items(), key=lambda kv: (-kv[1], kv[0]))]

    def connectors(self) -> list[dict]:
        """One card per connector with a stake in this cycle: the roster, then
        anyone off it who holds a batch."""
        return [self.connector_card(name) for name in self.connector_names()]

    def connector_pages(self) -> list[dict]:
        """One page per connector: their top 5 by expected value, then the rest of
        their ranked list, what they are already sitting on, and (read-only) the
        companies where their path is the strongest but did not route to them."""
        out = []
        for name in self.connector_names():
            mine = [dict(r, rank_here=i) for i, r in enumerate((r for r in self.ranked() if r["connector"] == name), 1)]
            out.append({
                **self.connector_card(name),
                "top": mine[:TOP_N], "rest": mine[TOP_N:], "ranked_count": len(mine), "cycle_size": len(self.alloc_by_rid),
                "ranked_value_fmt": money(self.dollars_total([self.by_rid[r["request_id"]] for r in mine])),
                "no_slot": sum(1 for r in mine if not r["allocated"]),
                "strongest_elsewhere": self.strongest_elsewhere(name),
                "formula": self.formula(), "completions": self.completion_export(), "as_of": self.today.isoformat(),
            })
        return out

    # -- 9. what the CRM is missing --------------------------------------------
    def crm(self) -> dict:
        w = wb.Writeback(self.today)
        review = w.review_rows()
        imports = w.import_rows()

        def rows(group: str) -> list[dict]:
            return [{**asdict(r), "value_fmt": money(self.dollars(r.company_id)), "href": self.company_ref(r.company_id)["href"],
                     "request_ids": bar(r.request_ids)} for r in review if r.group == group]

        groups = [{"group": g, "title": wb.GROUP_TITLES[g], "rows": rows(g), "count": len(rows(g)),
                   "value_fmt": money(self.dollars_total(rows(g)))}
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
            "actions": {"top": bg.ASKED, "nudge": bg.NUDGED, "chase": bg.CHASED},
            "ids": sorted(c["completion_id"] for c in self.completions), "count": len(self.completions),
            "quiet_days": NUDGE_QUIET_DAYS,
            "stamp": BUILD_STAMP.name, "repo_url": repo_url(), "workflow": WORKFLOW_FILE,
            "path": bg.COMPLETIONS_OUT.relative_to(bg.ROOT).as_posix(),
        }

    # -- 9c. what Accept writes ---------------------------------------------------
    def intake_export(self) -> dict:
        """Everything the browser needs to preview and accept an upload: every
        file as it stands in golden/current/ (columns + rows, so the diff is
        computed against the data the build read), the key per file, the ledger
        of uploads already accepted, and the Supabase endpoint. Only the anon
        key goes in; the service key never does."""
        bg.load_env()
        url = os.environ.get("SUPABASE_URL", "").strip()
        files = {}
        for name in intake.existing_targets():
            src = CURRENT / name
            if not src.exists():
                continue
            if intake.format_of(name) == "jsonl":
                files[name] = {"format": "jsonl", "keys": ["request_id"], "threads": intake.read_threads(src)}
            else:
                cols, rows = intake.read_csv_file(src)
                files[name] = {"format": "csv", "keys": intake.schema_of(name)["keys"], "columns": cols,
                               "rows": [[r.get(c, "") for c in cols] for r in rows]}
        rows = intake.ledger()
        return {
            "supabase_url": bg.supabase_rest(url) if url else "",
            "anon_key": os.environ.get("SUPABASE_ANON_KEY", "").strip(),
            "table": intake.SUPABASE_TABLE,
            "files": files,
            "schemas": [{"pattern": p, "keys": s["keys"], "family": bool(s.get("family")), "format": intake.format_of(p)}
                        for p, s in intake.SCHEMAS.items()],
            "ledger": [{k: r.get(k, "") for k in intake.LEDGER_COLUMNS} for r in rows],
            "ids": sorted(r["upload_id"] for r in rows),
            "generation": intake.generation(rows),
            "revert_target": intake.REVERT,
            "revert_command": intake.REVERT_COMMAND,
            "rejected": [{k: r.get(k, "") for k in intake.REJECTED_COLUMNS} for r in intake._read(intake.REJECTED)],
            "command": intake.COMMAND,
            "path": intake.LEDGER.relative_to(intake.ROOT).as_posix(),
            "current": CURRENT.relative_to(ROOT).as_posix(),
        }

    # -- 10. upload preview rules ----------------------------------------------
    def known_regex(self, res: gr.Resolver | None = None) -> re.Pattern:
        """What the build's registry scans a message for: every CRM and fund spelling,
        every company on file with no CRM account, and every company the network
        reaches (see Registry.known_names)."""
        res = res or load_resolver()
        return gr.names_regex([*(n for e in res.entities for n in e.names),
                               *(n for c in self.companies.values() if not c["crm_account_ids"]
                                 for n in [c["company_name"], *bar(c["also_known_as"])]),
                               *bg.network_company_names(self.roster)])

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
        # companies only the network knows: not on file, so the build would create
        # them (no CRM account) and file these paths on the next rebuild
        known_network = {}
        for key, net in self.network_only.items():
            for n in net["names"]:
                known_network.setdefault(gr.normalize_strict(n), key)
                known_network.setdefault(gr.normalize(n), key)

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
            best = next((p for p in paths if p["askable"]), None)
            acct = next((self.accounts[a] for a in bar(c["crm_account_ids"]) if a in self.accounts), None)
            companies[cid] = {
                **self.company_ref(cid), "industry": ind, "stage": c["stage"], "crm": bool(c["crm_account_ids"]),
                "owner": c["owner"], "arr_fmt": money(usd(acct["arr_potential_usd"])) if acct else "",
                "paths": paths, "path_count": len(paths), "priority": self.route_priority(cid),
                # who is sitting on an unresolved ask here, path or no path: the preview
                # skips them (or ranks them last) whether they have a path or offer in a thread
                "holds": self.holds(cid),
                "best": {"connector": best["connector"], "reach_type": best["reach_type"], "contact": best["contact"],
                         "score": best["score"], "label": best["label"], "strength": best["strength"], "fit": best["fit"],
                         "rate": best["rate"], "capacity_left": best["capacity_left"], "hold": best["hold"]} if best else None,
                "offer_score": {n: round(bg.PATH_BASE["offer"] * self.fit(n, ind) * self.rate(n), 3) for n in askable},
                "offer_fit": {n: round(self.fit(n, ind), 2) for n in askable},
                "offer_score_unknown": round(bg.PATH_BASE["offer"] * 0.7 * bg.PRIOR_RATE, 3),
            }
        for key, net in self.network_only.items():
            paths = self.rank_paths(net["paths"], "")
            best = paths[0] if paths else None
            companies[key] = {
                "company_id": "", "company_name": net["name"], "href": "", "network": True, "names": net["names"],
                "industry": "", "stage": "", "crm": False, "owner": "", "arr_fmt": "",
                "paths": paths[:NETWORK_PATHS_SHOWN], "path_count": len(paths), "priority": self.route_priority(key),
                "holds": {},
                "best": {"connector": best["connector"], "reach_type": best["reach_type"], "contact": best["contact"],
                         "score": best["score"], "label": best["label"], "strength": best["strength"], "fit": best["fit"],
                         "rate": best["rate"], "capacity_left": best["capacity_left"], "hold": ""} if best else None,
                "offer_score": {n: round(bg.PATH_BASE["offer"] * 0.7 * self.rate(n), 3) for n in askable},
                "offer_fit": {n: 0.7 for n in askable},
                "offer_score_unknown": round(bg.PATH_BASE["offer"] * 0.7 * bg.PRIOR_RATE, 3),
            }
        return {
            "cues": [{"label": label, **js_regex(pat), "score": score} for label, pat, score in gp._CUES],
            "lower_cues": [{"label": label, **js_regex(pat), "score": score} for label, pat, score in gp._LOWER_CUES],
            "word": js_regex(gp._WORD),
            "split": js_regex(gp._SPLIT), "domain": js_regex(gp._DOMAIN), "title": js_regex(gp.TITLE_RE),
            "domain_cue": gp.DOMAIN_CUE, "domain_score": gp.DOMAIN_SCORE,
            "known": js_regex(self.known_regex(res)), "known_cue": gp.KNOWN_CUE, "known_score": gp.KNOWN_SCORE,
            "bare": js_regex(gp._BARE), "bare_cue": gp.BARE_CUE, "bare_score": gp.BARE_SCORE,
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
            "known_network": known_network,
            # an offer on a company the build has never seen: no industry, so fit is 0.7 for everyone
            "offer_score_no_industry": {n: round(bg.PATH_BASE["offer"] * 0.7 * self.rate(n), 3) for n in askable},
            "offer_score_unknown": round(bg.PATH_BASE["offer"] * 0.7 * bg.PRIOR_RATE, 3),
            # the factors behind those scores, so the preview can show its arithmetic
            "offer_base": bg.PATH_BASE["offer"], "unknown_fit": 0.7, "prior_rate": bg.PRIOR_RATE,
            "off_roster_capacity": bg.OFF_ROSTER_CAPACITY, "no_crm_weight": NO_CRM_WEIGHT,
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
                                "resolved_by", "offer_by", "offer_text", "route_to", "path", "expected_value", "needs_human", "raw_ask"],
        }

    # -- everything ---------------------------------------------------------------
    def payload(self) -> dict:
        return {
            "as_of": self.today.isoformat(), "cycle": self.cycle, "trace_page": TRACE_PAGE, "batch_page": BATCH_PAGE,
            # the two populations every request count on the page is stated against
            "on_file": len(self.requests), "cycle_size": len(self.alloc_by_rid),
            "bands": [{"id": bid, "title": title, "sections": [sid for sid, _ in sections]}
                      for bid, title, sections in BANDS],
            "stages": self.stages(), "priorities": self.priorities(), "asks": self.asks(), "introduced": self.introduced(),
            "connectors": self.connectors(), "followups": self.followups(), "in_flight": self.in_flight(),
            "crm": self.crm(), "parser": self.parser(),
            "completions": self.completion_export(), "intake": self.intake_export(),
            "connector_pages": [{"connector": c["connector"], "page": c["page"], "on_roster": c["on_roster"]}
                                for c in self.connector_pages()],
        }


def payload(today: date | None = None) -> dict:
    return Live(today or as_of()).payload()


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
    return Live(today or as_of()).cycles()


def in_flight(today: date | None = None) -> dict:
    return Live(today or as_of()).in_flight()


def connector_fragments(today: date | None = None) -> list[tuple[dict, str]]:
    """(card, html) per connector page; card["page"] is the file name under docs/."""
    return [(c, _fragment(c, "bootConnector")) for c in Live(today or as_of()).connector_pages()]


def batch_fragment(today: date | None = None) -> str:
    return _fragment(Live(today or as_of()).batch_page(), "bootBatch")


if __name__ == "__main__":
    p = payload()
    print(f"as of {p['as_of']}, cycle {p['cycle']}")
    print("stages     ", ", ".join(f"{s['stage']} {s['count']} ({s['usd_fmt']})" for s in p["stages"]["stages"]))
    print("top 5      ", ", ".join(f"{r['request_id']} {r['company_name']} -> {r['connector']} EV {r['expected_value']}" for r in p["priorities"]["top"]))
    print(f"asks        {p['asks']['allocated']} allocated in {len(p['asks']['batches'])} batches; "
          + ", ".join(f"{e['count']} {e['reason']}" for e in p["asks"]["exceptions"]) + f"; {p['asks']['no_slot']} wait for a slot")
    print(f"follow-ups  {p['followups']['nudge']} nudges, {p['followups']['chase']} chases"
          + (f", {len(p['followups']['quiet'])} followed up recently" if p['followups']['quiet'] else ""))
    print(f"in flight   {p['in_flight']['open']} open: " + ", ".join(f"{r['count']} {r['key']}" for r in p["in_flight"]["rows"]))
    print(f"completions {p['completions']['count']} on file")
    print("crm        ", ", ".join(f"{g['count']} {g['group']}" for g in p["crm"]["groups"]))
