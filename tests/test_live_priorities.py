"""The Live Priorities tab (dashboard/live_priorities.py + .js).

    python3 -m unittest tests.test_live_priorities

Three things are checked:

  1. the payload the page embeds — every section computed in Python, the browser
     only renders — states the facts the golden files state: allocations and
     exceptions by reason, live-intro retries, responded-but-no-intro asks,
     importer-shaped CRM columns, and a Company Trace link on every company.
  2. the upload preview parses like the build: the JavaScript parser (run under
     node) picks the same target and resolves it the same way as golden/parse.py
     + golden/resolver.py on every Slack first message and every raw_ask.
  3. `build_golden.py --threads FILE` — the command the page shows — files the
     previewed threads as requests, keeps them on a later plain rebuild, and
     lands the same company_id and offer the preview showed.
"""
from __future__ import annotations

import csv
import inspect
import json
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dashboard import live_priorities as lp  # noqa: E402
from dashboard import request_state as rs  # noqa: E402
from dashboard.sankey_funnel import funnel_stages  # noqa: E402
from golden import build_golden as bg  # noqa: E402
from golden import parse as gp  # noqa: E402
from golden.resolve_cli import load_resolver  # noqa: E402

AS_OF = date(2026, 9, 5)
NODE = shutil.which("node")

NEW_THREADS = [
    {"request_id": "R2001", "messages": [
        {"ts": "2026-09-03T10:00:00Z", "user": "Sloane Fairweather",
         "text": "who do we know at Harrowgate Health? we need a path to their CTO"},
        {"ts": "2026-09-03T10:05:00Z", "user": "Owen Trask", "text": "happy to intro — I met their CTO last year"}]},
    {"request_id": "R2002", "messages": [
        {"ts": "2026-09-03T11:00:00Z", "user": "Sloane Fairweather",
         "text": "anyone connected to Jo Bloggs? They run engineering somewhere big."}]},
    {"request_id": "R2003", "messages": [
        {"ts": "2026-09-04T09:00:00Z", "user": "Bea Marsh",
         "text": "we need Kingsmere Retail Group. email domain is kingsmereretail.com"},
        {"ts": "2026-09-04T09:10:00Z", "user": "Bea Marsh", "text": "+1"}]},
    {"request_id": "R2004", "messages": [
        {"ts": "2026-09-04T10:00:00Z", "user": "Bea Marsh", "text": "how about Xanthe Labs"}]},
    {"request_id": "R1034", "messages": [
        {"ts": "2026-05-01T09:00:00Z", "user": "x", "text": "a thread for a request already on file"}]},
]


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_node(parser: dict, texts: list[str], threads: list[dict]) -> dict:
    jsonl = "".join(json.dumps(t) + "\n" for t in threads)
    proc = subprocess.run([NODE, str(ROOT / "tests" / "lp_parity.js")],
                          input=json.dumps({"parser": parser, "texts": texts, "threads": jsonl}),
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


class PayloadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.P = lp.payload(AS_OF)
        cls.trace_ids = {t["company_id"] for t in json.loads(
            (ROOT / "docs" / "companytrace.html").read_text(encoding="utf-8")
            .split('<script id="trace-data" type="application/json">')[1].split("</script>")[0])} \
            if (ROOT / "docs" / "companytrace.html").exists() else None

    def every_ref(self):
        """Every {company_id, company_name, href} triple anywhere in the payload."""
        def walk(v):
            if isinstance(v, dict):
                if "href" in v and "company_id" in v:
                    yield v
                for x in v.values():
                    yield from walk(x)
            elif isinstance(v, list):
                for x in v:
                    yield from walk(x)
        return list(walk({k: v for k, v in self.P.items() if k != "parser"}))

    def test_every_company_links_to_the_trace_tab(self):
        refs = self.every_ref()
        self.assertGreater(len(refs), 100)
        for r in refs:
            if r["company_id"]:
                self.assertEqual(r["href"], f"{lp.TRACE_PAGE}#{r['company_id']}", r)
                if self.trace_ids is not None:
                    self.assertIn(r["company_id"], self.trace_ids, "the trace tab must know this company")
            else:
                self.assertEqual(r["href"], "", "an unresolved company has nothing to link to")

    def test_stages_are_point_in_time(self):
        S = self.P["stages"]
        self.assertEqual([s["stage"] for s in S["stages"]],
                         ["needs data", "to be routed", "routed", "asked", "introduced", "meeting booked"])
        reqs = read_csv(ROOT / "golden" / "golden_requests.csv")
        companies = {r["company_id"] for r in reqs if r["company_id"]}
        unresolved = [r for r in reqs if not r["company_id"]]
        self.assertEqual(sum(s["count"] for s in S["stages"]) + S["excluded"]["count"], len(companies) + len(unresolved),
                         "each company lands in exactly one stage (or is excluded as Closed - no path); "
                         "a request with no company stands alone")
        self.assertEqual(sum(s["unresolved"] for s in S["stages"]) + S["excluded"]["unresolved"], len(unresolved))
        self.assertEqual(S["total"]["companies"] + S["total"]["unresolved"], S["total"]["count"])
        self.assertEqual(S["excluded"]["stage"], "closed")

    def test_every_dollar_on_the_page_is_the_companys_one_dollar(self):
        """One traceable $ per company everywhere on Live Priorities: CRM ARR
        potential, else the latest request carrying a deal value. The request's own
        $ lives only on the Company Trace hover."""
        L = lp.Live(AS_OF)
        P = lp.payload(AS_OF)
        seen = 0

        def walk(o, where):
            nonlocal seen
            if isinstance(o, dict):
                cid, fmt = o.get("company_id"), o.get("value_fmt")
                if cid and fmt:
                    seen += 1
                    self.assertEqual(fmt, lp.money(L.company_value(cid)[0]), f"{where}: {o.get('request_id') or o.get('company_name')}")
                for k, v in o.items():
                    walk(v, f"{where}.{k}")
            elif isinstance(o, list):
                for x in o:
                    walk(x, where + "[]")
        walk({k: v for k, v in P.items() if k != "parser"}, "payload")
        self.assertGreater(seen, 50)
        for g in P["crm"]["groups"]:
            self.assertEqual(g["value_fmt"], lp.money(L.dollars_total(g["rows"])), g["group"])
        for r in P["priorities"]["top"]:
            self.assertEqual(r["on_roster"], r["connector"] in L.roster, r["request_id"])
        self.assertTrue(any(r["on_roster"] for r in P["priorities"]["top"]))

    def test_stage_dollars_are_one_value_per_company(self):
        """CRM ARR potential first, else the latest request's deal value; never the
        sum of a company's requests. A company with a meeting booked stays there whatever
        else is open on it."""
        L = lp.Live(AS_OF)
        cos = read_csv(ROOT / "golden" / "golden_companies.csv")
        by_stage = {s["stage"]: s for s in self.P["stages"]["stages"]}
        expect = Counter()
        for c in cos:
            cid = c["company_id"]
            if cid not in L.by_company:
                continue
            stage = L.company_stage(cid)
            reqs = sorted(L.by_company[cid], key=lambda r: (r["request_date"], r["request_id"]))
            if c["crm_account_ids"] and int(c["value_usd"] or 0):
                value = int(c["value_usd"])
            else:
                value = next((int(r["value_usd"]) for r in reversed(reqs) if r["value_usd"]), 0)
            self.assertEqual(L.company_value(cid)[0], value, cid)
            stages = {L.stage_of(r) for r in reqs}
            if "meeting booked" in stages:
                self.assertEqual(stage, "meeting booked", f"{cid} has a meeting booked, whatever else is open")
            if stage != "closed":
                expect[stage] += value
        for r in L.requests:
            if not r["company_id"] and L.stage_of(r) != "closed":
                expect[L.stage_of(r)] += lp.usd(r["value_usd"])
        for s, usd in expect.items():
            self.assertEqual(by_stage[s]["usd"], usd, s)
        # the strip is strictly less than summing every request's deal value
        self.assertLess(sum(s["usd"] for s in by_stage.values()),
                        sum(lp.usd(r["value_usd"]) for r in L.requests if L.stage_of(r) != "closed"))

    def test_top_five_is_the_stated_formula(self):
        T = self.P["priorities"]
        self.assertEqual(len(T["top"]), 5)
        evs = [r["expected_value"] for r in T["top"]]
        self.assertEqual(evs, sorted(evs, reverse=True))
        for r in T["top"]:
            c = r["components"]
            rp = c["deal_value_musd"] * c["stage_weight"] * c["age"] * c["reps_waiting"]
            cs = c["path_strength"] * c["focus_fit"] * c["delivery_rate"] * c["title_fit"] * c["capacity_left"]
            self.assertAlmostEqual(r["request_priority"], rp, places=2, msg=r["request_id"])
            self.assertAlmostEqual(r["connector_score"], cs, places=2, msg=r["request_id"])
            self.assertAlmostEqual(r["expected_value"], rp * cs, places=2, msg=r["request_id"])
            self.assertEqual(c["reps_waiting"], len(r["reps"]))
            self.assertLessEqual(c["age"], 2.0)
        self.assertIn("request priority × connector score", T["formula"]["expected_value"])
        self.assertEqual(T["formula"]["stage_weight"]["Negotiation"], lp.STAGE_WEIGHT["Negotiation"])

    def test_the_considered_count_splits_by_why_each_request_is_in_the_queue(self):
        """The header's N live requests = allocated this cycle + routed with no slot +
        held on an unresolved ask + asked already (a retry the allocator ranked but
        could not seat, so its request_state stays asked), each split saying how many
        are retries."""
        T, A, L = self.P["priorities"], self.P["asks"], lp.Live(AS_OF)
        ranked = L.ranked()
        self.assertEqual(sum(b["count"] for b in T["considered_by"]), T["considered"], "every ranked request in one split")
        self.assertEqual(sorted(rid for b in T["considered_by"] for rid in b["request_ids"]), sorted(r["request_id"] for r in ranked))
        by = {b["key"]: b for b in T["considered_by"]}
        self.assertEqual([b["key"] for b in T["considered_by"]], [k for k, _ in lp.CONSIDERED_BY if k in by], "header order")
        self.assertEqual(by["allocated"]["count"], A["allocated"], "the Current Asks total")
        self.assertEqual(by["no_slot"]["count"], A["no_slot"], "the Current Asks no-slot count")
        self.assertEqual(sorted(by["allocated"]["request_ids"]), sorted(r["request_id"] for r in ranked if r["allocated"]))
        held = {r["request_id"] for e in A["exceptions"] if e["reason"] == bg.UNRESOLVED_ASK for r in e["rows"]}
        self.assertEqual(set(by.get("held", {"request_ids": []})["request_ids"]), held & {r["request_id"] for r in ranked})
        self.assertNotIn("other", by, "every ranked request is allocated, out of slots, held, or asked already")
        retry = {r["request_id"] for r in ranked if r["retry"]}
        asked = {rid for rid, s in L.states.items() if s == rs.ASKED}
        self.assertEqual(set(by.get("asked", {"request_ids": []})["request_ids"]),
                         {r["request_id"] for r in ranked if not r["allocated"]} & asked, "asked retries left without a slot")
        self.assertTrue(set(by.get("asked", {"request_ids": []})["request_ids"]) <= retry, "only a retry can be asked already")
        for b in T["considered_by"]:
            self.assertEqual(b["retries"], len(retry & set(b["request_ids"])), b["key"])
            self.assertEqual(b["label"], dict(lp.CONSIDERED_BY)[b["key"]])
        self.assertEqual(sum(b["retries"] for b in T["considered_by"]), len(retry))
        self.assertEqual(by["allocated"]["retries"], self.P["introduced"]["retry_requests"], "the Already Introduced retries")

    def test_current_asks_match_golden_allocation(self):
        A, L = self.P["asks"], lp.Live(AS_OF)
        alloc = read_csv(ROOT / "golden" / "golden_allocation.csv")
        allocated = [r for r in alloc if r["allocated_to"]]
        self.assertEqual(A["allocated"], len(allocated))
        self.assertEqual(len(A["batches"]), len({r["batch_id"] for r in allocated}))
        self.assertEqual(sum(len(c["request_ids"]) for b in A["batches"] for c in b["companies"]), A["allocated"])
        for b in A["batches"]:
            self.assertEqual(b["size"], sum(len(c["request_ids"]) for c in b["companies"]))
            for c in b["companies"]:
                self.assertTrue(c["wanted"], "every person wanted, not just one")
                self.assertTrue(c["waiting"] and c["path_type"] and c["why"])
        self.assertEqual(sorted(c["company_id"] for c in A["all"]),
                         sorted(c["company_id"] for b in A["batches"] for c in b["companies"]),
                         "the Aggregate tab is every batch's companies")
        values = [c["value_usd"] for c in A["all"]]
        self.assertEqual(values, sorted(values, reverse=True), "biggest first")
        self.assertEqual(sum(len(c["request_ids"]) for c in A["all"]), A["allocated"])
        self.assertTrue(all(c["connector"] and c["slug"] and c["batch_id"] for c in A["all"]))
        # the exceptions section is the classified table (request_state.state, the one Live Data groups
        # by) filtered to the states an exception_reason names: an allocation row whose request is in the
        # ask log is "asked" and not listed, so the 3 capacity-exhausted rows already asked (and the one
        # unresolved-ask row) are not exceptions here. Capacity exhausted is not an exception either: those
        # requests have a connector and an expected value, so their one home is the ranked list
        self.assertEqual((A["on_file"], A["cycle_size"]),
                         (len(L.requests), len(bg.latest_cycle(alloc))),
                         "the two populations the page states counts against")
        states = L.states
        by_state = Counter(states[a["request_id"]] for a in bg.latest_cycle(alloc))
        no_slot = [a for a in bg.latest_cycle(alloc) if states[a["request_id"]] == bg.CAPACITY_EXHAUSTED]
        self.assertEqual(A["no_slot"], len(no_slot))
        self.assertEqual(A["exception_count"],
                         len(bg.latest_cycle(alloc)) - by_state[rs.ASKED] - by_state[rs.ALLOCATED] - len(no_slot))
        expected_exceptions = Counter(
            states[a["request_id"]] for a in bg.latest_cycle(alloc)
            if states[a["request_id"]] not in (rs.ASKED, rs.ALLOCATED, bg.CAPACITY_EXHAUSTED)
        )
        self.assertEqual({e["reason"]: e["count"] for e in A["exceptions"]},
                         dict(expected_exceptions))
        self.assertEqual(A["repair_days"], bg.REPAIR_DAYS)
        for e in A["exceptions"]:
            for r in e["rows"]:
                self.assertEqual(states[r["request_id"]], e["reason"], "grouped by the same state Live Data's cuts use")
        ranked = {r["request_id"] for r in L.ranked()}
        self.assertTrue(all(a["request_id"] in ranked for a in no_slot), "every no-slot request is on the ranked list")
        parked = {a["request_id"] for a in alloc
                  if a["exception_reason"].startswith((bg.ALREADY_INTRODUCED, bg.INTRO_CLAIMED_NOT_LOGGED))}
        self.assertTrue(parked and not parked & ranked, "nothing parked on a live intro or in the repair queue is offered as an ask")
        # the requests the allocator took back from Closed - no path / Intro sent say so on every
        # row they land on; the repair queue is the one place a claim is held rather than reopened
        reopened = {a["request_id"]: bg.reopened(a) for a in alloc if a["status_as_filed"] in bg.REOPEN_STATUSES}
        self.assertTrue(any(reopened.values()))
        for r in L.ranked():
            self.assertEqual(r["reopened"], reopened.get(r["request_id"], ""))
        for e in A["exceptions"]:
            for r in e["rows"]:
                self.assertEqual(r["reopened"], reopened.get(r["request_id"], ""))
        repair = next(e for e in A["exceptions"] if e["reason"] == bg.INTRO_CLAIMED_NOT_LOGGED)
        for r in repair["rows"]:
            self.assertRegex(r["detail"], r"^filed Intro sent, no intro in the log, flagged \d{4}-\d{2}-\d{2}, routed as Stalled from \d{4}-\d{2}-\d{2}$")
            self.assertEqual(r["reopened"], "")
        for c in A["all"]:
            self.assertEqual(c["reopened"], "; ".join(f"{rid} {reopened[rid]}" for rid in c["request_ids"] if reopened.get(rid)))
        held = next(e for e in A["exceptions"] if e["reason"] == bg.UNRESOLVED_ASK)
        for r in held["rows"]:
            self.assertRegex(r["detail"], r"agreed on \d{4}-\d{2}-\d{2} \(R1\d{3}\), no intro - nudge|no reply - day \d+ of \d+")
        parked = next(e for e in A["exceptions"] if e["reason"] == "already introduced")
        for r in parked["rows"]:
            self.assertRegex(r["detail"], r"^.+ on \d{4}-\d{2}-\d{2} \(R1\d{3}(, meeting booked)?\)$", "the reason names the intro")
        companies = {c["company_id"]: c for c in read_csv(ROOT / "golden" / "golden_companies.csv")}
        blocked_by_rid = {r["request_id"]: r["blocked_reason"] for r in read_csv(ROOT / "golden" / "golden_requests.csv")}
        for e in A["exceptions"]:
            for r in e["rows"]:
                self.assertEqual(r["blocked_reason"], blocked_by_rid[r["request_id"]], "golden_requests.blocked_reason, rendered as one column")
                if e["reason"] == "company unresolved":
                    self.assertEqual(r["crm_stage"], "")
                else:
                    self.assertEqual(r["crm_stage"], companies[r["company_id"]]["stage"] or "no CRM account")
        # who on the roster covers the sector, on every exception with a company, so the blank
        # cell becomes a named person; the in-focus finding rides on the section header
        for e in A["exceptions"]:
            for r in e["rows"]:
                self.assertEqual(r["sector_cover"] is not None, bool(r["company_id"]), r["request_id"])
        self.assertEqual(A["focus"], L.focus_finding())
        no_path = next(e for e in A["exceptions"] if e["reason"] == "no path to this company in the network")
        by_name = {r["company_name"]: r["sector_cover"] for r in no_path["rows"]}
        self.assertEqual([c["connector"] for c in by_name["Halcyon Grid"]["connectors"]], ["Marcus Aldridge"])
        self.assertEqual([c["connector"] for c in by_name["Pemberton Retail"]["connectors"]], ["Dana Whitfield"])
        self.assertEqual(by_name["Halcyon Grid"]["connectors"][0]["asked"], "", "never asked")
        self.assertEqual(by_name["Sablefield Motors"]["connectors"], [])
        self.assertEqual(by_name["Sablefield Motors"]["note"], "nobody on the roster covers Automotive")

    def test_already_introduced_parks_the_company_and_names_who_extends_it(self):
        """Redtree Foods: Dana's 2026-03-18 intro to Imani (R1003) never booked a
        meeting and is older than INTRO_LIVE_DAYS, so Dana is asked again for
        R1067/R1074 — labelled a retry, naming that intro. A company whose intro
        booked a meeting (or is fresher) is parked instead: no connector slot,
        the rep introduced asks for the other names."""
        P, I, L = self.P, self.P["introduced"], lp.Live(AS_OF)
        self.assertEqual(I["days"], bg.INTRO_LIVE_DAYS)
        alloc = read_csv(ROOT / "golden" / "golden_allocation.csv")
        parked = [a for a in alloc if a["exception_reason"].startswith(bg.ALREADY_INTRODUCED)]
        self.assertEqual(I["requests"], len(parked))
        self.assertEqual(sorted(rid for r in I["rows"] for rid in r["request_ids"]), sorted(a["request_id"] for a in parked))
        self.assertEqual(I["count"], len({a["company_id"] for a in parked}), "one row per company")
        values = [r["value_usd"] for r in I["rows"]]
        self.assertEqual(values, sorted(values, reverse=True))
        outcomes = {o["request_id"]: o for o in read_csv(ROOT / "dataset" / "intro_outcomes.csv")}
        requests = {r["request_id"]: r for r in read_csv(ROOT / "golden" / "golden_requests.csv")}
        for r in I["rows"]:
            i = r["intro"]
            self.assertTrue(i["live"])
            o = outcomes[i["request_id"]]
            self.assertEqual((o["connector_asked"], o["intro_date"], o["meeting_booked"] == "Y"), (i["connector"], i["intro_date"], i["meeting_booked"]))
            self.assertEqual(requests[i["request_id"]]["company_id"], r["company_id"], "the intro is on the same company")
            self.assertEqual(r["owner"], requests[i["request_id"]]["requested_by"], "the rep who received the intro extends it")
            self.assertIn(r["owner"].split()[0], r["action"])
            self.assertTrue(r["wanted"] and r["waiting"] and r["href"])
        # parked companies are out of every fresh-ask surface
        parked_cos = {r["company_id"] for r in I["rows"]}
        fresh = ({r["company_id"] for r in P["priorities"]["top"]}
                 | {c["company_id"] for b in P["asks"]["batches"] for c in b["companies"]}
                 | {q["company_id"] for c in P["connectors"] for q in c["queue"]}
                 | {x["company_id"] for c in P["connectors"] for x in c["companies"]})
        self.assertEqual(parked_cos & fresh, set())
        for m in L.batch_asks:
            self.assertEqual({q["company_id"] for q in m["requests"]} & parked_cos, set(), m["connector"])
        # Redtree: fizzled, so back in the queue as a retry, with the prior intro named on
        # every surface; R1003 itself (the request that intro was for) is back alongside
        redtree = [c for b in P["asks"]["batches"] for c in b["companies"] if c["company_id"] == "C045"]
        self.assertTrue(redtree)
        self.assertEqual(sorted(rid for c in redtree for rid in c["request_ids"]), ["R1003", "R1067", "R1074"])
        self.assertTrue(all(c["retry"] == redtree[0]["retry"] for c in redtree))
        retry = redtree[0]["retry"]
        self.assertEqual((retry["connector"], retry["intro_date"], retry["request_id"], retry["requested_by"], retry["meeting_booked"], retry["live"]),
                         ("Dana Whitfield", "2026-03-18", "R1003", "Imani Mkhize", False, False))
        self.assertGreater(retry["days"], bg.INTRO_LIVE_DAYS)
        self.assertIn("Dana's 2026-03-18 intro of Imani Mkhize to their VP Engineering went nowhere", retry["note"])
        self.assertIn("C045", [r["company_id"] for r in I["retries"]])
        self.assertEqual(I["retry_requests"], sum(len(r["request_ids"]) for r in I["retries"]))
        dana = next(c for c in P["connectors"] if c["connector"] == "Dana Whitfield")
        self.assertTrue(all(q["retry"] for q in dana["queue"] if q["company_id"] == "C045"))
        self.assertIn("retry: you introduced Imani Mkhize to their VP Engineering on 2026-03-18", dana["batch_ask"]["message"])
        # the retry label is the company's fizzled intro, on every fresh-ask surface, and only there
        retried = {x["company_id"] for x in I["retries"]}
        for r in L.ranked():
            self.assertEqual(r["retry"], L.retry_of(r["company_id"]), r["request_id"])
            if r["retry"]:
                self.assertFalse(r["retry"]["live"])
        for b in P["asks"]["batches"]:
            for c in b["companies"]:
                self.assertEqual(c["retry"] is not None, c["company_id"] in retried, c["company_name"])
        for m in L.batch_asks:
            for c in m["companies"]:
                self.assertEqual(c["retry"] is not None, c["company_id"] in retried, c["company_name"])
            self.assertEqual(m["message"].count("retry:") + m["message"].count("for context:"),
                             sum(1 for c in m["companies"] if c["retry"]), m["connector"])

    def test_offers_are_paths_not_a_section(self):
        """An offer in the Slack thread is the strongest reach type the allocator
        scores, so the offerer is the connector on the row; it is not listed again
        as a to-do of its own."""
        self.assertNotIn("offer_gaps", self.P)
        self.assertNotIn("offers", dict(lp.SECTIONS))
        reach = read_csv(ROOT / "golden" / "supply_reach.csv")
        offered = {(r["connector"], r["company_id"]) for r in reach if r["reach_type"] == "offer"}
        self.assertTrue(offered)
        routed = {(r["connector"], r["company_id"]) for r in lp.Live(AS_OF).ranked() if r["path"].startswith("offered in Slack")}
        self.assertTrue(routed and routed <= offered, "an offer row routes to whoever offered")

    def test_an_asked_request_whose_own_intro_fizzled_is_back_on_the_connectors_page(self):
        """Apex Holdings (C003): Marcus's 2026-03-11 intro for R1154 never booked a
        meeting, so R1154 is back in the queue as a retry (not parked behind his
        own ask). Marcus never answered R1069 there (2025-11-01, past the window),
        so his path ranks last and the retry goes to Espen, labelled with Marcus's
        intro; `sitting on` once the retry ask is logged as sent."""
        P = self.P
        marcus = next(c for c in P["connectors"] if c["connector"] == "Marcus Aldridge")
        self.assertNotIn("R1154", [q["request_id"] for q in marcus["queue"]])
        espen = next(a for a in lp.Live(AS_OF).allocation if a["request_id"] == "R1154")
        self.assertEqual(espen["allocated_to"], "Espen Rushworth-Oyelaran")
        q = next(r for r in lp.Live(AS_OF).ranked() if r["request_id"] == "R1154")
        self.assertEqual((q["company_id"], q["connector"], q["retry"]["connector"], q["retry"]["intro_date"], q["retry"]["request_id"]),
                         ("C003", "Espen Rushworth-Oyelaran", "Marcus Aldridge", "2026-03-11", "R1154"))
        self.assertNotIn("R1154", [s["request_id"] for s in marcus["sitting_on"]], "not sent yet: queue, not sitting on")
        self.assertNotIn("R1154", [r["request_id"] for r in P["followups"]["rows"]], "the old reply is not a nudge")
        paths = lp.Live(AS_OF).ranked_paths("C003")
        self.assertEqual([(p["connector"], p["hold"], p["askable"]) for p in paths],
                         [("Espen Rushworth-Oyelaran", "", True), ("Marcus Aldridge", bg.HOLD_LAST, True)],
                         "the roster path ranks behind the network one: its connector sat on an ask here")
        self.assertIn("no reply for", paths[1]["reason"])
        # the retry goes out: an ask_sent completion after the intro files reasked_date
        # and the request moves from the queue to what Marcus is sitting on
        reask = {"completion_id": "R1154:ask_sent:2026-09-05", "completed_at": "2026-09-05T10:15:00+00:00", "completed_by": "vera",
                 "action": bg.ASKED, "request_id": "R1154", "company_id": "", "connector": "Marcus Aldridge", "note": ""}
        with mock.patch.object(bg, "load_completions", return_value=[reask]):
            L = lp.Live(AS_OF)
        o = L.outcome_by_rid["R1154"]
        self.assertEqual((o["asked_date"], o["reasked_date"]), ("2026-03-05", "2026-09-05"))
        self.assertFalse(bg.retriable(o, AS_OF), "re-asked, so not queued again")
        card = L.connector_card("Marcus Aldridge")
        s = next(s for s in card["sitting_on"] if s["request_id"] == "R1154")
        self.assertEqual((s["company_id"], s["asked_date"], s["days_since_asked"], s["responded"], s["action"]),
                         ("C003", "2026-09-05", 0, False, "chase"), "counted from the re-ask, unanswered")
        self.assertEqual((s["retry"]["request_id"], s["retry"]["intro_date"], s["retry"]["requested_by"]),
                         ("R1154", "2026-03-11", "Yusuf Petrossian"))
        self.assertIn("Marcus's 2026-03-11 intro of Yusuf Petrossian to their Head of Platform Engineering went nowhere", s["retry"]["note"])
        self.assertEqual(card["asked_this_cycle"], marcus["asked_this_cycle"] + 1, "the retry spends a slot this cycle")
        self.assertEqual([c["asks"] for c in card["cycles"]][-1], [c["asks"] for c in marcus["cycles"]][-1] + 1)

    def test_a_meeting_with_no_opportunity_in_60_days_releases_the_company_once_newer_requests_wait(self):
        """Apex Logistics (C002): Elena's 2026-06-10 intro for R1038 booked a meeting
        but no opportunity followed, and R1024 was filed after it, so the company is
        no longer parked: R1024 is routed (to Marcus) as a retry whose note says
        why, and the retry table reads the same intro."""
        P, L = self.P, lp.Live(AS_OF)
        i = L.intro_state["C002"]
        self.assertEqual((i["request_id"], i["connector"], i["intro_date"], i["meeting_booked"], i["opportunity"], i["live"]),
                         ("R1038", "Elena Duvall", "2026-06-10", True, False, False))
        self.assertTrue(bg.meeting_stalled(i, ["2026-07-04"]))
        self.assertFalse(bg.meeting_stalled(i, ["2026-06-01"]), "nothing filed since the meeting: still parked")
        self.assertFalse(bg.meeting_stalled({**i, "opportunity": True}, ["2026-07-04"]))
        self.assertFalse(bg.meeting_stalled({**i, "days": bg.INTRO_LIVE_DAYS}, ["2026-07-04"]), "the meeting is still fresh")
        self.assertEqual(i["outcome"], f"meeting booked, no opportunity in {i['days']} days")
        self.assertGreater(i["days"], bg.INTRO_LIVE_DAYS)
        r1024 = next(r for r in L.ranked() if r["request_id"] == "R1024")
        self.assertEqual(r1024["retry"]["request_id"], "R1038")
        self.assertIn("Elena's 2026-06-10 intro of Nadia Okonkwo to their Chief Operating Officer went nowhere: meeting booked, no opportunity", r1024["retry"]["note"])
        marcus = next(c for c in P["connectors"] if c["connector"] == "Marcus Aldridge")
        self.assertIn("R1024", [q["request_id"] for q in marcus["queue"]])
        self.assertIn("C002", {x["company_id"] for x in P["introduced"]["retries"]})
        self.assertNotIn("C002", {r["company_id"] for e in P["asks"]["exceptions"] for r in e["rows"]
                                  if e["reason"] == "already introduced"})
        # a meeting nobody has asked about since keeps parking its company
        held = [cid for cid, i in L.intro_state.items() if i["live"] and i["meeting_booked"] and not i["opportunity"]]
        self.assertTrue(held)
        for cid in held:
            since = [r["request_date"] for r in L.requests if r["company_id"] == cid
                     and r["status_as_filed"] in bg.OPEN_STATUSES and r["request_date"] > L.intro_state[cid]["intro_date"]]
            self.assertTrue(L.intro_state[cid]["days"] <= bg.INTRO_LIVE_DAYS or not since, cid)

    def test_followups_are_every_live_ask_with_no_intro(self):
        """One home for nudges and chases: every connector (roster, off-roster batch
        holders, anyone else in intro_outcomes.csv), oldest ask first, the same
        rows the connector cards carry."""
        F, L = self.P["followups"], lp.Live(AS_OF)
        requests = {r["request_id"]: r for r in read_csv(ROOT / "golden" / "golden_requests.csv")}
        expect = [o for o in L.outcomes if (o["intro_sent"].strip() != "Y" or o["reasked_date"])
                  and requests[o["request_id"]]["status_as_filed"] in bg.OPEN_STATUSES]
        self.assertEqual(len(F["rows"]), len(expect), 42)
        self.assertEqual(F["count"], len(F["rows"]) - len(F["quiet"]))
        self.assertEqual(F["nudge"] + F["chase"], F["count"])
        self.assertEqual(F["nudge"], sum(1 for o in expect if o["responded"].strip() == "Y" and not o["reasked_date"]), 19)
        self.assertEqual(F["chase"], 23)
        self.assertEqual(F["quiet_days"], lp.NUDGE_QUIET_DAYS)
        live = [r for r in F["rows"] if not r["quiet"]]
        self.assertEqual([r["asked_date"] for r in live], sorted(r["asked_date"] for r in live), "oldest ask first")
        self.assertEqual([r["quiet"] for r in F["rows"]], sorted(r["quiet"] for r in F["rows"]), "quiet rows last")
        for r in F["rows"]:
            self.assertEqual(r["action"], "nudge" if r["responded"] else "chase")
            self.assertEqual(bool(r["agreed_date"]), r["responded"], "agreed is when they said yes")
            self.assertGreaterEqual(r["days_since_asked"], 0)
            if r["company_id"]:
                self.assertEqual((r["value_usd"], r["value_source"]), L.company_value(r["company_id"]),
                                 f"{r['request_id']}: the company's one $ as on Company Trace, not the request's")
        # the per-connector tabs partition the rows; anyone with a row is a tab, roster first
        names = [c["connector"] for c in F["by_connector"]]
        self.assertEqual(names[:len(L.roster)], list(L.roster))
        self.assertIn("Hana Nakashima", names, "off the roster and holding no batch, still owes a follow-up")
        self.assertEqual(sorted(r["request_id"] for c in F["by_connector"] for r in c["rows"]), sorted(r["request_id"] for r in F["rows"]))
        for c in F["by_connector"]:
            self.assertTrue(c["rows"], "no empty tabs")
            self.assertTrue(all(r["connector"] == c["connector"] for r in c["rows"]))
            self.assertEqual(c["count"], c["nudge"] + c["chase"])
            self.assertEqual(c["on_roster"], c["connector"] in L.roster)
        # the same rows the connector cards carry: one computation, two views
        for c in self.P["connectors"]:
            mine = next((x for x in F["by_connector"] if x["connector"] == c["connector"]), None)
            self.assertEqual(c["sitting_on"], mine["rows"] if mine else [])
        # the unresolved-ask exception is named on the row that holds it up
        held = {r["request_id"] for e in self.P["asks"]["exceptions"] if e["reason"] == bg.UNRESOLVED_ASK for r in e["rows"]}
        self.assertEqual({rid for r in F["rows"] for rid in r["blocking"]}, held)
        self.assertNotIn("value_fmt", F, "no request-value total on the section")

    def test_in_flight_puts_every_open_request_in_one_state_the_sections_agree_on(self):
        """The Live Data table: every open request once (filed open, or in the allocator's
        cycle whatever it was filed under), and each state's count is the one the owning
        section of this tab already shows."""
        P, F = self.P, self.P["in_flight"]
        requests = read_csv(ROOT / "golden" / "golden_requests.csv")
        current = rs.current_allocation(read_csv(ROOT / "golden" / "golden_allocation.csv"))
        open_ids = sorted(r["request_id"] for r in requests
                          if r["status_as_filed"] in bg.OPEN_STATUSES or r["request_id"] in current)
        self.assertEqual(F["open"], len(open_ids))
        filed_open = sum(1 for r in requests if r["status_as_filed"] in bg.OPEN_STATUSES)
        reopened = sum(1 for r in requests if r["status_as_filed"] not in bg.OPEN_STATUSES and r["request_id"] in current)
        self.assertEqual(F["open"], filed_open + reopened, "the never-asked Closed - no path / Intro sent rows in the cycle are in flight too")
        self.assertEqual(sorted(rid for r in F["rows"] for rid in r["request_ids"]), open_ids, "each open request in exactly one state")
        self.assertEqual(sum(r["count"] for r in F["rows"]), F["open"])
        self.assertEqual(sum(g["count"] for g in F["groups"]), F["open"])
        self.assertEqual(sum(o["count"] for o in F["outside"]) + F["open"], len(requests), "the asked-and-finished are named, not in flight")
        self.assertTrue(all(o["status"] not in bg.OPEN_STATUSES for o in F["outside"]))
        self.assertEqual([r["key"] for r in F["rows"]], [k for k, *_ in lp.IN_FLIGHT_STATES if k not in ("quiet", "other")],
                         "flight order; quiet and other only when non-empty")
        by = {r["key"]: r for r in F["rows"]}
        A, I, FU = P["asks"], P["introduced"], P["followups"]
        reasons = {e["reason"]: len(e["rows"]) for e in A["exceptions"]}
        self.assertEqual(by["queued"]["count"], A["allocated"], "Top Priorities")
        self.assertEqual(by["no_slot"]["count"], A["no_slot"])
        self.assertEqual(by["no_path"]["count"], reasons[bg.NO_PATH], "Unrouted Exceptions")
        self.assertEqual(by["unresolved"]["count"], reasons["company unresolved"])
        self.assertEqual(by["held"]["count"], reasons.get(bg.UNRESOLVED_ASK, 0))
        self.assertEqual(by["repair"]["count"], reasons[bg.INTRO_CLAIMED_NOT_LOGGED], "the repair queue")
        self.assertEqual(by["parked"]["count"], I["requests"], "Already Introduced")
        self.assertEqual(by["nudge"]["count"], FU["nudge"], "Follow-Ups Owed")
        self.assertEqual(by["chase"]["count"], FU["chase"])
        self.assertEqual(by.get("quiet", {"count": 0})["count"], len(FU["quiet"]))
        self.assertEqual(sorted(by["nudge"]["request_ids"] + by["chase"]["request_ids"] + by.get("quiet", {"request_ids": []})["request_ids"]),
                         sorted(r["request_id"] for r in FU["rows"]))
        self.assertEqual(sorted(by["parked"]["request_ids"]), sorted(rid for r in I["rows"] for rid in r["request_ids"]))
        self.assertIn(f"{I['retry_requests']} of them a retry", by["queued"]["note"])
        by_rid = {r["request_id"]: r for r in requests}
        L = lp.Live(AS_OF)
        for rid in by["meeting"]["request_ids"]:
            self.assertEqual(L.stage_of(by_rid[rid]), "meeting booked", rid)
        for rid in by["introduced"]["request_ids"]:
            self.assertEqual(L.stage_of(by_rid[rid]), "introduced", rid)
        sections = {sid for sid, _ in lp.SECTIONS}
        for r in F["rows"]:
            self.assertIn(r["section"], sections, f"{r['key']} points at a section of this tab")
            self.assertEqual(r["value_usd"], L.dollars_total([by_rid[rid] for rid in r["request_ids"]]), r["key"])
            self.assertEqual(r["value_fmt"], lp.money(r["value_usd"]))
        self.assertEqual((F["quiet_days"], F["intro_live_days"]), (lp.NUDGE_QUIET_DAYS, bg.INTRO_LIVE_DAYS))

    def test_connectors(self):
        """A card per connector with a stake in the cycle: the roster in roster
        order, then the off-roster batch holders, largest batch first."""
        C, L = self.P["connectors"], lp.Live(AS_OF)
        self.assertEqual([c["connector"] for c in C], L.connector_names())
        self.assertEqual([c["connector"] for c in C[:6]],
                         ["Marcus Aldridge", "Dana Whitfield", "Priya Raghunathan", "Tomás Beckett", "Elena Duvall", "Owen Trask"])
        A = self.P["asks"]
        self.assertEqual(sorted(b["connector"] for b in A["batches"]), sorted(c["connector"] for c in C if c["companies"]),
                         "every batch holder has a tab, and only they have a batch")
        self.assertEqual({c["connector"] for c in C[6:]}, {b["connector"] for b in A["batches"]} - set(L.roster), "the off-roster tabs are the off-roster batch holders")
        self.assertEqual(sorted(x["company_id"] for c in C for x in c["companies"]), sorted(x["company_id"] for x in A["all"]), "the tabs and the Aggregate carry the same companies")
        for c in C:
            self.assertEqual(c["on_roster"], c["connector"] in L.roster)
            self.assertEqual(c["used"], c["asked_this_cycle"] + c["allocated_this_cycle"])
            # an ask recorded off the allocation may take used past capacity: flagged, not capped
            self.assertEqual(c["idle"], max(0, c["capacity"] - c["used"]), c["connector"])
            self.assertEqual(c["over_capacity"], max(0, c["used"] - c["capacity"]) if c["capacity"] else 0, c["connector"])
            self.assertEqual(c["capacity"] > 0, c["on_roster"], "only the roster states a capacity")
            self.assertEqual(len(c["queue"]), c["allocated_this_cycle"])
            for q in c["queue"]:
                self.assertEqual(q["connector"], c["connector"], "the queue's ask_sent tick carries who was asked")
            self.assertEqual(sum(len(x["request_ids"]) for x in c["companies"]), len(c["queue"]), "the batch by company is the queue")
            self.assertEqual(bool(c["batch_id"]), bool(c["queue"]))
            batch = next((b for b in A["batches"] if b["connector"] == c["connector"]), None)
            self.assertEqual(c["companies"], batch["companies"] if batch else [])
            self.assertTrue(0 <= c["delivery_rate"] <= 1)
            self.assertEqual(c["quiet_days"], lp.NUDGE_QUIET_DAYS)
            for s in c["sitting_on"]:
                self.assertIsInstance(s["responded"], bool)
                self.assertEqual(s["action"], "nudge" if s["responded"] else "chase", "replied: nudge; silent: chase")
                self.assertEqual(s["connector"], c["connector"], "the tick carries who to follow up with")
                self.assertIsInstance(s["quiet"], bool)
            quiet = [s["quiet"] for s in c["sitting_on"]]
            self.assertEqual(quiet, sorted(quiet), "actionable rows first, recently followed-up rows last")

    def test_completion_actions_cover_every_tick_and_no_crm(self):
        X = self.P["completions"]
        self.assertEqual(X["actions"], {"top": "ask_sent", "nudge": "nudged", "chase": "chased"})
        self.assertNotIn(lp.bg.CHECKED_IN, X["actions"].values(), "a check-in is not ticked or posted anywhere")
        self.assertEqual(X["quiet_days"], lp.NUDGE_QUIET_DAYS)
        self.assertNotIn("checkin_days", X)
        js = (ROOT / "dashboard" / "live_priorities.js").read_text(encoding="utf-8")
        self.assertNotIn("account_created", js)
        self.assertNotIn("crmTick", js)
        self.assertNotIn("checkinTick", js)
        self.assertNotIn("checked_in", js)
        for name in ("askTick", "followTick", "groupTick", "pickTick", "mirror"):
            self.assertIn(f"const {name} = ", js)
        self.assertNotIn("nudgeTick", js, "one tick for a follow-up, whichever table it is in")
        # one ask_sent per request, keyed on action + request: the same tick in Top Priorities, a connector's
        # batch (one box per company, fanned out to its requests) and a no-path exception (connector picked)
        self.assertEqual(js.count("pickTick(state, askTick(X, { ...r, connector: '' })"), 1)
        self.assertEqual(js.count("groupTick(state, g)"), 1)
        self.assertIn("noPath ? pickTick", js, "only a no-path exception takes an ask; the others point at nudge/chase, Already Introduced or the Route tool")
        A = self.P["asks"]
        self.assertEqual(A["roster"], [c["connector"] for c in self.P["connectors"] if c["on_roster"]], "the picker lists the roster")
        self.assertIn("mirror(state, batchTicks(x, x.connector))", js, "the Aggregate tab is done-state only")
        introduced = js.split("sec.introduced = ")[1].split("sec.exceptions = ")[0]
        self.assertNotIn("Tick(", introduced, "nothing to tick under Already Introduced")
        self.assertIn("mirror(state, batchTicks(r, r.connectors.join(', ')))", introduced,
                      "a retry row is done-state only: its asks are ticked under the connector or Top Priorities")
        # every retry is allocated this cycle, so its ask_sent keys exist on a batch row already
        batched = {rid for c in self.P["connectors"] for x in c["companies"] for rid in x["request_ids"]}
        for r in self.P["introduced"]["retries"]:
            self.assertTrue(set(r["request_ids"]) <= batched, r["company_id"])

    def test_crm_exports_are_importer_shaped(self):
        C = self.P["crm"]
        self.assertEqual(C["import"]["filename"], "crm_import.csv")
        self.assertEqual(C["import"]["columns"], lp.wb.IMPORT_COLUMNS)
        rows = list(csv.DictReader(C["import"]["csv"].splitlines()))
        self.assertEqual(len(rows), C["import"]["count"])
        self.assertTrue(all(list(r.keys()) == lp.wb.IMPORT_COLUMNS for r in rows))
        self.assertEqual(C["review"]["filename"], "crm_review.csv")
        review = list(csv.DictReader(C["review"]["csv"].splitlines()))
        self.assertTrue(all(r["status"] == lp.wb.STATUS and r["executed_on"] == "" for r in review),
                        "every CRM row is a recommendation; nothing is executed from the tab")
        self.assertEqual([g["group"] for g in C["groups"]], ["create", "merge", "owners", "reopen"])

    def test_connector_pages_top_five_then_the_rest(self):
        live = lp.Live(AS_OF)
        pages = live.connector_pages()
        names = [c["connector"] for c in pages]
        self.assertEqual(names, [c["connector"] for c in self.P["connectors"]], "a page per card: roster first, roster order, then the off-roster batch holders")
        self.assertEqual(names, [c["connector"] for c in self.P["connector_pages"]])
        self.assertEqual(len(set(names)), len(names))
        seen = 0
        for c in pages:
            mine = c["top"] + c["rest"]
            self.assertLessEqual(len(c["top"]), lp.TOP_N)
            self.assertEqual(len(c["rest"]), max(0, len(mine) - lp.TOP_N))
            self.assertEqual(c["ranked_count"], len(mine))
            self.assertTrue(all(r["connector"] == c["connector"] for r in mine))
            self.assertEqual([r["rank_here"] for r in mine], list(range(1, len(mine) + 1)))
            self.assertEqual([r["expected_value"] for r in mine],
                             sorted((r["expected_value"] for r in mine), reverse=True))
            self.assertEqual([r["rank"] for r in mine], sorted(r["rank"] for r in mine),
                             "a connector's list keeps the global Live Priorities order")
            self.assertEqual(c["page"], f"connector-{lp.slug(c['connector'])}.html")
            self.assertIn("formula", c)
            for r in mine:
                if r["company_id"]:
                    self.assertEqual(r["href"], f"{lp.TRACE_PAGE}#{r['company_id']}")
            seen += len(mine)
        self.assertEqual(seen, len(live.ranked()), "every ranked request lands on exactly one connector page")
        self.assertEqual(lp.slug("Tomás Beckett"), "tomas-beckett")

    def test_strongest_path_elsewhere_is_read_only_and_never_an_ask(self):
        """Elena's Harrowgate offer is the strongest raw path but never a logged ask:
        it must not appear in `sitting_on` (intro_outcomes.csv only) or her queue,
        only in the read-only `strongest_elsewhere` list with capacity and where
        the requests went."""
        live = lp.Live(AS_OF)
        elena = next(c for c in live.connector_pages() if c["connector"] == "Elena Duvall")
        self.assertNotIn("C018", [s["company_id"] for s in elena["sitting_on"]])
        self.assertNotIn("C018", [q["company_id"] for q in elena["queue"]])
        self.assertNotIn("C018", [r["company_id"] for r in elena["top"] + elena["rest"]])
        rows = elena["strongest_elsewhere"]
        row = next(r for r in rows if r["company_id"] == "C018")
        self.assertEqual((row["reach_type"], row["strength"], row["route_score"], row["outside_focus"]), ("offer", 0.8, 0.0, True))
        used = sum(a["allocated_to"] == "Elena Duvall" for a in live.allocation)
        self.assertEqual((row["used"], row["capacity"]), (used, 3))
        self.assertEqual(row["routed_to"], ["Priya Raghunathan"], "Tomás agreed to R1057 there and sent no intro: nudged, not asked again")
        self.assertEqual(live.held[("Tomás Beckett", "C018")]["hold"], bg.HOLD_NUDGE)
        self.assertEqual(row["requests"], ["R1136", "R1140", "R1153", "R1173"],
                         "R1173, filed Intro sent with no intro logged, is in the allocator now (repair queue)")
        self.assertEqual(row["href"], f"{lp.TRACE_PAGE}#C018")
        self.assertTrue({"action", "asked_date", "nudged_on"}.isdisjoint(row), "nothing to tick, chase or nudge")
        self.assertEqual([r["strength"] for r in rows], sorted((r["strength"] for r in rows), reverse=True))
        for c in live.connector_pages():
            mine = {a["company_id"] for a in live.allocation if a["allocated_to"] == c["connector"]}
            for r in c["strongest_elsewhere"]:
                self.assertNotIn(r["company_id"], mine, f"{c['connector']} holds a request there; it is not 'not routed to you'")
                self.assertTrue(r["routed_to"] or r["unrouted"])
                self.assertNotIn(c["connector"], r["routed_to"])

    def test_cycles_intros_capacity_and_running_total(self):
        live = lp.Live(AS_OF)
        C = live.cycles()
        months = [r["cycle"] for r in C["rows"]]
        self.assertEqual(months[0], min(o["asked_date"][:7] for o in live.outcomes))
        self.assertEqual(months[-1], live.cycle)
        self.assertEqual(len(set(months)), len(months))
        for a, b in zip(months, months[1:]):
            y, m = int(a[:4]), int(a[5:7])
            self.assertEqual(b, f"{y + 1:04d}-01" if m == 12 else f"{y:04d}-{m + 1:02d}", "no month skipped")
        intros = [o for o in live.outcomes if o["intro_sent"] == "Y"]
        self.assertEqual(C["intros_total"], len(intros))
        self.assertEqual(C["asks_total"], len(live.outcomes))
        self.assertEqual(sum(r["intros"] for r in C["rows"]), len(intros))
        run = 0
        for r in C["rows"]:
            run += r["intros"]
            self.assertEqual(r["intros_cumulative"], run)
            self.assertEqual(r["intros"], sum(1 for o in intros if o["intro_date"].startswith(r["cycle"])))
            self.assertEqual(r["asks"], sum(1 for o in live.outcomes if o["asked_date"].startswith(r["cycle"])))
            self.assertEqual(r["capacity"], C["roster_capacity"])
            self.assertAlmostEqual(r["capacity_pct"], r["used"] / r["capacity"], places=3)
            if not r["current"]:
                self.assertEqual((r["allocated"], r["allocated_off_roster"]), (0, 0))
                self.assertEqual(r["used"], sum(1 for o in live.outcomes if o["asked_date"].startswith(r["cycle"])
                                                and o["connector_asked"] in live.roster))
        cur = C["rows"][-1]
        self.assertEqual(cur["allocated"], sum(1 for a in live.allocation if a["allocated_to"]))
        self.assertEqual(cur["allocated_off_roster"], sum(1 for a in live.allocation if a["allocated_to"] and a["allocated_to"] not in live.roster))
        self.assertEqual(C["roster_capacity"], sum(int(r["stated_monthly_capacity"]) for r in live.roster.values()))
        # per connector: the same rows, one name at a time; the pages carry them
        self.assertEqual([p["connector"] for p in C["per_connector"]], list(live.roster))
        for c in live.connector_pages():
            rows = c["cycles"]
            self.assertEqual([r["cycle"] for r in rows], months)
            self.assertEqual(rows[-1]["intros_cumulative"], c["intros_all_time"])
            self.assertEqual(rows[-1]["intros"], c["intros_this_cycle"])
            self.assertEqual(rows[-1]["used"], c["used"] if c["on_roster"] else 0)
            self.assertEqual(rows[-1]["capacity"], c["capacity"])
            if not c["on_roster"]:
                self.assertTrue(all(r["capacity_pct"] is None for r in rows))
        summed = [sum(p["rows"][i]["intros"] for p in C["per_connector"]) for i in range(len(months))]
        off = [sum(1 for o in intros if o["connector_asked"] not in live.roster and o["intro_date"].startswith(m)) for m in months]
        self.assertEqual([a + b for a, b in zip(summed, off)], [r["intros"] for r in C["rows"]])

    def test_page_embeds_the_payload_and_no_arithmetic_on_facts(self):
        html = lp.fragment(AS_OF)
        self.assertIn('<script id="lp-data" type="application/json">', html)
        self.assertNotIn("</script>", json.dumps(lp.payload(AS_OF)).replace("</", "<\\/"))
        js = (ROOT / "dashboard" / "live_priorities.js").read_text(encoding="utf-8")
        for token in ("deal_value_usd", "value_usd *", "* 0.9", "/ 365", "STAGE_WEIGHT"):
            self.assertNotIn(token, js, f"the browser renders; {token!r} would be it calculating")

    def test_section_nav_matches_the_sections_the_page_renders(self):
        js = (ROOT / "dashboard" / "live_priorities.js").read_text(encoding="utf-8")
        boot = js.split("function boot(")[1].split("function renderPreview(")[0]
        self.assertEqual([sid for sid, _ in lp.SECTIONS], re.findall(r'<section id="([^"]+)"', boot),
                         "SECTIONS is the header nav; it must list every section boot() renders, in order")
        self.assertEqual([sid for sid, _ in lp.SECTIONS],
                         ["route", "upload", "stages", "top", "connectors", "introduced", "exceptions", "followups", "crm"],
                         "intake (route), intake (add live data), orientation, actionable now, current cycle, other")
        self.assertEqual([len(sections) for *_, sections in lp.BANDS], [1, 1, 1, 1, 4, 1], "no Not Moving band")
        self.assertTrue(all(all(w[0].isupper() or w in ("a", "an", "and", "by", "of", "the") for w in label.replace("—", " ").split())
                            for _, label in lp.SECTIONS), "nav labels in Title Case")
        self.assertIn("Unrouted Exceptions <span", boot)
        for gone in ("Current Asks", "Roster Connector Capacity", "Suggested Unrouted", "Core Introduction Bottlenecks", "Preview a Slack Export", "#asks", "#bottlenecks", "#unrouted"):
            self.assertNotIn(gone, js, f"{gone}: one home per thing")
        connectors = boot.split('<section id="connectors"')[1].split('<section id=')[0]
        for token in ("D.connectors.map", "label: 'Aggregate'", "composeBlock(c.batch_ask", "c.companies.map", "A.all.map", "notifyCell"):
            self.assertIn(token, connectors, "a tab per connector: capacity, the drafted message, the batch by company, owner heads-ups; plus the Aggregate")
        self.assertNotIn("sittingTable", connectors, "follow-ups have one home on this page")
        exceptions = boot.split('<section id="exceptions"')[1].split('<section id=')[0]
        self.assertIn("<th>Who covers this sector</th>", exceptions)
        self.assertIn("<td>${cover(r.sector_cover)}</td>", exceptions, "the sector column is on every group")
        self.assertNotIn("noPath ? `<td>${cover", exceptions, "the sector column is on every group")
        self.assertIn("Fo.in_focus_pct", exceptions, "the in-focus finding is one line in the header")
        self.assertIn("A.no_slot", exceptions, "the no-slot requests are counted, and pointed at the ranked list")
        followups = boot.split('<section id="followups"')[1].split('<section id=')[0]
        self.assertIn("sittingTable(t.rows", followups)
        self.assertIn("'All connectors'", followups)
        route = boot.split('<section id="route"')[1].split('<section id=')[0]
        for token in ('id="lp-route-text"', 'id="lp-drop"', 'id="lp-file"', 'id="lp-preview"'):
            self.assertIn(token, route, "one intake box: paste or drop")
        self.assertIn("renderPreview(previewThreads(threads, P)", boot, "pasted text and a dropped file render the same way, one row per thread")
        folded = re.findall(r'<section id="([^"]+)">\$\{fold\(', boot)
        self.assertEqual(folded, ["connectors", "introduced", "exceptions", "followups", "crm"], "the long tables start collapsed")
        self.assertIn('<section id="stages" class="masthead">', boot)
        self.assertNotIn("<table", boot.split('<section id="stages"')[1].split("</section>")[0], "orientation is one strip, no rows")
        self.assertIn("CRM Updates <span", boot)
        self.assertNotIn("What the CRM is missing", js)

    def test_bands_are_in_the_payload_and_cover_every_section(self):
        bands = lp.payload(AS_OF)["bands"]
        self.assertEqual([b["id"] for b in bands], ["intake", "upload", "orientation", "now", "cycle", "other"])
        self.assertEqual(bands[1]["title"], "Intake: Add More Live Data")
        self.assertEqual([s for b in bands for s in b["sections"]], [sid for sid, _ in lp.SECTIONS])
        self.assertTrue(all(b["title"] for b in bands))
        self.assertNotIn("test", bands[0], "no membership question under the band title")
        js = (ROOT / "dashboard" / "live_priorities.js").read_text(encoding="utf-8")
        self.assertNotIn("Band ${i + 1}", js, "band headers carry the title only, no Band N label")


class FunnelWindowTest(unittest.TestCase):
    """Live Data's cumulative / last-12-months toggle: both views are computed here."""

    def test_since_filters_by_request_date(self):
        allt = funnel_stages()
        reqs = read_csv(ROOT / "golden" / "golden_requests.csv")
        since = sorted(r["request_date"][:10] for r in reqs)[len(reqs) // 2]
        rolling = funnel_stages(since=since)
        self.assertEqual([n for n, _ in rolling], [n for n, _ in allt])
        self.assertEqual(rolling[0][1], sum(1 for r in reqs if r["request_date"][:10] >= since))
        self.assertTrue(all(b <= a for (_, a), (_, b) in zip(allt, rolling)))
        self.assertLess(rolling[0][1], allt[0][1])
        self.assertEqual(funnel_stages(since="1900-01-01"), allt)


class RequesterCutTest(unittest.TestCase):
    """Live Data's per-requester charts: asks, accounts, CRM value, intro rate, urgency."""

    def test_requesters_partition_the_requests(self):
        from dashboard import data_cuts
        cuts = data_cuts.load()
        cut = data_cuts.requester_cut(cuts)
        rows = cut["requesters"]
        self.assertEqual({b["name"] for b in rows}, {r["requested_by"].strip() for r in cuts["requests"]})
        self.assertEqual(sum(b["requests"] for b in rows), len(cuts["requests"]))
        self.assertEqual([b["requests"] for b in rows], sorted((b["requests"] for b in rows), reverse=True))
        self.assertTrue(all(b["kind"] in ("SDR", "AE") for b in rows))
        for b in rows:
            mine = [r for r in cuts["requests"] if r["requested_by"].strip() == b["name"]]
            companies = {cuts["golden_requests"][r["request_id"]]["company_id"] for r in mine} - {""}
            self.assertEqual(b["accounts"], len(companies), b["name"])
            self.assertEqual(b["unresolved"], sum(1 for r in mine if not cuts["golden_requests"][r["request_id"]]["company_id"]))
            in_crm = {c for c in companies if cuts["golden_companies"][c]["crm_account_ids"]}
            self.assertEqual(b["crm_accounts"], len(in_crm))
            # one $ per company: CRM ARR potential where it has an account, else its latest deal value
            self.assertAlmostEqual(b["value"], sum(data_cuts.company_dollars(cuts, c)[0] for c in companies))
            self.assertGreaterEqual(b["value"], sum(float(cuts["golden_companies"][c]["value_usd"]) for c in in_crm))
            self.assertAlmostEqual(b["intro_rate"], b["intros"] / b["requests"])
            self.assertTrue(b["intros"] <= b["routed"] <= b["requests"], b["name"])
            self.assertEqual(b["critical"], sum(1 for r in mine if r["urgency"].strip().lower() == "critical"))
            self.assertEqual(b["critical_high"], sum(1 for r in mine if r["urgency"].strip().lower() in ("critical", "high")))
            self.assertTrue(0 <= b["critical_share"] <= b["critical_high_share"] <= 1)
        self.assertAlmostEqual(cut["intro_rate"], sum(b["intros"] for b in rows) / cut["requests"])
        self.assertLessEqual(cut["value"], sum(b["value"] for b in rows), "the total counts a shared account once")
        self.assertEqual(cut["value"], sum(data_cuts.company_dollars(cuts, c)[0] for c in {c for b in rows for c in b["companies"]}))
        self.assertGreater(sum(1 for b in rows if b["value"] > sum(float(cuts["golden_companies"][c]["value_usd"]) for c in b["companies"]
                                                                if cuts["golden_companies"][c]["crm_account_ids"])), 0,
                           "a company with no CRM account still counts at its deal value")


class UrgencyCutTest(unittest.TestCase):
    """Raw September's urgency overview keeps request-level urgency and CRM stage together."""
    @classmethod
    def setUpClass(cls):
        from dashboard import data_cuts
        cls.dc = data_cuts
        cls.raw = data_cuts.load()
        cls.cut = data_cuts.urgency_cut(cls.raw)

    def test_every_raw_request_has_one_ordered_urgency_row(self):
        rows = self.cut["rows"]
        self.assertEqual(len(rows), len(self.raw["requests"]))
        self.assertEqual({r["request_id"] for r in rows}, {r["request_id"] for r in self.raw["requests"]})
        self.assertEqual(sum(r["count"] for r in self.cut["categories"]), len(rows))
        self.assertEqual([r["urgency"] for r in self.cut["categories"]],
                         [u for u in self.dc.URGENCY_ORDER if any(r["urgency"] == u for r in rows)])
        self.assertEqual(rows, sorted(rows, key=lambda r: (r["urgency_rank"], -r["value"], r["filed"] or "9999-99-99", r["request_id"])))
        self.assertEqual(self.cut["top"], rows[:self.cut["limit"]])

    def test_urgency_and_crm_stage_are_the_september_values(self):
        by_id = {r["request_id"]: r for r in self.raw["requests"]}
        for row in self.cut["rows"]:
            raw = by_id[row["request_id"]]
            self.assertEqual(row["urgency"], self.dc.urgency_label(raw["urgency"]))
            self.assertIn(row["crm_stage"], {a["stage"] for a in self.raw["crm"]} | {"No CRM record"})


class GoldenSourceCutsTest(unittest.TestCase):
    """data_cuts.load("golden"): what the Live Data tab is computed from. The same cuts
    as the Raw Sept tab, over golden_requests.csv and the ask log with completions applied."""

    @classmethod
    def setUpClass(cls):
        from dashboard import data_cuts
        cls.dc = data_cuts
        cls.raw = data_cuts.load()
        cls.gold = data_cuts.load("golden", completions=[])

    def test_only_the_two_sources(self):
        with self.assertRaises(ValueError):
            self.dc.load("supabase")
        self.assertEqual((self.raw["source"], self.gold["source"]), ("dataset", "golden"))

    def test_golden_requests_wear_the_raw_shape(self):
        # the Live Data tab reads golden/current/ (dataset/ plus accepted uploads), not dataset/
        export = self.dc.dataset("intro_requests.csv", self.gold["dir"])
        export_by_id = {r["request_id"]: r for r in export}
        self.assertEqual([r["request_id"] for r in self.gold["requests"]], list(self.gold["golden_requests"]))
        roles = {r["requested_by"].strip(): r["requester_role"] for r in export if r["requester_role"].strip()}
        for r in self.gold["requests"]:
            self.assertEqual(set(r), set(export[0]), "every column a cut reads")
            g = self.gold["golden_requests"][r["request_id"]]
            self.assertEqual((r["requested_by"], r["request_date"], r["status"], r["urgency"], r["deal_value_usd"]),
                             (g["requested_by"], g["request_date"], g["status_as_filed"], g["urgency_declared"], g["value_usd"]),
                             "the facts golden carries win")
            filed = export_by_id.get(r["request_id"])
            if filed is not None and filed["requester_role"].strip():
                self.assertEqual(r["requester_role"], filed["requester_role"], r["request_id"])
            else:
                self.assertEqual(r["requester_role"], roles.get(g["requested_by"].strip(), ""),
                                 f"{r['request_id']}: carried forward or ingested, role from the requester's other rows")
        # a request golden carries that the raw export no longer has: role from the requester's other rows
        g = dict(next(iter(self.gold["golden_requests"].values())), request_id="R999")
        extra = self.dc.as_filed(g, {}, roles)
        self.assertEqual(extra["requester_role"], roles[g["requested_by"].strip()])
        self.assertEqual((extra["target_person_raw"], extra["path_found_flag"]), ("", ""))

    def test_without_completions_golden_agrees_with_raw_today(self):
        # Golden can also carry accepted live requests that are absent from the September export.
        # Restrict it to the export ids to compare the shared historical population.
        raw_ids = {r["request_id"] for r in self.raw["requests"]}
        gold = dict(self.gold,
                    requests=[r for r in self.gold["requests"] if r["request_id"] in raw_ids],
                    outcomes=[r for r in self.gold["outcomes"] if r["request_id"] in raw_ids],
                    outcome_by_request={rid: r for rid, r in self.gold["outcome_by_request"].items() if rid in raw_ids},
                    golden_requests={rid: r for rid, r in self.gold["golden_requests"].items() if rid in raw_ids},
                    allocation=[r for r in self.gold["allocation"] if r["request_id"] in raw_ids])
        self.assertEqual(self.dc.funnel_cut(gold), self.dc.funnel_cut(self.raw))
        self.assertEqual(self.dc.funnel_cut(self.gold), funnel_stages(),
                         "the same stages sankey_funnel.py computes from golden_requests.csv")
        self.assertEqual(self.dc.funnel_cut(self.gold, since="2026-01-01"), funnel_stages(since="2026-01-01"))
        self.assertEqual(self.dc.requester_cut(gold), self.dc.requester_cut(self.raw))
        self.assertEqual(self.dc.connector_cut(gold), self.dc.connector_cut(self.raw))
        self.assertEqual(self.dc.account_demand_cut(gold), self.dc.account_demand_cut(self.raw))
        self.assertEqual(self.dc.top_accounts_cut(gold), self.dc.top_accounts_cut(self.raw))
        self.assertEqual(self.dc.cycle_cut(gold), self.dc.cycle_cut(self.raw))

    def test_every_dollar_is_one_per_company(self):
        # dashboard/company_value.py prices every $ on the site: CRM ARR potential where the
        # company has an account, else the deal value on its latest request that carries one
        live = lp.Live(AS_OF)
        for b in self.dc.company_rows(self.gold):
            if b["unresolvable"]:
                continue
            value, source = live.company_value(b["company_id"])
            self.assertEqual((b["value"], b["value_source"]), (value, "CRM" if source == "crm" else "deal"), b["name"])
        top = self.dc.top_accounts_cut(self.gold)["companies"]
        self.assertEqual([b["value"] for b in top], sorted((b["value"] for b in top), reverse=True))
        # a company whose latest request carries a smaller deal value than an earlier one is priced at the latest
        by_company = self.dc.requests_by_company(self.gold)
        latest_wins = [cid for cid, rows in by_company.items()
                       if not self.gold["golden_companies"][cid]["crm_account_ids"]
                       and len({r["value_usd"] for r in rows if r["value_usd"]}) > 1]
        self.assertTrue(latest_wins, "the fixture has a company with two different deal values and no CRM account")
        for cid in latest_wins:
            newest = max((r for r in by_company[cid] if r["value_usd"]), key=lambda r: (r["request_date"], r["request_id"]))
            self.assertEqual(self.dc.company_dollars(self.gold, cid), (int(float(newest["value_usd"])), "deal"))
        cov = self.dc.outcome_delta_cut(self.gold)
        asked = {o["request_id"] for o in self.gold["outcomes"]}
        hole = [self.gold["golden_requests"][r["request_id"]] for r in self.gold["requests"]
                if r["request_id"] not in asked and r["status"] in ("Intro sent", "Routed")]
        self.assertEqual(cov["should_exist"], len(hole))
        self.assertEqual(cov["should_exist_value"], live.dollars_total(hole))
        resolved = [r for r in hole if r["company_id"]]
        self.assertEqual(self.dc.dollars(self.gold, [r["request_id"] for r in resolved] * 2), self.dc.dollars(self.gold, [r["request_id"] for r in resolved]),
                         "naming a request twice does not count its company twice")

    def test_an_ask_sent_from_live_priorities_counts_from_the_next_build(self):
        asked = {o["request_id"] for o in self.raw["outcomes"]}
        rid = next(r["request_id"] for r in self.raw["requests"] if r["request_id"] not in asked)
        connector = self.raw["roster"][0]["name"].strip()
        row = {c: "" for c in bg.COMPLETION_COLUMNS}
        row.update(completion_id=f"{rid}:ask_sent:2026-09-06", completed_at="2026-09-06T10:15:00+00:00",
                   completed_by="vera", action=bg.ASKED, request_id=rid, connector=connector)
        after = self.dc.load("golden", completions=[row])
        self.assertEqual(after["completions"], [row])
        self.assertEqual(self.dc.load()["completions"], [], "the Raw Sept tab never sees a completion")

        before_f, after_f = dict(self.dc.funnel_cut(self.gold)), dict(self.dc.funnel_cut(after))
        self.assertEqual(after_f["Requests"], before_f["Requests"])
        self.assertEqual(after_f["Asked"], before_f["Asked"] + 1, "one more ask, nothing back yet")
        self.assertEqual(after_f["Responded"], before_f["Responded"])
        self.assertEqual(after["outcome_by_request"][rid]["source"], "completions.csv")

        who = next(r["requested_by"].strip() for r in self.raw["requests"] if r["request_id"] == rid)
        routed = lambda cut: {b["name"]: b["routed"] for b in cut["requesters"]}  # noqa: E731
        before_r, after_r = routed(self.dc.requester_cut(self.gold)), routed(self.dc.requester_cut(after))
        self.assertEqual(after_r[who], before_r[who] + 1)
        self.assertEqual({k: v for k, v in after_r.items() if k != who}, {k: v for k, v in before_r.items() if k != who})

        asked_of = lambda cut: {c["name"]: c["asked"] for c in cut["connectors"]}  # noqa: E731
        before_c, after_c = asked_of(self.dc.connector_cut(self.gold)), asked_of(self.dc.connector_cut(after))
        self.assertEqual(after_c[connector], before_c[connector] + 1)

        cid = self.gold["golden_requests"][rid]["company_id"]
        if cid:
            by_cid = lambda cut: {b["company_id"]: b["routed"] for b in cut["companies"]}  # noqa: E731
            before_d, after_d = by_cid(self.dc.account_demand_cut(self.gold)), by_cid(self.dc.account_demand_cut(after))
            self.assertEqual(after_d[cid], before_d[cid] + 1)

        before_y, after_y = self.dc.cycle_cut(self.gold), self.dc.cycle_cut(after)
        self.assertEqual(after_y["asks_total"], before_y["asks_total"] + 1)
        self.assertEqual(after_y["cycle"], "2026-09", "the ask opens the month it was sent in")
        sept = next(r for r in after_y["rows"] if r["cycle"] == "2026-09")
        self.assertEqual((sept["asks"], sept["used"], sept["intros"]), (1, 1, 0))
        self.assertEqual(after_y["intros_total"], before_y["intros_total"])

    def test_a_re_ask_after_a_fizzled_intro_is_a_second_ask_in_its_month(self):
        fizzled = next(o for o in self.raw["outcomes"] if o["intro_sent"] == "Y" and o["meeting_booked"] != "Y")
        rid = fizzled["request_id"]
        row = {c: "" for c in bg.COMPLETION_COLUMNS}
        row.update(completion_id=f"{rid}:ask_sent:2026-09-06", completed_at="2026-09-06T10:15:00+00:00",
                   completed_by="vera", action=bg.ASKED, request_id=rid, connector=fizzled["connector_asked"])
        after = self.dc.load("golden", completions=[row])
        self.assertEqual(after["outcome_by_request"][rid]["reasked_date"], "2026-09-06")
        self.assertEqual(self.dc.ask_dates(after["outcome_by_request"][rid]), [fizzled["asked_date"], "2026-09-06"])
        self.assertEqual(self.dc.funnel_cut(after), self.dc.funnel_cut(self.gold), "the request was already asked")
        before_y, after_y = self.dc.cycle_cut(self.gold), self.dc.cycle_cut(after)
        self.assertEqual(after_y["asks_total"], before_y["asks_total"] + 1)
        self.assertEqual(next(r for r in after_y["rows"] if r["cycle"] == "2026-09")["asks"], 1)

    def test_cycle_cut_matches_live_priorities_on_the_months_on_file(self):
        # the Raw Sept tab's cycles are Live Priorities' cycle table with no allocation and no current
        # cycle; on the closed months both count the same asks, slots and intros
        live = lp.cycles(AS_OF)
        raw = self.dc.cycle_cut(self.raw)
        self.assertEqual(raw["roster_capacity"], live["roster_capacity"])
        self.assertTrue(set(raw["off_roster"]) <= set(live["off_roster"]), "Live Priorities adds whoever is allocated off-roster")
        self.assertFalse(any(r["current"] for r in raw["rows"]))
        self.assertTrue(all(r["allocated"] == 0 for r in raw["rows"]))
        live_by = {r["cycle"]: r for r in live["rows"] if not r["current"]}
        raw_by = {r["cycle"]: r for r in raw["rows"]}
        self.assertTrue(set(raw_by) <= set(live_by) | {live["cycle"]})
        for cyc, r in raw_by.items():
            if cyc in live_by:
                self.assertEqual((r["asks"], r["used"], r["intros"], r["intros_cumulative"], r["capacity_pct"]),
                                 (live_by[cyc]["asks"], live_by[cyc]["used"], live_by[cyc]["intros"],
                                  live_by[cyc]["intros_cumulative"], live_by[cyc]["capacity_pct"]), cyc)
        self.assertEqual([p["connector"] for p in raw["per_connector"]], [p["connector"] for p in live["per_connector"]])

    def test_yield_is_what_the_asks_routed_and_returned(self):
        y = self.dc.yield_cut(self.gold)
        stages = dict(self.dc.funnel_cut(self.gold))
        self.assertEqual((y["asks"], y["intros"], y["opps"]), (stages["Asked"], stages["Intros"], stages["Opportunities"]))
        by_id = {r["request_id"]: r for r in self.gold["requests"]}
        # one $ per company (dashboard/company_value.py), the rule Live Priorities prices every row by
        live = lp.Live(AS_OF)
        asked_rows = [self.gold["golden_requests"][o["request_id"]] for o in self.gold["outcomes"]]
        self.assertEqual(y["routed"], live.dollars_total(asked_rows))
        self.assertNotEqual(y["routed"], sum(float(by_id[o["request_id"]]["deal_value_usd"] or 0) for o in self.gold["outcomes"]),
                            "a company asked twice is routed once")
        self.assertEqual(y["requested"], live.dollars_total(list(self.gold["golden_requests"].values())))
        opp_rows = [self.gold["golden_requests"][o["request_id"]] for o in self.gold["outcomes"] if o["opportunity_created"] == "Y"]
        self.assertEqual(y["opp"], live.dollars_total(opp_rows))
        self.assertEqual(y["opp_companies"], len({r["company_id"] for r in opp_rows}))
        self.assertLess(y["opp_companies"], y["opps"], "a company with two opportunities logged counts once")
        self.assertNotEqual(y["opp"], sum(float(o["opportunity_value_usd"] or 0) for o in self.gold["outcomes"]))
        self.assertAlmostEqual(y["routed_per_ask"], y["routed"] / y["asks"])
        self.assertAlmostEqual(y["opp_per_intro"], y["opp"] / y["intros"])
        self.assertGreater(y["requested"], y["routed"], "the never-asked requests carry value too")
        cx = self.dc.connector_cut(self.gold)
        self.assertLessEqual(cx["opp_value"], y["opp"], "off-roster asks return too; the ranking is the roster")
        self.assertEqual([c["opp_per_ask"] for c in cx["by_return"]], sorted((c["opp_per_ask"] for c in cx["by_return"]), reverse=True))
        roster = {r["name"].strip() for r in self.gold["roster"]}
        for c in cx["connectors"]:
            mine = [o for o in self.gold["outcomes"] if o["connector_asked"].strip() == c["name"]]
            self.assertEqual(c["value"], live.dollars_total([self.gold["golden_requests"][o["request_id"]] for o in mine]), c["name"])
            self.assertEqual(c["opp_value"], live.dollars_total([self.gold["golden_requests"][o["request_id"]] for o in mine if o["opportunity_created"] == "Y"]), c["name"])
            self.assertNotIn("asked_rids", c)
        self.assertEqual(cx["opp_value"], live.dollars_total([r for r, o in zip(asked_rows, self.gold["outcomes"])
                                                             if o["opportunity_created"] == "Y" and o["connector_asked"].strip() in roster]))
        for c in cx["by_return"]:
            self.assertAlmostEqual(c["opp_per_ask"], c["opp_value"] / c["asked"], msg=c["name"])
        empty = self.dc.yield_cut(self.gold, since="2999-01-01")
        self.assertEqual((empty["asks"], empty["routed_per_ask"], empty["opp_per_intro"]), (0, 0, 0), "an empty window does not divide by zero")

    def test_backlog_is_the_never_asked_split_by_whether_a_path_exists(self):
        b = self.dc.backlog_cut(self.gold)
        stages = dict(self.dc.funnel_cut(self.gold))
        self.assertEqual(b["never"], stages["Requests"] - stages["Asked"])
        self.assertEqual(b["with_path"] + b["without_path"], b["never"])
        self.assertAlmostEqual(b["with_path_value"] + b["without_path_value"], b["never_value"])
        self.assertEqual(sum(c["requests"] for c in b["companies"]), b["with_path"])
        self.assertAlmostEqual(sum(c["value"] for c in b["companies"]), b["with_path_value"])
        # one $ per company: the backlog is worth its companies, not its requests
        live = lp.Live(AS_OF)
        never_ids = {r["request_id"] for r in self.gold["requests"]} - {o["request_id"] for o in self.gold["outcomes"]}
        never_rows = [self.gold["golden_requests"][rid] for rid in never_ids]
        self.assertEqual(b["never_value"], live.dollars_total(never_rows))
        self.assertLess(b["with_path_value"], sum(float(r["value_usd"] or 0) for r in never_rows if r["company_id"] in {c["company_id"] for c in b["companies"]}),
                        "a company requested twice counts once")
        for c in b["companies"]:
            self.assertEqual(c["value"], live.company_value(c["company_id"])[0])
        reach = {s["company_id"] for s in self.gold["supply"]}
        for c in b["companies"]:
            self.assertIn(c["company_id"], reach)
            self.assertTrue(c["connectors"] and c["name"], c)
        self.assertEqual([c["requests"] for c in b["companies"]], sorted((c["requests"] for c in b["companies"]), reverse=True))
        # an ask sent from Live Priorities takes its request out of the backlog on the next build
        rid = next(r["request_id"] for r in self.gold["requests"]
                   if r["request_id"] not in {o["request_id"] for o in self.gold["outcomes"]}
                   and self.gold["golden_requests"][r["request_id"]]["company_id"] in reach)
        row = {c: "" for c in bg.COMPLETION_COLUMNS}
        row.update(completion_id=f"{rid}:ask_sent:2026-09-06", completed_at="2026-09-06T10:15:00+00:00",
                   completed_by="vera", action=bg.ASKED, request_id=rid, connector=self.raw["roster"][0]["name"].strip())
        after = self.dc.backlog_cut(self.dc.load("golden", completions=[row]))
        self.assertEqual((after["never"], after["with_path"]), (b["never"] - 1, b["with_path"] - 1))

    def test_one_classifier_gives_every_request_one_state_on_both_pages(self):
        """dashboard/request_state.py: every request, one state each, the counts the pages
        show; and a request_id reaches the same state through data_cuts as through live_priorities."""
        via_cuts = self.dc.request_states(self.gold)
        via_live = lp.Live(AS_OF).states
        self.assertEqual(len(via_cuts), len(self.gold["requests"]))
        self.assertEqual(sorted(via_cuts), sorted(r["request_id"] for r in self.gold["requests"]), "every request on file, once")
        expected_states = {
            rs.ASKED, rs.ALLOCATED, bg.NO_PATH, bg.INTRO_CLAIMED_NOT_LOGGED,
            rs.COMPANY_UNRESOLVED, bg.CAPACITY_EXHAUSTED, bg.ALREADY_INTRODUCED,
            bg.UNRESOLVED_ASK,
        }
        self.assertTrue(set(via_cuts.values()) <= expected_states,
                        "every request reaches a known actionable state")
        self.assertFalse([s for s in via_cuts.values() if s.startswith(rs.STATUS_GATE)], "every filed status reaches the allocator")
        self.assertEqual(sum(Counter(via_cuts.values()).values()), len(self.gold["requests"]), "exactly one state per request")
        self.assertEqual(via_live, via_cuts, "the same request_id, the same state, whichever module reaches it")
        # the classifier reads the ask log and the current allocation cycle, never blocked_reason
        self.assertNotIn("blocked_reason", inspect.getsource(rs.state) + inspect.getsource(rs.classify))
        self.assertNotIn("blocked_reason", inspect.getsource(self.dc.blockage_cut))
        self.assertNotIn("blocked_reason", inspect.getsource(self.dc.backlog_cut))
        # the same read of golden_allocation.csv on both sides, keyed by request_id
        self.assertEqual(self.dc.in_cycle(self.gold), len(lp.Live(AS_OF).alloc_by_rid))
        # asked wins over an allocation row, including any new overlapping rows
        both = [rid for rid in via_cuts if rid in self.gold["outcome_by_request"] and rid in rs.current_allocation(self.gold["allocation"])]
        self.assertTrue(all(via_cuts[rid] == rs.ASKED for rid in both))
        self.assertEqual(rs.state("Open", None, None), "status gate: Open")
        self.assertEqual(rs.state("Open", None, {"allocated_to": "", "exception_reason": "something new: detail"}), "something new")
        self.assertEqual(rs.state("Open", {"request_id": "R"}, {"allocated_to": "x", "exception_reason": ""}), rs.ASKED)

    def test_blockage_is_the_classified_table_minus_asked_in_three_slices(self):
        """The Accounts donut and Remaining Unrouted: every state other than asked, bucketed by
        state and split into three slices over the blocked requests; nothing unmapped is dropped. Since
        bg.in_queue takes never-asked Closed - no path / Intro sent rows too, every one of the
        every one has an allocation row and the status gate holds nothing: the old "status gate:
        Closed - no path" wedge is now the allocator's own verdicts and "status gate: Intro
        sent" is the repair queue."""
        ab = self.dc.blockage_cut(self.gold)
        states = self.dc.request_states(self.gold)
        never = [rid for rid, s in states.items() if s != rs.ASKED]
        self.assertEqual(len(never), ab["never"])
        self.assertEqual(ab["never"], self.dc.backlog_cut(self.gold)["never"])
        self.assertEqual(sorted(ab["by_request"]), sorted(never), "every never-asked request lands in a bucket")
        self.assertEqual(ab["by_request"], {rid: states[rid] for rid in never}, "the bucket is the state")
        counts = Counter(states[rid] for rid in never)
        self.assertEqual(sum(b["count"] for b in ab["buckets"]), len(never), "each in exactly one")
        self.assertEqual({b["bucket"]: b["count"] for b in ab["buckets"]}, dict(counts))
        self.assertFalse([b for b in ab["buckets"] if b["bucket"].startswith(rs.STATUS_GATE)], "nothing held at the gate")
        # the populations every count is stated against
        self.assertEqual((ab["total"], ab["in_window"], ab["in_cycle"], ab["never"], ab["allocated"], ab["blocked"]),
                         (len(self.gold["requests"]), len(self.gold["requests"]), self.dc.in_cycle(self.gold),
                          len(never), counts[rs.ALLOCATED], len(never) - counts[rs.ALLOCATED]))
        expected_slices = {key: sum(counts[bucket] for bucket in buckets)
                           for key, (_, buckets) in rs.SLICES.items()}
        self.assertEqual({k: s["count"] for k, s in ab["slices"].items()}, expected_slices)
        for key, (_, members) in rs.SLICES.items():
            shown = [b["bucket"] for b in ab["slices"][key]["buckets"]]
            self.assertEqual(sorted(shown), sorted(m for m in members if counts[m]), f"{key}: its non-empty buckets")
            self.assertEqual([b["count"] for b in ab["slices"][key]["buckets"]],
                             sorted((counts[m] for m in shown), reverse=True), f"{key}: largest bucket first")
        self.assertEqual(ab["unmapped"], [])
        self.assertAlmostEqual(ab["supply_share"], expected_slices["supply"] / ab["blocked"])
        # the footnote: no path in supply_reach.csv, including any Intro sent claims the repair queue
        # holds before it gets to say so (the Closed - no path rows the gate used to
        # hold with no path are now in the allocator's own no-path bucket)
        self.assertEqual(ab["no_path"], sum(b["no_path"] for b in ab["buckets"] if b["bucket"] != rs.ALLOCATED))
        expected_gated = [b for b in ab["buckets"] if b["no_path"] and b["bucket"] != rs.ALLOCATED
                          and b["bucket"] not in rs.SLICES["supply"][1]]
        self.assertEqual(ab["no_path_gated"], expected_gated)
        repair = next(b for b in ab["buckets"] if b["bucket"] == bg.INTRO_CLAIMED_NOT_LOGGED)
        self.assertEqual(repair["with_path"] + repair["no_path"] + repair["unresolved"], repair["count"])
        # what the gate used to hold, by where the allocator put it
        current = rs.current_allocation(self.gold["allocation"])
        filed = {a["request_id"]: a["status_as_filed"] for a in current.values()}
        moved = Counter((filed[rid], ab["by_request"][rid]) for rid in never if filed.get(rid) in bg.REOPEN_STATUSES)
        for status in bg.REOPEN_STATUSES:
            self.assertEqual(sum(n for (filed_status, _), n in moved.items() if filed_status == status),
                             sum(1 for rid in never if filed.get(rid) == status), status)
        # the last-12-months view filters the same table
        bl12 = self.dc.blockage_cut(self.gold, since="2025-09-01")
        self.assertEqual(bl12["in_window"], sum(1 for r in self.gold["requests"] if r["request_date"] >= "2025-09-01"))
        self.assertTrue(set(bl12["by_request"]) <= set(ab["by_request"]))
        self.assertTrue(all(bl12["by_request"][rid] == ab["by_request"][rid] for rid in bl12["by_request"]))
        self.assertEqual(bl12["allocated"] + bl12["blocked"], bl12["never"])
        # an exception prefix build_golden.py could write that no slice claims is reported, never dropped
        current = rs.current_allocation(self.gold["allocation"])
        odd_id = next(rid for rid, b in ab["by_request"].items() if b == bg.NO_PATH)
        gold = dict(self.gold, allocation=[dict(a, exception_reason="something new: detail") if a["request_id"] == odd_id and a["cycle"] == current[odd_id]["cycle"] else a
                                            for a in self.gold["allocation"]])
        odd = self.dc.blockage_cut(gold)
        self.assertEqual([(b["bucket"], b["count"]) for b in odd["unmapped"]], [("something new", 1)])
        self.assertEqual((odd["slices"]["supply"]["count"], sum(b["count"] for b in odd["buckets"])),
                         (ab["slices"]["supply"]["count"] - 1, ab["never"]))

    def test_latency_medians_overall_and_by_month(self):
        lat = self.dc.latency_cut(self.gold, today=AS_OF)
        by_id = {r["request_id"]: r for r in self.gold["requests"]}
        to_ask = [(date.fromisoformat(o["asked_date"]) - date.fromisoformat(by_id[o["request_id"]]["request_date"])).days
                  for o in self.gold["outcomes"] if o["asked_date"].strip()]
        to_resp = [(date.fromisoformat(o["response_date"]) - date.fromisoformat(o["asked_date"])).days
                   for o in self.gold["outcomes"] if o["responded"] == "Y" and o["response_date"].strip()]
        to_intro = [(date.fromisoformat(o["intro_date"]) - date.fromisoformat(o["asked_date"])).days
                    for o in self.gold["outcomes"] if o["intro_sent"] == "Y" and o["intro_date"].strip()]
        self.assertEqual(lat["asks"], len(to_ask))
        self.assertEqual(lat["median_to_ask"], statistics.median(to_ask))
        self.assertEqual(lat["median_to_resp"], statistics.median(to_resp))
        self.assertEqual(lat["median_to_intro"], statistics.median(to_intro))
        self.assertEqual(lat["max_to_ask"], max(to_ask))
        self.assertLessEqual(lat["max_to_ask"], 7, "every ask on file went out inside a week")
        self.assertEqual(lat["asked_within_week"], len(to_ask))
        asked_ids = {o["request_id"] for o in self.gold["outcomes"]}
        expected_waiting = sum(1 for r in self.gold["requests"]
                               if r["request_id"] not in asked_ids
                               and (AS_OF - date.fromisoformat(r["request_date"])).days > lat["max_to_ask"])
        self.assertEqual(lat["waiting_past_max"], expected_waiting)
        months = sorted({r["request_date"][:7] for r in self.gold["requests"]})
        self.assertEqual([m["month"] for m in lat["monthly"]], months)
        self.assertEqual(sum(m["requests"] for m in lat["monthly"]), len(self.gold["requests"]))
        self.assertEqual(sum(m["asked"] for m in lat["monthly"]), lat["asks"])
        for m in lat["monthly"]:
            self.assertLessEqual(m["asked"], m["requests"], m["month"])
            if m["asked"] == 0:
                self.assertIsNone(m["to_ask"], m["month"])
        self.assertEqual(self.dc.latency_cut({"requests": [], "outcomes": []}, today=AS_OF)["median_to_ask"], None, "no asks, no median")


class TabPerimeterTest(unittest.TestCase):
    """Each tab reads one population throughout. Raw Sept: the September export
    in dataset/, before any upload, completion or allocation. Live Data:
    golden/current/ (dataset/ with the accepted uploads applied) plus golden/,
    the completions and the current cycle. Company $ on either tab is one value
    per company, and Live Data's $ foots to the Orientation strip on Live Priorities."""

    @classmethod
    def setUpClass(cls):
        from dashboard import data_cuts
        from paths import CURRENT, DATASET
        cls.dc, cls.DATASET, cls.CURRENT = data_cuts, DATASET, CURRENT
        cls.raw = data_cuts.load()
        cls.gold = data_cuts.load("golden", completions=[])

    def test_each_tab_reads_one_directory(self):
        self.assertEqual(self.raw["dir"], str(self.DATASET), "the Raw Sept tab reads the September export itself")
        self.assertEqual(self.gold["dir"], str(self.CURRENT), "the Live Data tab reads dataset/ with the accepted uploads applied")
        for mod in ("dashboard.build_dashboard", "dashboard.funnel_overview", "analysis.joins.join_rates",
                    "analysis.profile.profile_csvs", "analysis.integrity.integrity_audit"):
            src = (ROOT / (mod.replace(".", "/") + ".py")).read_text(encoding="utf-8")
            self.assertRegex(src, re.compile(r"^DATA(?:_DIR)? = (?:str\()?DATASET\)?$", re.M), f"{mod} feeds the Raw Sept tab: it reads dataset/")
            self.assertNotIn("CURRENT", src, f"{mod} feeds the Raw Sept tab only")

    def test_raw_tab_has_no_allocation_and_no_completion(self):
        self.assertEqual(self.raw["allocation"], [])
        self.assertEqual(self.raw["completions"], [])
        self.assertTrue(self.gold["allocation"], "the Live Data tab has the current cycle")
        self.assertTrue(all(r["allocated"] == 0 and not r["current"] for r in self.dc.cycle_cut(self.raw)["rows"]))

    def test_raw_tab_company_facts_are_the_september_export(self):
        raw_ids = [r["request_id"] for r in self.raw["requests"]]
        self.assertEqual(list(self.raw["golden_requests"]), raw_ids, "no request golden carried forward or ingested since")
        raw_by_id = {r["request_id"]: r for r in self.raw["requests"]}
        for rid, g in self.raw["golden_requests"].items():
            self.assertEqual(g["value_usd"], bg.money(raw_by_id[rid]["deal_value_usd"]), rid)
            self.assertEqual(g["status_as_filed"], raw_by_id[rid]["status"].strip(), rid)
            self.assertEqual(g["company_id"], self.gold["golden_requests"][rid]["company_id"], f"{rid}: the resolution is shared")
        arr = {a["account_id"]: int(a["arr_potential_usd"] or 0) for a in self.raw["crm"]}
        for cid, c in self.raw["golden_companies"].items():
            ids = [i for i in c["crm_account_ids"].split(bg.MULTI) if i]
            self.assertTrue(all(i in arr for i in ids), cid)
            self.assertEqual(c["value_usd"], str(max(arr[i] for i in ids)) if ids else "", cid)

    def test_a_later_upload_moves_the_live_tab_only(self):
        # a request re-filed at a new deal value, a CRM account re-priced, a request added: golden/current/ changes, dataset/ does not
        rid = next(r["request_id"] for r in self.raw["requests"] if self.gold["golden_requests"][r["request_id"]]["value_usd"]
                   and not self.gold["golden_companies"].get(self.gold["golden_requests"][r["request_id"]]["company_id"], {}).get("crm_account_ids"))
        bumped = {rid: dict(self.gold["golden_requests"][rid], value_usd="999999999")}
        sept = self.dc.september_requests(bumped, self.raw["requests"])
        self.assertEqual(sept[rid]["value_usd"], self.raw["golden_requests"][rid]["value_usd"], "the Raw Sept tab keeps the export's deal value")
        self.assertEqual(self.dc.september_requests({**bumped, "R999999": dict(bumped[rid], request_id="R999999")}, self.raw["requests"]).keys(), {rid},
                         "a request added since is not on the Raw Sept tab")
        cid, c = next((cid, c) for cid, c in self.gold["golden_companies"].items() if c["crm_account_ids"] and c["value_usd"])
        repriced = {cid: dict(c, value_usd="1", crm_account_ids=c["crm_account_ids"] + bg.MULTI + "A_NEW")}
        self.assertEqual(self.dc.september_companies(repriced, self.raw["crm"])[cid]["value_usd"], self.raw["golden_companies"][cid]["value_usd"])
        self.assertEqual(self.dc.september_companies(repriced, self.raw["crm"])[cid]["crm_account_ids"], c["crm_account_ids"])

    def test_live_data_dollars_foot_to_the_orientation_strip(self):
        live = lp.Live(AS_OF)
        S = live.stages()
        every = self.dc.dollars(self.gold, self.dc.rids(self.gold["requests"]))
        self.assertEqual(S["total"]["usd"] + S["excluded"]["usd"], every,
                         "one $ per company over every request on file = the strip + the closed companies it leaves off")
        self.assertEqual(S["total"]["count"] + S["excluded"]["count"],
                         len(self.dc.requests_by_company(self.gold)) + sum(1 for r in self.gold["requests"] if not self.gold["golden_requests"][r["request_id"]]["company_id"]),
                         "one cell per resolved company plus one per unresolved request")
        self.assertNotEqual(S["total"]["count"], len(self.gold["requests"]), "the strip counts companies, the funnel counts requests")

    def test_in_flight_total_prices_each_company_once(self):
        f = lp.Live(AS_OF).in_flight()
        rids = [rid for r in f["rows"] for rid in r["request_ids"]]
        self.assertEqual(len(rids), f["open"])
        self.assertEqual(f["value_usd"], self.dc.dollars(self.gold, rids))
        self.assertLessEqual(f["value_usd"], sum(r["value_usd"] for r in f["rows"]), "a company in several states is priced in each row, once in the total")


@unittest.skipUnless((ROOT / "docs" / "livedata.html").exists(), "run `python3 build.py dashboard` first")
class BuiltPagesTest(unittest.TestCase):
    """What `python3 build.py dashboard` writes under docs/."""

    @classmethod
    def setUpClass(cls):
        cls.docs = ROOT / "docs"
        cls.cards = lp.Live(AS_OF).connector_pages()
        cls.pages = {n: (cls.docs / n).read_text(encoding="utf-8") for n in
                     ["halyardscoping.html", "livedata.html", "companytrace.html", "livepriorities.html"]
                     + [c["page"] for c in cls.cards]}

    def test_masthead_and_tab_rows_on_every_page(self):
        data_tabs = {"halyardscoping.html", "livedata.html", "companytrace.html"}
        for name, html in self.pages.items():
            self.assertIn("<b>Halyard Baton</b> / intro routing console", html, name)
            self.assertIn('<svg class="logo"', html, name)
            self.assertEqual(html.count('.html" class="on">'), 1, f"{name}: exactly one tab is on")
            tabs = html.split('<div class="tabs">')[1].split("</div>")[0]
            self.assertEqual(re.findall(r'href="([^"#]+)"', tabs),
                             ["livepriorities.html", "batchask.html", "companytrace.html", "livedata.html", "halyardscoping.html"], name)
            if name in data_tabs:
                self.assertNotIn('<div class="tabs people">', html, f"{name}: the connector row belongs to Live Priorities")
                continue
            self.assertIn('<div class="tabs people">', html, name)
            for c in self.cards:
                self.assertIn(f'href="{c["page"]}"', html, f"{name} must link to {c['connector']}")
        self.assertIn(f'href="{self.cards[0]["page"]}" class="on"', self.pages[self.cards[0]["page"]])
        self.assertIn("--baton", self.pages["livepriorities.html"], "the connector row has its own colour")

    def test_connector_page_boots_its_own_card(self):
        for c in self.cards:
            html = self.pages[c["page"]]
            self.assertIn("LP.bootConnector(", html)
            blob = json.loads(html.split('<script id="lp-data" type="application/json">')[1].split("</script>")[0])
            self.assertEqual(blob["connector"], c["connector"])
            self.assertEqual([r["request_id"] for r in blob["top"]], [r["request_id"] for r in c["top"]])
            self.assertEqual(len(blob["rest"]), len(c["rest"]))

    def test_priorities_header_nav_and_back_to_top(self):
        html = self.pages["livepriorities.html"]
        for sid, label in lp.SECTIONS:
            self.assertIn(f'<a href="#{sid}">{label}</a>', html)
        for bid, *_ in lp.BANDS:
            self.assertIn(f'<a class="band" href="#band-{bid}">', html)
        for name, page in self.pages.items():
            self.assertEqual(page.count('<button class="totop"'), 1, name)

    def test_live_data_has_both_funnel_views(self):
        html = self.pages["livedata.html"]
        self.assertIn(">Cumulative<", html)
        self.assertIn(">Last 12 months<", html)
        self.assertIn('<div class="fview" data-view="all">', html)
        self.assertIn('<div class="fview" data-view="12m" hidden>', html)
        self.assertIn('id="sankey"', html)
        self.assertIn('id="sankey-12m"', html)

    STRATEGIC = ["funnel", "accounts", "requesters", "connectors", "latency", "cycles"]

    def sections(self, name):
        return re.findall(r'<(?:section|div class="divider") id="([^"]+)"', self.pages[name])

    def test_raw_sept_carries_the_live_charts_after_file_flow_and_joins_below_the_divider(self):
        html = self.pages["halyardscoping.html"]
        order = self.sections("halyardscoping.html")
        self.assertEqual(order[:9], ["flow", *self.STRATEGIC[:2], "urgency", *self.STRATEGIC[2:], "overview"], "Urgency follows Accounts before the remaining shared charts")
        self.assertEqual(order[order.index("integrity-divider"):],
                         ["integrity-divider", "joins", "targets", "quality", "verify", "integrity"],
                         "the divider sits right above Joins; Joins is above CSV Profile")
        self.assertLess(order.index("scoping"), order.index("integrity-divider"), "Slack Threads is strategic")
        self.assertIn('<div class="divider" id="integrity-divider">\n  <span class="t">Data integrity</span>', html)
        self.assertIn("Everything from here down checks the files themselves", html)
        # the sidebar walks the page in order, with the two bands
        side = html.split('<nav class="toc"')[1].split("</nav>")[0]
        self.assertEqual(re.findall(r'href="#([^"]+)"', side),
                         ["flow", "flow", *self.STRATEGIC[:2], "urgency", *self.STRATEGIC[2:], "overview", "timing", "scoping", "integrity-divider",
                          "joins", "targets", "quality", "verify", "integrity"])
        self.assertEqual(re.findall(r'<a class="band" href="#[^"]+">([^<]+)<', side), ["Strategic data", "Data integrity"])
        self.assertEqual(self.sections("livedata.html"), [self.STRATEGIC[0], "unrouted", "inflight", *self.STRATEGIC[1:]],
                         "Live Data alone carries Remaining Unrouted and Requests in Flight, right after the funnel")
        live_side = self.pages["livedata.html"].split('<nav class="toc"')[1].split("</nav>")[0]
        self.assertEqual(re.findall(r'href="#([^"]+)"', live_side), [self.STRATEGIC[0], "unrouted", "inflight", *self.STRATEGIC[1:]])
        self.assertNotIn('id="inflight"', html, "Raw Sept reads the exports as filed; nothing is in flight there")

    def test_requests_in_flight_shows_the_live_priorities_counts(self):
        """The table on Live Data is the in_flight payload rendered, so each count is
        the one the owning Live Priorities section shows."""
        html = self.pages["livedata.html"]
        F = lp.in_flight()
        section = html.split('<section id="inflight">')[1].split("</section>")[0]
        side = html.split('<nav class="toc"')[1].split("</nav>")[0]
        self.assertIn('href="#inflight"', side)
        self.assertIn(">Requests in Flight<", section)
        cells = re.findall(r'<tr><td>([^<]+)(?:<br>[^<]*<span class="foot">[^<]*</span>)?</td><td class="num"><b>(\d+)</b></td>', section)
        self.assertEqual(cells, [(r["label"], str(r["count"])) for r in F["rows"]], "one row per state, in flight order")
        self.assertIn(f'<th class="num">{F["open"]}</th>', section)
        for g in F["groups"]:
            self.assertIn(f'<tr class="group"><th colspan="6">{g["group"]} <span class="foot">{g["count"]} of the {F["open"]} in flight</span></th></tr>', section)
        for r in F["rows"]:
            self.assertIn(f'href="livepriorities.html#{r["section"]}"', section, f"{r['key']} links to the section that owns it")
            self.assertIn(f'<td class="num">{r["value_fmt"]}</td>', section)
        for key, label in (("nudge", "nudges"), ("chase", "chases")):
            n = next(r["count"] for r in F["rows"] if r["key"] == key)
            self.assertIn(f"{n} {label}", section)

    def test_the_two_tabs_render_the_same_charts_from_their_own_source(self):
        for name in ("halyardscoping.html", "livedata.html"):
            html = self.pages[name]
            ids = Counter(re.findall(r'\bid="([^"]+)"', html))
            self.assertEqual([k for k, v in ids.items() if v > 1], [], f"{name}: no id twice")
            live = name == "livedata.html"
            for div in ("sankey", "sankey-12m", "demand", "demand-12m", "req-asks", "req-value",
                        "req-accounts", "req-rate", "req-urgency", "connector-return", "latency-chart", "cycles-chart"):
                self.assertIn(f'id="{div}"', html, f"{name} draws {div}")
            for div in ("urgency-top", "urgency-total"):
                (self.assertNotIn if live else self.assertIn)(f'id="{div}"', html, f"{name}: Urgency belongs to Raw Sept")
            for div in ("blockage", "blockage-12m"):
                (self.assertIn if live else self.assertNotIn)(f'id="{div}"', html, f"{name}: Remaining Unrouted is Live Data only")
            self.assertEqual(html.count('data-view="all" role="tab">Cumulative<'), 3 if live else 2,
                             f"{name}: funnel and Top 20 toggles" + (", plus Remaining Unrouted" if live else ""))
            self.assertEqual(html.count("querySelectorAll('.seg[data-scope]')"), 1, f"{name}: the toggle script once")
        raw, live = self.pages["halyardscoping.html"], self.pages["livedata.html"]
        self.assertIn("<code>golden/completions.csv</code> applied", live)
        self.assertIn("exist only as a Submit on Live Priorities", live)
        self.assertNotIn("exist only as a Submit on Live Priorities", raw, "Raw Sept reads the exports as filed")
        self.assertIn("as filed; capacity used is roster asks", raw)
        self.assertIn("counts this build's allocation as slots used", live)

    def test_accounts_no_longer_repeats_the_blockage_donut(self):
        for name in ("halyardscoping.html", "livedata.html"):
            html = self.pages[name]
            self.assertNotIn("allocation-blockage", html, name)
            self.assertNotIn("Blockage by Allocation Exception", html, name)
            accounts = html.split('<section id="accounts">')[1].split("</section>")[0]
            self.assertNotIn("of the blockage is a missing relationship.", accounts, f"{name}: the donut lives in Remaining Unrouted only")

    def test_remaining_unrouted_cumulative_donut_reads_the_allocation(self):
        from dashboard import data_cuts
        bl = data_cuts.blockage_cut(data_cuts.load("golden"))
        live = self.pages["livedata.html"]
        panel = live.split('<section id="unrouted">')[1].split("</section>")[0]
        cumulative = panel.split('<div class="fview" data-view="all">')[1]
        self.assertIn(f"blocked\\u003cbr\\u003eof {bl['total']} requests on file", cumulative, "the denominator on the chart")
        values = [bl["slices"][key]["count"] for key in ("supply", "process", "closed")]
        self.assertIn('"values":' + json.dumps(values, separators=(",", ":")), cumulative)
        self.assertIn('"labels":["supply","process","correctly not asked"]', cumulative)
        for key in ("supply", "process", "closed"):
            for bucket in bl["slices"][key]["buckets"]:
                self.assertIn(f"{bucket['bucket']} {bucket['count']}", cumulative, "the tooltip names the prefixes it sums")
        for held in ("status gate: Closed - no path", "status gate: Intro sent"):
            self.assertNotIn(held, cumulative, "every filed status reaches the allocator now")
        caption = re.sub(r"<[^>]+>", "", cumulative)
        self.assertIn(f"{bl['never']} of the {bl['total']} requests on file never reach a connector; {bl['blocked']} of those are blocked. The other {bl['allocated']} are allocated this cycle and not yet asked; they carry a routed_to and are not blocked.", caption)
        self.assertIn(f"Only {bl['supply_share']:.0%} of the blockage is a missing relationship.", caption)
        repair = next(b for b in bl["buckets"] if b["bucket"] == bg.INTRO_CLAIMED_NOT_LOGGED)
        self.assertIn(f"{repair['bucket']} {repair['count']} ({repair['with_path']} with a path available, {repair['no_path'] + repair['unresolved']} without", caption)
        self.assertIn(f"{bl['no_path']} never-asked requests (of the {bl['total']} on file) name a company with no path in supply_reach.csv", caption)
        self.assertIn("dashboard/request_state.py", caption, "names the classifier both pages share")
        self.assertIn("blocked_reason is not an input", caption)
        gated_text = ", ".join(f"{bucket['no_path']} in {bucket['bucket']}" for bucket in bl["no_path_gated"])
        self.assertIn(f"({gated_text})", caption)
        self.assertNotIn("Outside the wedges", caption, "nothing unmapped this build")

    def test_live_data_opens_on_the_headline_kpis(self):
        from dashboard import data_cuts
        html = self.pages["livedata.html"]
        gold = data_cuts.load("golden")
        y, lat, b = data_cuts.yield_cut(gold), data_cuts.latency_cut(gold), data_cuts.backlog_cut(gold)
        strip = html.split('<div class="kpis headline">')[1].split("</div>\n\n")[0]
        self.assertLess(html.index('<div class="kpis headline">'), html.index('<section id="funnel">'), "the strip is above every section")
        labels = re.findall(r'<div class="l">([^<]+)</div>', strip)
        self.assertEqual(labels, ["opportunity value created", "return per ask", "median ask to intro",
                                  "median ask to first response", "reachable but never asked"])
        for text in (f"from {y['asks']} asks", f"{lat['median_to_intro']:g} d", f"{lat['median_to_resp']:g} d",
                     f"{b['with_path']} of {b['total']} requests on file, at {len(b['companies'])} companies with a path in supply_reach.csv, each counted once"):
            self.assertIn(text, strip)
        self.assertNotIn('class="kpis headline"', self.pages["halyardscoping.html"], "Raw Sept keeps its own top")

    def test_backlog_box_sits_under_the_sankey_with_no_yield_strip(self):
        from dashboard import data_cuts
        for name, source in (("halyardscoping.html", "dataset"), ("livedata.html", "golden")):
            b = data_cuts.backlog_cut(data_cuts.load(source))
            html = self.pages[name]
            funnel = html.split('<section id="funnel">')[1].split("</section>")[0]
            i = [funnel.index('id="sankey-12m"'), funnel.index('id="sankey"'),
                 funnel.index("<h3>Stage table, last 12 months</h3>"), funnel.index("<h3>Stage table</h3>")]
            self.assertEqual(i, sorted(i), f"{name}: sankeys, then the stage tables")
            self.assertEqual(funnel.count("never reach a connector.</b>"), 2, f"{name}: a backlog box under each sankey")
            self.assertNotIn("<h3>Yield</h3>", funnel, f"{name}: no yield strip")
            for label in ("routed to a connector", "routed per ask", "opportunity value created", "return per ask"):
                self.assertNotIn(f'<div class="l">{label}</div>', funnel, f"{name}: {label} left the funnel section")
            self.assertNotIn("Why they never reach a connector", funnel)
            self.assertEqual(funnel.count('data-scope="funnel"'), 1)
            for gone in ('id="unrouted"', "Remaining Unrouted", 'id="blockage"', "of the blockage is a missing relationship."):
                self.assertNotIn(gone, funnel, f"{name}: the unrouted donut is not inside the funnel section")
            self.assertIn(f"<b>{b['never']} of the {b['total']} requests on file never reach a connector.</b>", funnel)
            self.assertIn(f"{b['with_path']} of them are for {len(b['companies'])} companies that already have a path in <code>supply_reach.csv</code>, "
                          f"a backlog worth ${b['with_path_value'] / 1e6:.1f}M (one $ per company)", funnel)

    def test_remaining_unrouted_is_its_own_section_on_live_data_only(self):
        from dashboard import data_cuts  # never build_dashboard: importing it rewrites docs/
        from golden.clock import as_of
        gold = data_cuts.load("golden")
        bl = data_cuts.blockage_cut(gold)
        bl12 = data_cuts.blockage_cut(gold, since=(as_of() - timedelta(days=365)).isoformat())
        raw = self.pages["halyardscoping.html"]
        for gone in ('<section id="unrouted">', "Remaining Unrouted", 'id="blockage"', 'id="blockage-12m"', "of the blockage is a missing relationship."):
            self.assertNotIn(gone, raw, "Raw Sept has no Remaining Unrouted donut")
        html = self.pages["livedata.html"]
        self.assertEqual(html.count("<h2>Remaining Unrouted</h2>"), 1, "one section, toggled on its own")
        panel = html.split('<section id="unrouted">')[1].split("</section>")[0]
        i = [panel.index('id="unrouted-toggle" data-scope="unrouted"'), panel.index('id="blockage-12m"'), panel.index('id="blockage"')]
        self.assertEqual(i, sorted(i))
        self.assertIn('<button class="on" data-view="all" role="tab">Cumulative</button><button data-view="12m" role="tab">Last 12 months</button>', panel)
        self.assertIn('id="unrouted-window" data-all="', panel)
        self.assertIn(f"{bl['never']} of {bl['total']} requests on file never asked", panel)
        self.assertEqual(panel.count("of the blockage is a missing relationship."), 2, "a donut and its reading per view")
        self.assertNotIn("from <code>blocked_reason</code>", panel, "grouped by the request's state, not blocked_reason")
        self.assertIn(f"blocked\\u003cbr\\u003eof {bl['total']} requests on file", panel, "the denominator on the cumulative donut")
        self.assertIn("blocked\\u003cbr\\u003eof " + str(bl12["in_window"]) + " requests dated ", panel, "and on the last-12-months donut")
        self.assertIn('<div class="fview" data-view="12m" hidden>', panel)
        self.assertIn('<div class="fview" data-view="all">', panel)
        self.assertIn(f"{bl['never']} of the {bl['total']} requests on file never reach a connector; {bl['blocked']} of those are blocked. The other {bl['allocated']} are allocated this cycle and not yet asked", panel)
        self.assertIn(f"{bl12['never']} of the {bl12['in_window']} requests dated ", panel, "the 12-month view states its own population")
        self.assertIn(f"<b>Only {bl['supply_share']:.0%} of the blockage is a missing relationship.</b>", panel)
        self.assertIn("v.parentElement.closest(scopes) !== scope", html, "each toggle only flips its own views")

    def test_connectors_ranked_by_return_per_ask_and_a_latency_section(self):
        from dashboard import data_cuts
        for name, source in (("halyardscoping.html", "dataset"), ("livedata.html", "golden")):
            html = self.pages[name]
            cuts = data_cuts.load(source)
            ranked = data_cuts.connector_cut(cuts)["by_return"]
            block = html.split("<h3>Ranked by return per ask</h3>")[1].split("<h3>Routing ignores the roster notes</h3>")[0]
            self.assertIn("<th>Opp $</th><th>Per ask $</th><th>Per intro $</th>", block.replace("\n", ""), name)
            names = re.findall(r"<tr><td>\d+</td><td>([^<]+)</td>", block)
            self.assertEqual(names, [c["name"] for c in ranked], f"{name}: best return per ask first")
            self.assertEqual([c["opp_per_ask"] for c in ranked], sorted((c["opp_per_ask"] for c in ranked), reverse=True))
            lat = data_cuts.latency_cut(cuts)
            section = html.split('<section id="latency">')[1].split("</section>")[0]
            self.assertIn("<h2>Latency</h2>", section)
            self.assertIn("<b>A request not asked inside a week is never asked.</b>", section)
            self.assertIn(f"({lat['asked_within_week']} of {lat['asks']} inside seven)", section)
            self.assertIn('<th>Month requested</th>', section)
            self.assertEqual(len(re.findall(r"<tr><td>\d{4}-\d{2}</td>", section)), len(lat["monthly"]), f"{name}: one row a month")
            for label in ("median request to ask", "median ask to first response", "median ask to intro"):
                self.assertIn(f'<div class="l">{label}</div>', section, name)

    def test_live_data_top_20_by_asks_has_the_same_toggle_as_the_funnel(self):
        from dashboard import data_cuts
        html = self.pages["livedata.html"]
        self.assertEqual(html.count('data-view="all" role="tab">Cumulative<'), 3, "funnel, Remaining Unrouted and Top 20 each carry the toggle")
        self.assertIn('id="demand-toggle" data-scope="demand-views"', html)
        self.assertIn('id="demand"', html)
        self.assertIn('id="demand-12m"', html)
        cuts = data_cuts.load()
        every, recent = data_cuts.account_demand_cut(cuts), data_cuts.account_demand_cut(cuts, since="2026-01-01")
        self.assertGreater(every["asks"], recent["asks"], "the window drops older asks")
        self.assertTrue(0 < recent["asks"] == sum(b["requests"] for b in recent["companies"] + recent["unresolvable"]))
        cutoff = {r["request_id"] for r in cuts["golden_requests"].values() if r["request_date"][:10] >= "2026-01-01"}
        self.assertEqual(recent["asks"], len(cutoff))
        for b in recent["companies"]:
            self.assertGreaterEqual(next(e for e in every["companies"] if e["company_id"] == b["company_id"])["requests"],
                                    b["requests"], b["name"])
        self.assertEqual(data_cuts.account_demand_cut(cuts, since="2999-01-01")["asks"], 0, "an empty window does not divide by zero")


@unittest.skipUnless(NODE, "node is not installed")
class ParserParityTest(unittest.TestCase):
    """The upload preview's parser is the build's parser."""

    @classmethod
    def setUpClass(cls):
        cls.live = lp.Live(AS_OF)
        cls.parser = cls.live.parser()
        cls.res = load_resolver()

    def test_js_extracts_and_resolves_like_python(self):
        texts = [t["first"]["text"] for t in self.live.threads.values()]
        texts += [r["raw_ask"] for r in self.live.requests]
        texts += [t["messages"][0]["text"] for t in NEW_THREADS]
        texts += ["how about harrowgate health", "Harrowgate Health?", "how about thornbury financial",
                  "harrowgate health or quillon pharma, whichever is easier",
                  "can we connect with Quillon Pharma? harrowgate health is already a customer", "Not Harrowgate Health",
                  "how about kingsmere retail group", "how about xanthe labs", "Looking for a warm path into Zenner Foods"]
        js = run_node(self.parser, texts, [])["extracted"]
        self.assertEqual(len(js), len(texts))
        known = self.live.known_regex()
        bad = []
        for text, got in zip(texts, js):
            ex = gp.extract(text, self.res, known)
            want = {
                "mentions": [[m.start, m.text, m.cue, m.score, m.is_domain] for m in ex.mentions],
                "target": ex.target.text if ex.target else None,
                "target_id": ex.target.resolution.entity_id if ex.target and ex.target.resolution else "",
                "method": ex.target.resolution.method if ex.target and ex.target.resolution else "",
                "candidates": [c.entity_id for c in ex.target.resolution.candidates] if ex.target and ex.target.resolution else [],
            }
            if want != got:
                bad.append((text, want, got))
        self.assertEqual(bad, [], f"{len(bad)} of {len(texts)} texts parse differently in the browser")

    def test_preview_steps_over_a_connector_with_an_unresolved_ask_as_the_allocator_does(self):
        """Brightmoor Energy (C007): Elena agreed to R1190 and sent no intro, and she
        is the only path, so a new request there is an exception unless someone
        else offers. Kingsmere (C058): Yusuf offered once and is on nudge, so a new
        offer of his is not a route. Apex (C003): Marcus never answered R1069, long
        past the window, so he is askable but ranks behind Espen even offering."""
        held = self.live.held
        self.assertEqual((held[("Elena Duvall", "C007")]["hold"], held[("Yusuf Petrossian", "C058")]["hold"], held[("Marcus Aldridge", "C003")]["hold"]),
                         (bg.HOLD_NUDGE, bg.HOLD_NUDGE, bg.HOLD_LAST))
        ask = lambda rid, text, *replies: {"request_id": rid, "messages": [
            {"ts": "2026-09-05T10:00:00Z", "user": "Bea Marsh", "text": text},
            *({"ts": "2026-09-05T10:05:00Z", "user": who, "text": "happy to intro — I know their exec team"} for who in replies)]}
        threads = [ask("R3001", "who do we know at Brightmoor Energy?"),
                   ask("R3002", "who do we know at Brightmoor Energy?", "Dana Whitfield"),
                   ask("R3003", "we need Kingsmere Retail Group", "Yusuf Petrossian"),
                   ask("R3004", "we need Apex Holdings", "Marcus Aldridge")]
        pv = {r["request_id"]: r for r in run_node(self.parser, [], threads)["preview"]}
        P = self.parser
        self.assertEqual(pv["R3001"]["company_id"], "C007")
        self.assertEqual((pv["R3001"]["route_to"], pv["R3001"]["path"]), ("", bg.UNRESOLVED_ASK))
        self.assertEqual(pv["R3001"]["held"], [P["companies"]["C007"]["holds"]["Elena Duvall"]["reason"]])
        self.assertTrue(any(f.startswith(bg.UNRESOLVED_ASK) and "Elena Duvall agreed on 2026-07-06 (R1190)" in f for f in pv["R3001"]["flags"]))
        self.assertIsNone(P["companies"]["C007"]["best"])
        self.assertEqual([p["askable"] for p in P["companies"]["C007"]["paths"]], [False, False])
        self.assertEqual((pv["R3002"]["route_to"], pv["R3002"]["path"]), ("Dana Whitfield", f"offered in Slack ({P['companies']['C007']['offer_score']['Dana Whitfield']:.2f})"))
        self.assertEqual((pv["R3003"]["route_to"], pv["R3003"]["offer_by"]), (P["companies"]["C058"]["best"]["connector"], "Yusuf Petrossian"))
        self.assertNotIn("Yusuf Petrossian", [c["who"] for c in pv["R3003"]["cands"]])
        self.assertTrue(any(f.startswith("Yusuf Petrossian offers, but") and f.endswith("nudge them instead of asking afresh") for f in pv["R3003"]["flags"]))
        self.assertEqual(pv["R3004"]["route_to"], "Espen Rushworth-Oyelaran")
        self.assertEqual([(c["who"], c["hold"]) for c in pv["R3004"]["cands"]],
                         [("Espen Rushworth-Oyelaran", ""), ("Marcus Aldridge", bg.HOLD_LAST)])
        self.assertGreater(P["companies"]["C003"]["offer_score"]["Marcus Aldridge"], P["companies"]["C003"]["best"]["score"],
                           "his offer would outscore the network path; the hold, not the score, ranks him last")
        for rid in ("R3002", "R3003", "R3004"):
            self.assertNotIn(bg.UNRESOLVED_ASK, pv[rid]["path"])


@unittest.skipUnless(NODE, "node is not installed")
class ThreadsIngestTest(unittest.TestCase):
    """`build_golden.py --threads` does what the preview said it would."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="halyard-threads-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        shutil.copytree(ROOT / "dataset", self.root / "dataset")
        (self.root / "golden").mkdir()
        for p in (ROOT / "golden").iterdir():
            if p.suffix in (".py", ".csv"):
                shutil.copy(p, self.root / "golden" / p.name)
        self.upload = self.root / "new.jsonl"
        self.upload.write_text("".join(json.dumps(t) + "\n" for t in NEW_THREADS), encoding="utf-8")
        self.requests = self.root / "golden" / "golden_requests.csv"
        self.before = {r["request_id"]: r for r in read_csv(self.requests)}

    def build(self, *extra: str) -> str:
        proc = subprocess.run([sys.executable, str(self.root / "golden" / "build_golden.py"), "--as-of", AS_OF.isoformat(), *extra],
                              capture_output=True, text=True, cwd=self.root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc.stdout

    def test_threads_land_as_the_preview_showed(self):
        live = lp.Live(AS_OF)
        preview = {r["request_id"]: r for r in run_node(live.parser(), [], NEW_THREADS)["preview"]}
        out = self.build("--threads", str(self.upload))
        self.assertIn("4 appended", out)
        rows = {r["request_id"]: r for r in read_csv(self.requests)}
        self.assertEqual(len(rows), len(self.before) + 4)
        # routing and blocked_reason are conclusions and follow the allocation the new requests reshuffle
        conclusions = set(bg.ROUTING_COLUMNS) | {"blocked_reason"}
        self.assertEqual({k: v for k, v in rows["R1034"].items() if k not in conclusions},
                         {k: v for k, v in self.before["R1034"].items() if k not in conclusions},
                         "a thread for a filed request changes no filed fact")
        self.assertEqual(rows["R1034"]["blocked_reason"], bg.BLOCK_NO_PATH,
                         "the uploaded thread replaces the one carrying the only (off-roster) offer, so the recomputed block widens")

        for rid, first in (("R2001", NEW_THREADS[0]), ("R2002", NEW_THREADS[1]), ("R2003", NEW_THREADS[2]), ("R2004", NEW_THREADS[3])):
            r = rows[rid]
            if preview[rid]["company_id"]:
                self.assertEqual(r["company_id"], preview[rid]["company_id"], rid)
            self.assertEqual(r["requested_by"], first["messages"][0]["user"])
            self.assertEqual(r["request_date"], first["messages"][0]["ts"][:10])
            self.assertEqual(r["raw_ask"], first["messages"][0]["text"])
            self.assertEqual(r["status_as_filed"], "Open")
            self.assertEqual((r["value_usd"], r["urgency_declared"], r["target_title"]), ("", "", ""))
            self.assertIn("no deal value", r["needs_review"])
        self.assertEqual(rows["R2001"]["company_id"], "C018")
        self.assertEqual(rows["R2001"]["offer_in_thread"], "Y")
        self.assertEqual(preview["R2001"]["offer_by"], "Owen Trask")
        self.assertEqual(rows["R2002"]["company_id"], "")
        self.assertEqual(rows["R2002"]["blocked_reason"], "no company named in the ask")
        reach = read_csv(self.root / "golden" / "supply_reach.csv")
        self.assertTrue(any(s["connector"] == "Owen Trask" and s["company_id"] == "C018" and s["reach_type"] == "offer"
                            for s in reach), "the offer in the uploaded thread becomes supply")
        for s in reach:
            self.assertNotIn("new.jsonl R1034", s["evidence"])

        # A bare network name stays network-only until an accepted request files it. Once it is
        # on file, the same preview resolves it to that existing company instead of minting a duplicate.
        pv = preview["R2004"]
        self.assertEqual(pv["company_name"], "Xanthe Labs")
        xanthe = rows["R2004"]
        self.assertTrue(xanthe["company_id"])
        companies = {c["company_id"]: c for c in read_csv(self.root / "golden" / "golden_companies.csv")}
        self.assertEqual((companies[xanthe["company_id"]]["company_name"], companies[xanthe["company_id"]]["crm_account_ids"]),
                         ("Xanthe Labs", ""))
        filed = [s for s in reach if s["company_id"] == xanthe["company_id"]]
        if pv["network"]:
            self.assertEqual(pv["network"], "network:xanthelabs")
            self.assertIn("no CRM account, create one (see CRM Updates)", pv["flags"])
            shown = live.network_only[pv["network"]]["paths"]
            self.assertEqual(len(filed), len(shown))
            self.assertEqual({(s["connector"], s["reach_type"], s["contact_name"], s["strength"]) for s in filed},
                             {(s["connector"], s["reach_type"], s["contact_name"], s["strength"]) for s in shown})
        else:
            self.assertEqual(xanthe["company_id"], pv["company_id"])
            self.assertFalse(pv["network"])
        best, _ = bg.best_route(filed, live.roster, live.rates, "")
        self.assertEqual(pv["route_to"], best["connector"])

        again = self.build()
        dataset_ids = {r["request_id"] for r in read_csv(self.root / "dataset" / "intro_requests.csv")}
        carried = sum(rid not in dataset_ids for rid in rows)
        self.assertIn(f"{carried} not in dataset/intro_requests.csv and carried forward", again)
        self.assertIn("0 appended", again)
        after = {r["request_id"]: r for r in read_csv(self.requests)}
        for rid in ("R2001", "R2002", "R2003", "R2004"):
            self.assertEqual({k: v for k, v in after[rid].items() if k not in conclusions},
                             {k: v for k, v in rows[rid].items() if k not in conclusions},
                             f"{rid} survives a rebuild without --threads")


if __name__ == "__main__":
    unittest.main()
