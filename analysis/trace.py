#!/usr/bin/env python3
"""The full history of one company, from every file that mentions it.

    python3 analysis/trace.py "Harrowgate Health"        # print one trace
    python3 analysis/trace.py C018 --as-of 2026-09-05    # by id, at a date
    python3 analysis/trace.py                            # every company with a
                                                         # request -> analysis/traces/

Six sections: the header (identity, request counts and the routing stage), where the files
disagree (skipped when they don't), who can reach them (supply_reach.csv ranked
by route score = strength x focus fit x delivery rate, the allocator's own sort
key, with the reason the top row did not take every live request), the chronology (every event from intro_requests.csv,
slack_threads.jsonl, intro_outcomes.csv and crm_accounts.csv, oldest first),
next steps, one row per person, cheapest action first, and the additional
investor and operator network (network_orbit.csv: everyone investor_network.csv
puts around the company, board seats first, then those a connector knows, then
those nobody has a warm path to; skipped when the file has no row for the
company). That last section is context, not supply: nothing in it is scored,
allocated or counted against a connector.

Chronology markers:  <- missed   ++ worked   ** offer   !! warning

Read-only over dataset/ and golden/. The company is looked up in
golden_companies.csv (id, name, alias, CRM account id, or any spelling a
request used); requests are joined on the company_id the golden build already
resolved, so this file never re-resolves names.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from golden.build_golden import (NETWORK_OUT, OFFER_RE, OPEN_STATUSES, PRIOR_RATE, REACHABLE_AS_CONNECTOR, STAGES, capacity,  # noqa: E402
                                 delivery_rates, fit, latest_cycle, load_completions, load_roster, load_threads, path_score,
                                 stage_of, with_completions)
from golden.resolver import normalize, normalize_strict  # noqa: E402
from paths import ANALYSIS, DATASET, GOLDEN  # noqa: E402

TRACES = ANALYSIS / "traces"
STALE_TOUCH_DAYS = 90
NO_WARM_PATH = "no warm path"  # the orbit table's label for a person no connector knows

MISSED, WORKED, OFFER, WARN, PLAIN = "<-", "++", "**", "!!", "  "

SOURCES = {
    "requests": "intro_requests.csv",
    "slack": "slack_threads.jsonl",
    "outcomes": "intro_outcomes.csv",
    "crm": "crm_accounts.csv",
}


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------
def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def parse_date(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).date()


def money(s: str) -> str:
    try:
        return f"${int(float(s)):,}"
    except (TypeError, ValueError):
        return s or "?"


def days_ago(d: date | None, today: date) -> str:
    return f"{(today - d).days} days ago" if d else "undated"


@dataclass
class Data:
    companies: list[dict]
    requests: list[dict]          # golden_requests.csv
    filed: dict[str, dict]        # intro_requests.csv by request_id
    outcomes: dict[str, list[dict]]
    threads: dict[str, dict]
    accounts: dict[str, dict]     # crm_accounts.csv by account_id
    supply: list[dict]
    allocation: list[dict]
    roster: dict[str, dict]
    outcome_by_rid: dict[str, dict]  # the ask log as the build reads it (completions applied), one row per request
    alloc_by_rid: dict[str, dict]    # the current cycle's allocation by request_id
    rates: dict[str, float]          # delivery rate per connector, as the allocator scores them
    orbit: list[dict]                # network_orbit.csv: investors and operators around each company

    @classmethod
    def load(cls) -> "Data":
        outcomes: dict[str, list[dict]] = defaultdict(list)
        logged = read_csv(DATASET / SOURCES["outcomes"])
        for o in logged:
            outcomes[o["request_id"]].append(o)
        allocation = latest_cycle(read_csv(GOLDEN / "golden_allocation.csv"))
        roster = load_roster()
        as_read = with_completions(logged, load_completions())
        threads = {}
        with open(DATASET / SOURCES["slack"], encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    t = json.loads(line)
                    threads[t["request_id"]] = t
        return cls(
            companies=read_csv(GOLDEN / "golden_companies.csv"),
            requests=read_csv(GOLDEN / "golden_requests.csv"),
            filed={r["request_id"]: r for r in read_csv(DATASET / SOURCES["requests"])},
            outcomes=outcomes,
            threads=threads,
            accounts={a["account_id"]: a for a in read_csv(DATASET / SOURCES["crm"])},
            supply=read_csv(GOLDEN / "supply_reach.csv"),
            allocation=allocation,
            roster=roster,
            outcome_by_rid={o["request_id"]: o for o in as_read},
            alloc_by_rid={a["request_id"]: a for a in allocation},
            rates=delivery_rates(roster, as_read, load_threads()),
            orbit=read_csv(NETWORK_OUT) if NETWORK_OUT.exists() else [],
        )


def find_company(data: Data, query: str) -> dict | None:
    """Match on id, name, alias, CRM account id, or any spelling a request used."""
    q = query.strip()
    for c in data.companies:
        if q.upper() == c["company_id"] or q.upper() in split_bar(c["crm_account_ids"]):
            return c
    spellings: dict[str, set[str]] = defaultdict(set)
    for c in data.companies:
        spellings[c["company_id"]].update([c["company_name"], *split_bar(c["also_known_as"])])
        for aid in split_bar(c["crm_account_ids"]):
            if aid in data.accounts:
                spellings[c["company_id"]].add(data.accounts[aid]["account_name"])
    for r in data.requests:
        if r["company_id"]:
            spellings[r["company_id"]].add(r["company_as_written"])
    # exact name first (holdco vs opco differ only by a suffix normalize() strips), then loose
    for norm, pool in ((normalize_strict, "name"), (normalize_strict, "all"), (normalize, "all")):
        key = norm(q)
        if not key:
            return None
        hits = [c for c in data.companies
                if key in {norm(s) for s in ([c["company_name"]] if pool == "name" else spellings[c["company_id"]]) if s}]
        if hits:
            return hits[0] if len(hits) == 1 else None
    return None


def split_bar(s: str) -> list[str]:
    return [p.strip() for p in (s or "").split("|") if p.strip()]


# ---------------------------------------------------------------------------
# one company
# ---------------------------------------------------------------------------
@dataclass
class Event:
    when: date
    source: str
    who: str
    what: str
    mark: str = PLAIN
    request_id: str = ""
    order: int = 0  # tie-break within a day: request, slack, outcome

    def line(self) -> str:
        return f"{self.mark} {self.when.isoformat()}  {self.source:<20} {self.who:<20} {self.what}"


@dataclass
class Step:
    order: int
    who: str
    role: str
    action: str
    why: str
    request_ids: list[str] = field(default_factory=list)


class Trace:
    def __init__(self, data: Data, company: dict, today: date):
        self.d = data
        self.c = company
        self.cid = company["company_id"]
        self.today = today
        self.requests = sorted((r for r in data.requests if r["company_id"] == self.cid),
                               key=lambda r: (r["request_date"], r["request_id"]))
        self.request_ids = [r["request_id"] for r in self.requests]
        # ranked as the allocator ranks them: route score first, raw strength breaks ties
        self.paths = sorted((p for p in data.supply if p["company_id"] == self.cid and p["reach_type"] != "none"),
                            key=lambda p: (-self.route_score(p), -float(p["strength"])))
        self.accounts = [data.accounts[a] for a in split_bar(company["crm_account_ids"]) if a in data.accounts]
        self.live = [a for a in data.allocation if a["company_id"] == self.cid]
        self.allocated = {a["request_id"]: a for a in self.live if a["allocated_to"]}
        # board seats first, then anyone a connector knows, then the cold rows
        self.orbit = sorted((r for r in data.orbit if r["company_id"] == self.cid),
                            key=lambda r: (r["board_seat"] != "yes", r["reachable_via"] == "", r["person"], r["source"]))

    # -- helpers --------------------------------------------------------------
    def spellings(self) -> list[str]:
        seen = {self.c["company_name"]}
        out = []
        for s in [*split_bar(self.c["also_known_as"]), *(a["account_name"] for a in self.accounts),
                  *(r["company_as_written"] for r in self.requests)]:
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out

    def intro_logged(self, rid: str) -> dict | None:
        for o in self.d.outcomes.get(rid, []):
            if o["intro_sent"] == "Y":
                return o
        return None

    def offers(self, rid: str) -> list[dict]:
        t = self.d.threads.get(rid)
        return [m for m in t["messages"][1:] if OFFER_RE.search(m["text"])] if t else []

    def asked(self, rid: str, person: str) -> bool:
        return any(o["connector_asked"] == person for o in self.d.outcomes.get(rid, []))

    def role_of(self, person: str) -> str:
        r = self.d.roster.get(person)
        if r:
            return f"{r['role']} ({r['type'].lower()} connector)"
        for rq in self.requests:
            f = self.d.filed.get(rq["request_id"])
            if rq["requested_by"] == person:
                return f["requester_role"] if f else "requester"
        if person in split_bar(self.c["owner"]):
            return "CRM owner"
        return "off-roster connector"

    def stage_of(self, r: dict) -> str:
        rid = r["request_id"]
        return stage_of(r, self.d.outcome_by_rid.get(rid), self.d.alloc_by_rid.get(rid))

    def fit_of(self, connector: str) -> float:
        r = self.d.roster.get(connector)
        return fit(r, self.c["industry"]) if r else 0.7

    def rate_of(self, connector: str) -> float:
        return self.d.rates.get(connector, PRIOR_RATE)

    def route_score(self, p: dict) -> float:
        """strength x focus fit x delivery rate: what build_golden.allocate sorts on."""
        return path_score(p, self.d.roster, self.d.rates, self.c["industry"])

    def strongest(self) -> dict | None:
        """The path with the highest raw strength: the row that reads as #1 when
        the table is sorted by strength alone."""
        return max(self.paths, key=lambda p: float(p["strength"])) if self.paths else None

    def bypass(self) -> str:
        """Why the strongest path did not take every live request this cycle:
        'Elena Duvall, offer 0.800, at capacity 3/3, Healthcare is outside her
        focus (route score 0.000); R1136 routed to Dana Whitfield, R1153 to Tomás Beckett'.
        Read off the roster, supply_reach.csv and this cycle's golden_allocation.csv
        rows for the company (never best_path_if_unbudgeted, which is sparse).
        Empty when there is no path, nothing is live this cycle, or the strongest
        path holds every live request."""
        top = self.strongest()
        if top is None or not self.live:
            return ""
        who = top["connector"]
        elsewhere = [a for a in self.live if a["allocated_to"] != who]
        if not elsewhere:
            return ""
        cap = capacity(self.d.roster, who)
        used = cap - int(top["idle_capacity"] or 0)
        why = []
        if cap and used >= cap:
            why.append(f"at capacity {used}/{cap}")
        elif cap:
            why.append(f"{used}/{cap} used this cycle")
        if self.fit_of(who) <= 0:
            why.append(f"{self.c['industry']} is outside their focus (route score {self.route_score(top):.3f})")
        went = [f"{a['request_id']} routed to {a['allocated_to']}" if a["allocated_to"]
                else f"{a['request_id']} unrouted" + (f" ({a['exception_reason']})" if a["exception_reason"] else "")
                for a in sorted(elsewhere, key=lambda a: a["request_id"])]
        holds = sorted(a["request_id"] for a in self.live if a["allocated_to"] == who)
        return (f"{who}, {top['reach_type']} {float(top['strength']):.3f}, " + ", ".join(why)
                + (f", holds {', '.join(holds)}" if holds else "") + "; " + ", ".join(went))

    def routing(self) -> dict:
        """Where the company sits in the routing funnel: the furthest stage any of
        its requests reached ('closed' only when every request is Closed - no
        path), the stage of its latest request, how many requests sit at each
        stage, and of those asked, how many connectors agreed vs never replied."""
        stages = {r["request_id"]: self.stage_of(r) for r in self.requests}
        counts = Counter(stages.values())
        asked = [rid for rid, s in stages.items() if s == "asked"]
        agreed = sum(1 for rid in asked if (self.d.outcome_by_rid.get(rid) or {}).get("responded") == "Y")
        return {
            "furthest": max((s for s in stages.values() if s != "closed"), key=STAGES.index, default="closed"),
            "latest": stages.get(self.c["latest_request_id"], ""),
            "counts": {s: counts[s] for s in [*STAGES, "closed"] if counts[s]},
            "awaiting_intro": {"agreed": agreed, "silent": len(asked) - agreed},
        }

    def last_touch(self) -> tuple[date | None, dict | None]:
        best, acct = None, None
        for a in self.accounts:
            d = parse_date(a["last_touch_date"])
            if d and (best is None or d > best):
                best, acct = d, a
        return best, acct

    # -- section 1 --------------------------------------------------------------
    def header(self) -> list[str]:
        c = self.c
        people = {r["requested_by"] for r in self.requests}
        titles = {r["target_title"] for r in self.requests if r["target_title"]}
        aka = self.spellings()
        out = [f"# {c['company_name']}  ({c['company_id']})", ""]
        out.append(f"- stage: {c['stage'] or '?'} | industry: {c['industry'] or '?'} | owner: {c['owner'] or 'none'}"
                   f" | deal value: {money(c['value_usd'])}"
                   + (f" | largest request: {money(c['largest_request_usd'])}" if c["largest_request_usd"] else ""))
        out.append(f"- CRM accounts: {c['crm_account_ids'] or 'none'}"
                   + (f" ({c['domain']})" if c["domain"] else "")
                   + (f" | duplicates: {c['duplicate_accounts']}" if c["duplicate_accounts"] not in ("", "no") else ""))
        out.append(f"- also goes by: {' | '.join(aka) if aka else 'nothing else'}")
        out.append(f"- {len(self.requests)} request{'s' if len(self.requests) != 1 else ''}"
                   f" from {len(people)} {'person' if len(people) == 1 else 'people'}"
                   f" wanting {len(titles)} different title{'s' if len(titles) != 1 else ''}"
                   + (f": {' | '.join(sorted(titles))}" if titles else ""))
        return out

    # -- section 2 --------------------------------------------------------------
    def disagreements(self) -> list[str]:
        out = []
        owners = split_bar(self.c["owner"])
        if len(self.accounts) > 1:
            by_owner = defaultdict(list)
            for a in self.accounts:
                by_owner[a["owner"]].append(a["account_id"])
            if len(by_owner) > 1:
                out.append("- crm_accounts.csv: two accounts, two owners: "
                           + "; ".join(f"{', '.join(ids)} -> {o or 'nobody'}" for o, ids in by_owner.items()))
            stages = {a["stage"] for a in self.accounts}
            if len(stages) > 1:
                out.append("- crm_accounts.csv: the accounts disagree on stage: "
                           + "; ".join(f"{a['account_id']} {a['stage']}" for a in self.accounts))
        elif len(owners) > 1:
            out.append(f"- golden_companies.csv: owners disagree: {self.c['owner']}")

        n_paths = len(self.paths)
        for r in self.requests:
            rid, status = r["request_id"], r["status_as_filed"]
            f = self.d.filed.get(rid)
            logged = self.intro_logged(rid)
            outs = self.d.outcomes.get(rid, [])
            if f and f["status"] != status:
                out.append(f"- {rid}: intro_requests.csv now says \"{f['status']}\"; golden_requests.csv filed it as \"{status}\"")
            if status == "Intro sent" and not logged:
                out.append(f"- {rid}: filed \"Intro sent\" but intro_outcomes.csv has "
                           + (f"no intro (asked {outs[0]['connector_asked']}, intro_sent={outs[0]['intro_sent']})" if outs
                              else "no row at all"))
            if status == "Closed - no path" and n_paths:
                out.append(f"- {rid}: filed \"Closed - no path\" but supply_reach.csv has {n_paths} path"
                           f"{'s' if n_paths != 1 else ''} into {self.c['company_name']}")
            if status in OPEN_STATUSES and logged:
                out.append(f"- {rid}: filed \"{status}\" but intro_outcomes.csv says {logged['connector_asked']} "
                           f"sent the intro on {logged['intro_date']}")
            if f:
                flag = f["path_found_flag"]
                if flag == "No path found" and n_paths:
                    out.append(f"- {rid}: intro_requests.csv path_found_flag=\"No path found\" but supply_reach.csv has {n_paths} paths")
                if flag == "Path found" and not n_paths:
                    out.append(f"- {rid}: intro_requests.csv path_found_flag=\"Path found\" but supply_reach.csv has no path")
            if r["routed_to"] and outs and all(o["connector_asked"] != r["routed_to"] for o in outs):
                out.append(f"- {rid}: routed to {r['routed_to']} in golden_requests.csv but intro_outcomes.csv shows "
                           f"{', '.join(o['connector_asked'] for o in outs)} asked")
            for m in self.offers(rid):
                if not self.asked(rid, m["user"]):
                    out.append(f"- {rid}: {m['user']} offered in slack_threads.jsonl on {m['ts'][:10]} "
                               f"(\"{m['text']}\") but intro_outcomes.csv never asked them")
        return out

    # -- section 3 --------------------------------------------------------------
    def reach(self) -> list[str]:
        if not self.paths:
            return ["nobody in the network reaches this company"]
        out = ["ranked by route score = strength x focus fit x delivery rate, the allocator's sort key", "",
               "| route score | strength | connector | reach | contact | evidence |", "|---|---|---|---|---|---|"]
        for p in self.paths:
            contact = " — ".join(x for x in (p["contact_name"], p["contact_title"]) if x) or "?"
            reach = p["reach_type"] + (" (board seat)" if p["board_seat"] == "yes" else "")
            out.append(f"| {self.route_score(p):.3f} | {float(p['strength']):.3f} | {p['connector']} ({p['connector_type']}) "
                       f"| {reach} | {contact} | {p['evidence']} |")
        why = self.bypass()
        if why:
            out += ["", f"strongest path, not where it went: {why}"]
        return out

    # -- section 4 --------------------------------------------------------------
    def events(self) -> list[Event]:
        evs: list[Event] = []
        titles_seen: dict[str, tuple[str, date]] = {}
        for r in self.requests:
            rid = r["request_id"]
            f = self.d.filed.get(rid, {})
            when = parse_date(r["request_date"]) or self.today
            role = f.get("requester_role", "")
            status = r["status_as_filed"]
            logged = self.intro_logged(rid)
            mark = PLAIN
            notes = []
            if status == "Intro sent" and not logged:
                mark, notes = WARN, [*notes, "no intro in intro_outcomes.csv"]
            elif status == "Closed - no path" and self.paths:
                mark, notes = WARN, [*notes, f"{len(self.paths)} paths in supply_reach.csv"]
            title = r["target_title"]
            if title in titles_seen:
                prev, prev_when = titles_seen[title]
                mark = WARN
                notes.append(f"same title as {prev}, {(when - prev_when).days} days earlier")
            else:
                titles_seen[title] = (rid, when)
            what = (f"{rid} raised by {r['requested_by']}" + (f" ({role})" if role else "")
                    + f": wants {title or '?'}, {money(r['value_usd'])}, {r['urgency_declared'] or '?'} urgency,"
                    f" filed \"{status}\"")
            if notes:
                what += "  [" + "; ".join(notes) + "]"
            evs.append(Event(when, SOURCES["requests"], r["requested_by"], what, mark, rid, 0))

            t = self.d.threads.get(rid)
            for m in (t["messages"] if t else []):
                text = m["text"].strip()
                mk, what = PLAIN, f"{rid} slack: \"{text}\""
                if OFFER_RE.search(text):
                    mk = OFFER
                    if not self.asked(rid, m["user"]):
                        what += "  [never taken up]"
                evs.append(Event(parse_date(m["ts"]) or when, SOURCES["slack"], m["user"], what, mk, rid, 1))

            for o in self.d.outcomes.get(rid, []):
                who = o["connector_asked"]
                asked_on = parse_date(o["asked_date"])
                if asked_on:
                    evs.append(Event(asked_on, SOURCES["outcomes"], who, f"{rid} asked", PLAIN, rid, 2))
                replied_on = parse_date(o["response_date"])
                if o["responded"] == "Y":
                    evs.append(Event(replied_on or asked_on or self.today, SOURCES["outcomes"], who,
                                     f"{rid} replied" + (f" ({(replied_on - asked_on).days} days after the ask)"
                                                         if replied_on and asked_on else ""), WORKED, rid, 2))
                elif asked_on:
                    evs.append(Event(self.today, SOURCES["outcomes"], who,
                                     f"{rid} never replied (asked {asked_on.isoformat()}, {days_ago(asked_on, self.today)})",
                                     MISSED, rid, 2))
                intro_on = parse_date(o["intro_date"])
                if o["intro_sent"] == "Y":
                    evs.append(Event(intro_on or replied_on or self.today, SOURCES["outcomes"], who,
                                     f"{rid} intro sent", WORKED, rid, 2))
                elif o["responded"] == "Y":
                    evs.append(Event(self.today, SOURCES["outcomes"], who,
                                     f"{rid} said yes {days_ago(replied_on, self.today)} and never forwarded",
                                     MISSED, rid, 2))
                if o["meeting_booked"] == "Y":
                    evs.append(Event(intro_on or self.today, SOURCES["outcomes"], who, f"{rid} meeting booked", WORKED, rid, 3))
                if o["opportunity_created"] == "Y":
                    evs.append(Event(intro_on or self.today, SOURCES["outcomes"], who,
                                     f"{rid} opportunity created, {money(o['opportunity_value_usd'])}", WORKED, rid, 3))

        touch, acct = self.last_touch()
        if touch and acct:
            stale = (self.today - touch).days
            evs.append(Event(touch, SOURCES["crm"], acct["owner"] or "nobody",
                             f"last CRM touch on {acct['account_id']}" +
                             (f"  [{stale} days ago, nothing since]" if stale >= STALE_TOUCH_DAYS else ""),
                             WARN if stale >= STALE_TOUCH_DAYS else PLAIN, "", 4))
        return evs

    def chronology(self) -> list[str]:
        evs = self.events()
        if not evs:
            return ["nothing on record"]
        blocks: dict[str, list[Event]] = defaultdict(list)
        for e in evs:
            blocks[e.request_id].append(e)
        # blocks ordered by their first event; the CRM touch (no request) goes last
        ordered = sorted(blocks.items(), key=lambda kv: (kv[0] == "", min(e.when for e in kv[1]), kv[0]))
        out = ["```"]
        for i, (_, es) in enumerate(ordered):
            if i:
                out.append("")
            out.extend(e.line() for e in sorted(es, key=lambda e: (e.when, e.order)))
        out.append("```")
        return out

    # -- section 5 --------------------------------------------------------------
    def next_steps(self) -> list[Step]:
        steps: dict[str, Step] = {}

        def add(order: int, who: str, action: str, why: str, rids: list[str], role: str = "") -> None:
            s = steps.get(who)
            if s is None:
                steps[who] = Step(order, who, role or self.role_of(who), action, why, list(rids))
                return
            if order < s.order:
                s.order = order
            if action not in s.action.split("; "):
                s.action += f"; {action}"
            s.why += f"; {why}"
            s.request_ids += [r for r in rids if r not in s.request_ids]

        for r in self.requests:
            rid = r["request_id"]
            for m in self.offers(rid):
                if not self.asked(rid, m["user"]):
                    add(1, m["user"], "take them up on it",
                        f"offered on {m['ts'][:10]} (\"{m['text']}\") and was never asked — free, they already said yes", [rid])
        for r in self.requests:
            rid = r["request_id"]
            for o in self.d.outcomes.get(rid, []):
                if o["responded"] == "Y" and o["intro_sent"] != "Y":
                    add(2, o["connector_asked"], "nudge, don't re-ask",
                        f"said yes on {o['response_date']} and never forwarded", [rid])
        for rid, a in self.allocated.items():
            add(3, a["allocated_to"], f"send the ask (batch {a['batch_id']})",
                f"allocated in golden_allocation.csv via {a['path_type']} path"
                + (f" to {a['contact_name']}" if a["contact_name"] else "") + f", score {a['route_score']}", [rid])
        touch, acct = self.last_touch()
        if acct and acct["owner"] and touch and (self.today - touch).days >= STALE_TOUCH_DAYS:
            add(4, acct["owner"], "check in on the account",
                f"last touch {touch.isoformat()}, {(self.today - touch).days} days ago", [], role=f"CRM owner ({acct['account_id']})")

        waiting: dict[str, list[dict]] = defaultdict(list)
        for r in self.requests:
            rid = r["request_id"]
            closed_for_real = r["status_as_filed"] == "Closed - no path" and not self.paths
            if not closed_for_real and not self.intro_logged(rid):
                waiting[r["requested_by"]].append(r)
        if waiting:
            def waited(r: dict) -> int:
                return (self.today - (parse_date(r["request_date"]) or self.today)).days

            longest = {rep: max(waited(r) for r in rs) for rep, rs in waiting.items()}
            reps = sorted(waiting, key=lambda rep: (-longest[rep], rep))
            rids = [r["request_id"] for rep in reps for r in sorted(waiting[rep], key=waited, reverse=True)]
            holders = []
            for rep in reps:
                for r in waiting[rep]:
                    alloc = self.allocated.get(r["request_id"])
                    h = r["routed_to"] or (alloc["allocated_to"] if alloc else "")
                    if h and h not in holders:
                        holders.append(h)
            n = len(reps)
            steps["\u0000reps"] = Step(
                5, ", ".join(f"{rep} ({longest[rep]} days)" for rep in reps),
                f"{n} rep{'s' if n != 1 else ''} still waiting, longest first",
                f"tell them it's with {' / '.join(holders)}" if holders else "tell them nobody has it",
                f"{n} rep{'s' if n != 1 else ''} raised this and {'have' if n != 1 else 'has'} heard nothing; "
                f"the oldest has been waiting {max(longest.values())} days", rids)
        return sorted(steps.values(), key=lambda s: (s.order, s.who))

    def next_steps_table(self) -> list[str]:
        steps = self.next_steps()
        if not steps:
            return ["nobody needs to do anything"]
        out = ["| # | who | role | action | why | requests |", "|---|---|---|---|---|---|"]
        for i, s in enumerate(steps, 1):
            out.append(f"| {i} | {s.who} | {s.role} | {s.action} | {s.why} | {', '.join(s.request_ids) or '—'} |")
        return out

    # -- section 6 --------------------------------------------------------------
    @staticmethod
    def orbit_route(r: dict) -> str:
        """How the person could be reached, as the table prints it."""
        via = r["reachable_via"]
        if via == REACHABLE_AS_CONNECTOR:
            return "on the roster"
        if via:
            return "via " + ", ".join(split_bar(via))
        return NO_WARM_PATH

    def orbit_table(self) -> list[str]:
        n_cold = sum(1 for r in self.orbit if not r["reachable_via"])
        out = [f"{len(self.orbit)} {'person' if len(self.orbit) == 1 else 'people'} from investor_network.csv, "
               f"{n_cold} with no warm path; read-only: not scored, not allocated, not on supply_reach.csv", "",
               "| person | role | fund | board seat | source | warm path |", "|---|---|---|---|---|---|"]
        for r in self.orbit:
            out.append(f"| {r['person']} | {r['role']} | {r['fund']} | {r['board_seat']} | {r['source']} | {self.orbit_route(r)} |")
        return out

    # -- all --------------------------------------------------------------------
    def render(self) -> str:
        n_req = len(self.requests)
        sections = [self.header()]
        dis = self.disagreements()
        if dis:
            sections.append(["## 2. Where the files disagree", "", *dis])
        sections.append(["## 3. Who can reach them", "", *self.reach()])
        sections.append([f"## 4. Chronology ({len(self.events())} events, {n_req} request{'s' if n_req != 1 else ''},"
                         f" as of {self.today.isoformat()})", "",
                         *self.chronology()])
        sections.append(["## 5. Next steps, by person, cheapest first", "", *self.next_steps_table()])
        if self.orbit:
            sections.append(["## 6. Additional Investor and Operator Network", "", *self.orbit_table()])
        return "\n\n".join("\n".join(s) for s in sections) + "\n"

    def as_dict(self) -> dict:
        """The same five sections as data, for the dashboard."""
        c = self.c
        evs = self.events()
        blocks: dict[str, list[Event]] = defaultdict(list)
        for e in evs:
            blocks[e.request_id].append(e)
        ordered = sorted(blocks.items(), key=lambda kv: (kv[0] == "", min(e.when for e in kv[1]), kv[0]))
        return {
            "company_id": c["company_id"],
            "company_name": c["company_name"],
            "search": " ".join([c["company_id"], c["company_name"], *self.spellings(), *split_bar(c["crm_account_ids"])]),
            "header": {
                "stage": c["stage"], "industry": c["industry"], "owner": c["owner"],
                "value_usd": money(c["value_usd"]), "largest_request_usd": money(c["largest_request_usd"]) if c["largest_request_usd"] else "",
                "crm_account_ids": c["crm_account_ids"], "domain": c["domain"], "duplicate_accounts": c["duplicate_accounts"],
                "also_known_as": self.spellings(),
                "routing": self.routing(),
                "requests": len(self.requests),
                "people": len({r["requested_by"] for r in self.requests}),
                "titles": sorted({r["target_title"] for r in self.requests if r["target_title"]}),
            },
            "disagreements": [d[2:] for d in self.disagreements()],
            "reach": [{"route_score": round(self.route_score(p), 3), "strength": float(p["strength"]),
                       "fit": round(self.fit_of(p["connector"]), 2), "rate": round(self.rate_of(p["connector"]), 3),
                       "connector": p["connector"], "connector_type": p["connector_type"],
                       "reach_type": p["reach_type"] + (" (board seat)" if p["board_seat"] == "yes" else ""),
                       "contact_name": p["contact_name"], "contact_title": p["contact_title"], "evidence": p["evidence"],
                       "bypass": self.bypass() if p is self.strongest() else ""}
                      for p in self.paths],
            "as_of": self.today.isoformat(),
            "chronology": [[{"mark": e.mark, "date": e.when.isoformat(), "source": e.source, "who": e.who, "what": e.what,
                             "request_id": e.request_id} for e in sorted(es, key=lambda e: (e.when, e.order))]
                           for _, es in ordered],
            "next_steps": [{"order": s.order, "who": s.who, "role": s.role, "action": s.action, "why": s.why,
                            "request_ids": s.request_ids} for s in self.next_steps()],
            "orbit": [{"person": r["person"], "role": r["role"], "fund": r["fund"], "board_seat": r["board_seat"] == "yes",
                       "source": r["source"], "reachable_via": r["reachable_via"], "route": self.orbit_route(r)}
                      for r in self.orbit],
        }


def all_traces(today: date | None = None) -> list[dict]:
    """as_dict() for every company with a request, most-requested first."""
    data = Data.load()
    today = today or date.today()
    companies = [c for c in data.companies if int(c["total_requests"] or 0)]
    companies.sort(key=lambda c: (-int(c["total_requests"]), c["company_name"]))
    return [Trace(data, c, today).as_dict() for c in companies]


# ---------------------------------------------------------------------------
# entry points
# ---------------------------------------------------------------------------
def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def write_all(today: date | None = None) -> list[Path]:
    """One trace per company with at least one request -> analysis/traces/."""
    data = Data.load()
    today = today or date.today()
    TRACES.mkdir(exist_ok=True)
    written = []
    for c in data.companies:
        if int(c["total_requests"] or 0) == 0:
            continue
        path = TRACES / f"{c['company_id']}-{slug(c['company_name'])}.md"
        path.write_text(Trace(data, c, today).render(), encoding="utf-8")
        written.append(path)
    print(f"wrote {len(written)} traces to {TRACES.relative_to(ROOT)}/")
    return written


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("company", nargs="?", help="name, alias, id (C018) or CRM account id (A1050)")
    ap.add_argument("--as-of", default=date.today().isoformat())
    args = ap.parse_args(argv)
    today = parse_date(args.as_of) or date.today()
    if not args.company:
        write_all(today)
        return
    data = Data.load()
    company = find_company(data, args.company)
    if company is None:
        sys.exit(f"no single company matches {args.company!r}; try the id from golden/golden_companies.csv")
    sys.stdout.write(Trace(data, company, today).render())


if __name__ == "__main__":
    main(sys.argv[1:])
