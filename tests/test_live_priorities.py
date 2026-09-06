"""The Live Priorities tab (dashboard/live_priorities.py + .js).

    python3 -m unittest tests.test_live_priorities

Three things are checked:

  1. the payload the page embeds — every section computed in Python, the browser
     only renders — states the facts the golden files state: 27 allocated in 8
     batches, 56 exceptions by reason (11 of them parked behind a live intro,
     and the fizzled ones labelled as retries), the 23 responded-but-no-intro
     asks, importer-shaped CRM columns, and a company link into Company Trace on
     every company.
  2. the upload preview parses like the build: the JavaScript parser (run under
     node) picks the same target and resolves it the same way as golden/parse.py
     + golden/resolver.py on every Slack first message and every raw_ask.
  3. `build_golden.py --threads FILE` — the command the page shows — files the
     previewed threads as requests, keeps them on a later plain rebuild, and
     lands the same company_id and offer the preview showed.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dashboard import live_priorities as lp  # noqa: E402
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
            cs = c["path_strength"] * c["focus_fit"] * c["delivery_rate"] * c["capacity_left"]
            self.assertAlmostEqual(r["request_priority"], rp, places=2, msg=r["request_id"])
            self.assertAlmostEqual(r["connector_score"], cs, places=2, msg=r["request_id"])
            self.assertAlmostEqual(r["expected_value"], rp * cs, places=2, msg=r["request_id"])
            self.assertEqual(c["reps_waiting"], len(r["reps"]))
            self.assertLessEqual(c["age"], 2.0)
        self.assertIn("request priority × connector score", T["formula"]["expected_value"])
        self.assertEqual(T["formula"]["stage_weight"]["Negotiation"], lp.STAGE_WEIGHT["Negotiation"])

    def test_current_asks_match_golden_allocation(self):
        A = self.P["asks"]
        alloc = read_csv(ROOT / "golden" / "golden_allocation.csv")
        allocated = [r for r in alloc if r["allocated_to"]]
        self.assertEqual(A["allocated"], len(allocated), 27)
        self.assertEqual(len(A["batches"]), len({r["batch_id"] for r in allocated}), 8)
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
        self.assertEqual(A["exception_count"], len(alloc) - len(allocated), 56)
        self.assertEqual({e["reason"]: e["count"] for e in A["exceptions"]},
                         {"no path to this company in the network": 28, "already introduced": 10,
                          "company unresolved": 9, "capacity exhausted this cycle": 10, bg.UNRESOLVED_ASK: 1})
        held = next(e for e in A["exceptions"] if e["reason"] == bg.UNRESOLVED_ASK)
        for r in held["rows"]:
            self.assertRegex(r["detail"], r"agreed on \d{4}-\d{2}-\d{2} \(R1\d{3}\), no intro - nudge|no reply - day \d+ of \d+")
        # capacity exhausted: the other requests on the account routed this cycle are named
        capacity = next(e for e in A["exceptions"] if e["reason"] == bg.CAPACITY_EXHAUSTED)
        routed = {a["request_id"]: a["allocated_to"] for a in allocated}
        for r in capacity["rows"]:
            self.assertEqual(r["routed_here"],
                             [{"request_id": rid, "connector": routed[rid]} for rid in sorted(routed)
                              if next(a for a in alloc if a["request_id"] == rid)["company_id"] == r["company_id"]])
        by_rid = {r["request_id"]: r for r in capacity["rows"]}
        self.assertEqual(by_rid["R1041"]["routed_here"], [{"request_id": "R1024", "connector": "Marcus Aldridge"}])
        self.assertEqual(by_rid["R1004"]["routed_here"], [], "nothing else on Marchford Clinics routed this cycle")
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
        # no path: who on the roster covers the sector, so the blank cell becomes a named person
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
        self.assertEqual(I["requests"], len(parked), 14)
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
                 | {x["company_id"] for c in P["unrouted"]["per_connector"] for x in c["companies"]})
        self.assertEqual(parked_cos & fresh, set())
        for m in L.batch_asks:
            self.assertEqual({q["company_id"] for q in m["requests"]} & parked_cos, set(), m["connector"])
        # Redtree: fizzled, so back in the queue as a retry, with the prior intro named on
        # every surface; R1003 itself (the request that intro was for) is back alongside
        redtree = [c for b in P["asks"]["batches"] for c in b["companies"] if c["company_id"] == "C045"]
        self.assertEqual(len(redtree), 1)
        self.assertEqual(sorted(redtree[0]["request_ids"]), ["R1003", "R1067", "R1074"])
        retry = redtree[0]["retry"]
        self.assertEqual((retry["connector"], retry["intro_date"], retry["request_id"], retry["requested_by"], retry["meeting_booked"], retry["live"]),
                         ("Dana Whitfield", "2026-03-18", "R1003", "Imani Mkhize", False, False))
        self.assertGreater(retry["days"], bg.INTRO_LIVE_DAYS)
        self.assertIn("Dana's 2026-03-18 intro to Imani Mkhize went nowhere", retry["note"])
        self.assertIn("C045", [r["company_id"] for r in I["retries"]])
        self.assertEqual(I["retry_requests"], sum(len(r["request_ids"]) for r in I["retries"]))
        dana = next(c for c in P["connectors"] if c["connector"] == "Dana Whitfield")
        self.assertTrue(all(q["retry"] for q in dana["queue"] if q["company_id"] == "C045"))
        self.assertIn("retry: you introduced Imani Mkhize there on 2026-03-18", dana["batch_ask"]["message"])
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
        self.assertNotIn("R1154", [r["request_id"] for r in P["bottlenecks"]["rows"]], "the old reply is not a nudge")
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
        self.assertIn("Marcus's 2026-03-11 intro to Yusuf Petrossian went nowhere", s["retry"]["note"])
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
        self.assertIn("Elena's 2026-06-10 intro to Nadia Okonkwo went nowhere: meeting booked, no opportunity", r1024["retry"]["note"])
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

    def test_bottlenecks_are_nudges(self):
        B = self.P["bottlenecks"]
        outcomes = read_csv(ROOT / "dataset" / "intro_outcomes.csv")
        expect = [o for o in outcomes if o["responded"].strip() == "Y" and o["intro_sent"].strip() != "Y"]
        self.assertEqual(B["count"], len(expect), 23)
        self.assertTrue(all(r["action"] == "nudge" for r in B["rows"]))
        self.assertTrue(all(r["days_since_agreed"] >= 0 for r in B["rows"]))
        self.assertEqual([r["days_since_agreed"] for r in B["rows"]],
                         sorted((r["days_since_agreed"] for r in B["rows"]), reverse=True))
        L = lp.Live(AS_OF)
        for r in B["rows"]:
            if r["company_id"]:
                self.assertEqual((r["value_usd"], r["value_source"]), L.company_value(r["company_id"]),
                                 f"{r['request_id']}: the company's one $ as on Company Trace, not the request's")
        self.assertNotIn("value_fmt", B, "no request-value total on the section")

    def test_connectors(self):
        C = self.P["connectors"]
        self.assertEqual([c["connector"] for c in C],
                         ["Marcus Aldridge", "Dana Whitfield", "Priya Raghunathan", "Tomás Beckett", "Elena Duvall", "Owen Trask"])
        for c in C:
            self.assertEqual(c["used"], c["asked_this_cycle"] + c["allocated_this_cycle"])
            self.assertEqual(c["used"] + c["idle"], c["capacity"], c["connector"])
            self.assertEqual(len(c["queue"]), c["allocated_this_cycle"])
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
        self.assertEqual(X["actions"], {"top": "ask_sent", "bottlenecks": "nudged", "nudge": "nudged", "chase": "chased"})
        self.assertNotIn(lp.bg.CHECKED_IN, X["actions"].values(), "a check-in is not ticked or posted anywhere")
        self.assertEqual(X["quiet_days"], lp.NUDGE_QUIET_DAYS)
        self.assertNotIn("checkin_days", X)
        js = (ROOT / "dashboard" / "live_priorities.js").read_text(encoding="utf-8")
        self.assertNotIn("account_created", js)
        self.assertNotIn("crmTick", js)
        self.assertNotIn("checkinTick", js)
        self.assertNotIn("checked_in", js)
        for name in ("askTick", "nudgeTick", "followTick"):
            self.assertIn(f"const {name} = ", js)

    def test_unrouted_in_focus(self):
        U = self.P["unrouted"]
        self.assertEqual(U["finding"]["in_focus_pct"], "64%")
        self.assertEqual(U["finding"]["out_focus_pct"], "32%")
        self.assertEqual(U["finding"]["in_focus_asks"], 14)
        for c in U["per_connector"]:
            focus = set(c["focus"])
            for co in c["companies"]:
                self.assertIn(co["industry"], focus, f"{co['company_name']} is outside {c['connector']}'s focus")

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
        self.assertEqual(names[:6], [c["connector"] for c in self.P["connectors"]], "roster first, roster order")
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
        self.assertEqual(row["requests"], ["R1136", "R1140", "R1153"])
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
                         ["route", "upload", "stages", "top", "crm", "asks", "introduced", "connectors", "exceptions", "unrouted", "bottlenecks"],
                         "intake, orientation, actionable now, current cycle")
        self.assertEqual([len(sections) for *_, sections in lp.BANDS], [2, 1, 2, 6], "no Not Moving band")
        self.assertTrue(all(all(w[0].isupper() or w in ("a", "an", "and", "by", "of", "the") for w in label.replace("—", " ").split())
                            for _, label in lp.SECTIONS), "nav labels in Title Case")
        self.assertIn("Unrouted Exceptions <span", boot)
        asks = boot.split('<section id="asks"')[1].split('<section id=')[0]
        self.assertNotIn("EXCEPTION_TITLE", asks, "exceptions have their own section, not a fold inside Current Asks")
        folded = re.findall(r'<section id="([^"]+)">\$\{fold\(', boot)
        self.assertEqual(folded, ["crm", "asks", "introduced", "connectors", "exceptions", "unrouted", "bottlenecks"], "the long tables start collapsed")
        self.assertIn('<section id="stages" class="masthead">', boot)
        self.assertNotIn("<table", boot.split('<section id="stages"')[1].split("</section>")[0], "orientation is one strip, no rows")
        self.assertIn("CRM Updates <span", boot)
        self.assertNotIn("What the CRM is missing", js)

    def test_bands_are_in_the_payload_and_cover_every_section(self):
        bands = lp.payload(AS_OF)["bands"]
        self.assertEqual([b["id"] for b in bands], ["intake", "orientation", "now", "cycle"])
        self.assertEqual([s for b in bands for s in b["sections"]], [sid for sid, _ in lp.SECTIONS])
        self.assertTrue(all(b["title"] and b["test"].endswith("?") for b in bands))


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

    def test_live_data_top_20_by_asks_has_the_same_toggle_as_the_funnel(self):
        from dashboard import data_cuts
        html = self.pages["livedata.html"]
        self.assertEqual(html.count('data-view="all" role="tab">Cumulative<'), 2, "funnel and Top 20 each carry the toggle")
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
            if rid != "R2004":   # the build mints the network-only company's id; the preview has none to show
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

        # a bare network-only name: the preview showed the company the network reaches, with
        # no id and no CRM account, and the paths it would get; the build creates it and files them
        pv = preview["R2004"]
        self.assertEqual((pv["company_id"], pv["network"], pv["company_name"]), ("", "network:xanthelabs", "Xanthe Labs"))
        self.assertIn("no CRM account, create one (see CRM Updates)", pv["flags"])
        xanthe = rows["R2004"]
        self.assertTrue(xanthe["company_id"])
        companies = {c["company_id"]: c for c in read_csv(self.root / "golden" / "golden_companies.csv")}
        self.assertEqual((companies[xanthe["company_id"]]["company_name"], companies[xanthe["company_id"]]["crm_account_ids"]),
                         ("Xanthe Labs", ""))
        filed = [s for s in reach if s["company_id"] == xanthe["company_id"]]
        shown = live.network_only["network:xanthelabs"]["paths"]
        self.assertEqual(len(filed), len(shown))
        self.assertEqual({(s["connector"], s["reach_type"], s["contact_name"], s["strength"]) for s in filed},
                         {(s["connector"], s["reach_type"], s["contact_name"], s["strength"]) for s in shown})
        best, _ = bg.best_route(filed, live.roster, live.rates, "")
        self.assertEqual(pv["route_to"], best["connector"])

        again = self.build()
        self.assertIn("4 not in dataset/intro_requests.csv and carried forward", again)
        self.assertIn("0 appended", again)
        after = {r["request_id"]: r for r in read_csv(self.requests)}
        for rid in ("R2001", "R2002", "R2003", "R2004"):
            self.assertEqual({k: v for k, v in after[rid].items() if k not in conclusions},
                             {k: v for k, v in rows[rid].items() if k not in conclusions},
                             f"{rid} survives a rebuild without --threads")


if __name__ == "__main__":
    unittest.main()
