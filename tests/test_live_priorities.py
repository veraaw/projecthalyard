"""The Live Priorities tab (dashboard/live_priorities.py + .js).

    python3 -m unittest tests.test_live_priorities

Three things are checked:

  1. the payload the page embeds — every section computed in Python, the browser
     only renders — states the facts the golden files state: 27 allocated in 8
     batches, 56 exceptions by reason (11 of them parked behind a live intro,
     and the fizzled ones labelled as retries), the four unanswered offers, the 23
     responded-but-no-intro asks, the 60-day check-in tests, importer-shaped
     CRM columns, and a company link into Company Trace on every company.
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
                         ["needs data", "to be routed", "routed", "asked", "introduced", "won"])
        reqs = read_csv(ROOT / "golden" / "golden_requests.csv")
        companies = {r["company_id"] for r in reqs if r["company_id"]}
        unresolved = [r for r in reqs if not r["company_id"]]
        self.assertEqual(sum(s["count"] for s in S["stages"]) + S["excluded"]["count"], len(companies) + len(unresolved),
                         "each company lands in exactly one stage (or is excluded as Closed - no path); "
                         "a request with no company stands alone")
        self.assertEqual(sum(s["unresolved"] for s in S["stages"]) + S["excluded"]["unresolved"], len(unresolved))
        self.assertEqual(S["total"]["companies"] + S["total"]["unresolved"], S["total"]["count"])
        self.assertEqual(S["excluded"]["stage"], "closed")

    def test_stage_dollars_are_one_value_per_company(self):
        """CRM ARR potential first, else the latest request's deal value; never the
        sum of a company's requests. A won company stays won whatever else is open on it."""
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
            if "won" in stages:
                self.assertEqual(stage, "won", f"{cid} is won, whatever else is open")
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
                         {"no path to this company in the network": 28, "already introduced": 11,
                          "company unresolved": 8, "capacity exhausted this cycle": 2})
        parked = next(e for e in A["exceptions"] if e["reason"] == "already introduced")
        for r in parked["rows"]:
            self.assertRegex(r["detail"], r"^.+ on \d{4}-\d{2}-\d{2} \(R1\d{3}(, meeting booked)?\)$", "the reason names the intro")
        companies = {c["company_id"]: c for c in read_csv(ROOT / "golden" / "golden_companies.csv")}
        for e in A["exceptions"]:
            for r in e["rows"]:
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
        self.assertEqual(I["requests"], len(parked), 11)
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
        # Redtree: fizzled, so back in the queue as a retry, with the prior intro named on every surface
        redtree = [c for b in P["asks"]["batches"] for c in b["companies"] if c["company_id"] == "C045"]
        self.assertEqual(len(redtree), 1)
        self.assertEqual(sorted(redtree[0]["request_ids"]), ["R1067", "R1074"])
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
            self.assertEqual(m["message"].count("retry:"), sum(1 for c in m["companies"] if c["retry"]), m["connector"])

    def test_offer_gaps(self):
        O = self.P["offer_gaps"]
        self.assertEqual(sorted(r["request_id"] for r in O["rows"]), ["R1034", "R1109", "R1115", "R1136"])
        self.assertEqual(sum(r["value_usd"] for r in O["rows"]), 3_750_000)
        self.assertEqual(O["value_fmt"], "$3.8M")
        r1109 = next(r for r in O["rows"] if r["request_id"] == "R1109")
        self.assertEqual(r1109["status"], "Closed - no path")
        self.assertEqual([o["who"] for o in r1109["offers"]], ["Owen Trask"])
        for r in O["rows"]:
            for o in r["offers"]:
                self.assertTrue(o["text"], "what they wrote")

    def test_bottlenecks_are_nudges(self):
        B = self.P["bottlenecks"]
        outcomes = read_csv(ROOT / "dataset" / "intro_outcomes.csv")
        expect = [o for o in outcomes if o["responded"].strip() == "Y" and o["intro_sent"].strip() != "Y"]
        self.assertEqual(B["count"], len(expect), 23)
        self.assertTrue(all(r["action"] == "nudge" for r in B["rows"]))
        self.assertTrue(all(r["days_since_agreed"] >= 0 for r in B["rows"]))
        self.assertEqual([r["days_since_agreed"] for r in B["rows"]],
                         sorted((r["days_since_agreed"] for r in B["rows"]), reverse=True))

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

    def test_checkins_lead_with_no_crm_touch_on_live_requests(self):
        K = self.P["checkins"]
        self.assertEqual(K["days"], 60)
        self.assertEqual(K["count"], len(K["rows"]))
        for r in K["rows"]:
            self.assertGreater(r["live_requests"], 0, "only companies with live requests are listed")
            self.assertTrue(r["touch_days"] is None or r["touch_days"] > 60, "only companies with no CRM touch in 60 days are listed")
            self.assertIn("CRM touch", r["failed"])
            self.assertEqual("intro ask" in r["failed"], r["ask_days"] is None or r["ask_days"] > 60, r)
        self.assertEqual(K["both"], sum(1 for r in K["rows"] if len(r["failed"]) == 2))
        self.assertEqual((K["unique"], K["owned"]), (sum(1 for r in K["rows"] if not r["owned_by"]), sum(1 for r in K["rows"] if r["owned_by"])))
        self.assertEqual(K["unique"] + K["owned"], K["count"])
        self.assertGreater(K["unique"], 0)
        self.assertGreater(K["owned"], 0)
        for r in K["rows"]:
            self.assertNotIn("checked_in_on", r, "no Supabase completion on this section")
        self.assertNotIn("checked_in", K)

    def test_checkins_point_at_the_section_that_owns_the_action(self):
        P, K = self.P, self.P["checkins"]
        elsewhere = {
            "top": {r["company_id"] for r in P["priorities"]["top"]},
            "asks": {c["company_id"] for b in P["asks"]["batches"] for c in b["companies"]},
            "introduced": {r["company_id"] for r in P["introduced"]["rows"]},
            "connectors": {s["company_id"] for c in P["connectors"] for s in c["sitting_on"]},
            "offers": {r["company_id"] for r in P["offer_gaps"]["rows"]},
            "bottlenecks": {r["company_id"] for r in P["bottlenecks"]["rows"]},
            "unrouted": {x["company_id"] for c in P["unrouted"]["per_connector"] for x in c["companies"]},
            "crm": {r["company_id"] for g in P["crm"]["groups"] for r in g["rows"]},
        }
        order = [s for s, _ in lp.SECTIONS]
        titles = dict(lp.SECTIONS)
        for r in K["rows"]:
            owners = [s for s in order if r["company_id"] in elsewhere.get(s, set())]
            self.assertEqual(r["owned_by"], owners[0] if owners else "", f"{r['company_name']}: first section in page order that lists it")
            self.assertEqual(r["owned_by_title"], titles.get(r["owned_by"], ""))
        owned_flags = [bool(r["owned_by"]) for r in K["rows"]]
        self.assertEqual(owned_flags, sorted(owned_flags), "the rows nothing else owns sort to the top")
        for group in ([r for r in K["rows"] if not r["owned_by"]], [r for r in K["rows"] if r["owned_by"]]):
            keys = [(-len(r["failed"]), -r["live_value_usd"], r["company_name"]) for r in group]
            self.assertEqual(keys, sorted(keys), "within each half: both tests failed first, then largest live value")

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
        self.assertEqual(row["routed_to"], ["Tomás Beckett"])
        self.assertEqual(row["requests"], ["R1136", "R1153"])
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
                         ["route", "upload", "stages", "top", "offers", "bottlenecks", "crm", "asks", "introduced", "connectors", "unrouted", "checkins"],
                         "intake, orientation, actionable now, current cycle, not moving")
        self.assertEqual([len(sections) for *_, sections in lp.BANDS], [2, 1, 4, 3, 2])
        folded = re.findall(r'<section id="([^"]+)">\$\{fold\(', boot)
        self.assertEqual(folded, ["offers", "bottlenecks", "crm", "asks", "introduced", "connectors", "unrouted", "checkins"], "the long tables start collapsed")
        self.assertIn('<section id="stages" class="masthead">', boot)
        self.assertNotIn("<table", boot.split('<section id="stages"')[1].split("</section>")[0], "orientation is one strip, no rows")
        self.assertIn("CRM Updates <span", boot)
        self.assertNotIn("What the CRM is missing", js)

    def test_bands_are_in_the_payload_and_cover_every_section(self):
        bands = lp.payload(AS_OF)["bands"]
        self.assertEqual([b["id"] for b in bands], ["intake", "orientation", "now", "cycle", "stuck"])
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
        data_tabs = {"halyardscoping.html", "livedata.html"}
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
        js = run_node(self.parser, texts, [])["extracted"]
        self.assertEqual(len(js), len(texts))
        bad = []
        for text, got in zip(texts, js):
            ex = gp.extract(text, self.res)
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
        preview = {r["request_id"]: r for r in run_node(lp.Live(AS_OF).parser(), [], NEW_THREADS)["preview"]}
        out = self.build("--threads", str(self.upload))
        self.assertIn("3 appended", out)
        rows = {r["request_id"]: r for r in read_csv(self.requests)}
        self.assertEqual(len(rows), len(self.before) + 3)
        self.assertEqual(rows["R1034"], self.before["R1034"], "a thread for a filed request changes no filed fact")

        for rid, first in (("R2001", NEW_THREADS[0]), ("R2002", NEW_THREADS[1]), ("R2003", NEW_THREADS[2])):
            r = rows[rid]
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

        again = self.build()
        self.assertIn("3 not in dataset/intro_requests.csv and carried forward", again)
        self.assertIn("0 appended", again)
        after = {r["request_id"]: r for r in read_csv(self.requests)}
        for rid in ("R2001", "R2002", "R2003"):
            self.assertEqual(after[rid], rows[rid], f"{rid} survives a rebuild without --threads")


if __name__ == "__main__":
    unittest.main()
