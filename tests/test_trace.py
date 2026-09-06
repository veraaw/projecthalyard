"""Tests for analysis/trace.py, checked against Harrowgate Health.

    python3 -m unittest tests.test_trace
"""
from __future__ import annotations

import sys
import unittest
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from analysis.trace import MISSED, OFFER, WARN, WORKED, Data, Trace, find_company, money  # noqa: E402
from dashboard import live_priorities as lp  # noqa: E402
from golden import build_golden as bg  # noqa: E402

AS_OF = date(2026, 9, 5)


class HarrowgateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = Data.load()
        cls.company = find_company(cls.data, "Harrowgate Health")
        cls.trace = Trace(cls.data, cls.company, AS_OF)
        cls.text = cls.trace.render()

    def test_lookup_by_id_alias_and_account(self):
        for q in ("C018", "A1050", "harrowgate health", "Harrowgate Health"):
            self.assertEqual(find_company(self.data, q)["company_id"], "C018", q)
        self.assertIsNone(find_company(self.data, "no such company"))

    def test_header_counts(self):
        reqs = self.trace.requests
        self.assertEqual(len(reqs), 9)
        self.assertEqual(len({r["requested_by"] for r in reqs}), 7)
        self.assertEqual(len({r["target_title"] for r in reqs}), 6)
        self.assertIn("9 requests from 7 people wanting 6 different titles", self.text)

    def test_header_hover_detail_traces_each_count_to_its_requests(self):
        h = self.trace.as_dict()["header"]
        rows = h["request_rows"]
        self.assertEqual(len(rows), h["requests"])
        self.assertEqual([q["request_id"] for q in rows],
                         [r["request_id"] for r in sorted(self.trace.requests, key=lambda r: (r["request_date"], r["request_id"]), reverse=True)],
                         "newest first")
        self.assertEqual(len({q["requested_by"] for q in rows}), h["people"])
        self.assertEqual(Counter(q["stage"] for q in rows), Counter(h["routing"]["counts"]), "the routed / closed hovers list exactly the counted requests")
        for q in rows:
            self.assertRegex(q["date"], r"^\d{4}-\d{2}-\d{2}")
            if q["stage"] == "routed":
                self.assertTrue(q["routed_to"], q["request_id"])
        self.assertTrue(any(q["intro_date"] for q in rows), "an intro on file shows its date along the way")
        v = h["value"]
        self.assertEqual(v["value_usd"], money(self.company["value_usd"]), "the company's one $, as on Live Priorities")
        self.assertEqual(v["source"], "CRM ARR potential")
        self.assertEqual([q["request_id"] for q in v["by_request"]], [q["request_id"] for q in rows], "the $ hover is per request, same order")

    def test_routing_furthest_and_latest_differ(self):
        """Two intros landed, but the latest request (R1057, Stalled) is still with the connector asked."""
        rt = self.trace.as_dict()["header"]["routing"]
        self.assertEqual(rt["furthest"], "introduced")
        self.assertEqual(rt["latest"], "asked")
        self.assertEqual(rt["latest"], self.trace.stage_of(next(r for r in self.trace.requests
                                                                  if r["request_id"] == self.company["latest_request_id"])))
        self.assertEqual(list(rt["counts"]), [s for s in [*bg.STAGES, "closed"] if s in rt["counts"]], "STAGES order")
        self.assertEqual(rt["counts"]["asked"], rt["awaiting_intro"]["agreed"] + rt["awaiting_intro"]["silent"])
        self.assertEqual(rt["awaiting_intro"], {"agreed": 2, "silent": 2})

    def test_disagreements(self):
        dis = "\n".join(self.trace.disagreements())
        self.assertIn('R1173: filed "Intro sent" but intro_outcomes.csv has no row', dis)
        self.assertIn('R1090: filed "Closed - no path" but supply_reach.csv has 11 paths', dis)
        self.assertIn("R1136: Elena Duvall offered", dis)

    def test_reach_sorted_by_route_score_not_strength(self):
        """Elena's Slack offer is the strongest raw path (0.800) but Healthcare is
        outside her focus, so the allocator scores it 0 and it ranks last; the
        table sorts the way the allocator does and shows both numbers."""
        scores = [self.trace.route_score(p) for p in self.trace.paths]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(self.trace.strongest()["connector"], "Elena Duvall")
        self.assertEqual(self.trace.paths[-1]["connector"], "Elena Duvall")
        self.assertNotEqual(self.trace.paths[0]["connector"], "Elena Duvall")
        reach = self.trace.as_dict()["reach"]
        self.assertEqual([r["route_score"] for r in reach], sorted((r["route_score"] for r in reach), reverse=True))
        self.assertEqual((reach[-1]["strength"], reach[-1]["route_score"], reach[-1]["fit"]), (0.8, 0.0, 0.0))
        self.assertIn("| route score | strength | connector |", self.text)

    def test_bypass_reason_sits_on_the_strongest_row(self):
        """Read off the roster, supply_reach.csv and this cycle's allocation rows,
        not best_path_if_unbudgeted."""
        why = self.trace.bypass()
        used = sum(a["allocated_to"] == "Elena Duvall" for a in self.data.allocation)
        cap = bg.capacity(self.data.roster, "Elena Duvall")
        load = f"at capacity {used}/{cap}" if used >= cap else f"{used}/{cap} used this cycle"
        self.assertTrue(why.startswith(f"Elena Duvall, offer 0.800, {load}, Healthcare is outside their focus (route score 0.000); "), why)
        rows = [a for a in self.data.allocation if a["company_id"] == "C018"]
        self.assertIn("R1153", [a["request_id"] for a in rows])
        for a in rows:
            self.assertIn(f"{a['request_id']} routed to {a['allocated_to']}" if a["allocated_to"]
                          else f"{a['request_id']} unrouted ({a['exception_reason']})", why)
        reach = self.trace.as_dict()["reach"]
        self.assertEqual([r["connector"] for r in reach if r["bypass"]], ["Elena Duvall"])
        self.assertEqual(reach[-1]["bypass"], why)
        self.assertIn(f"strongest path, not where it went: {why}", self.text)

    def test_chronology(self):
        events = self.trace.events()
        self.assertTrue(40 <= len(events) <= 55, len(events))
        self.assertEqual({e.source for e in events},
                         {"intro_requests.csv", "slack_threads.jsonl", "intro_outcomes.csv", "crm_accounts.csv"})
        n_slack = sum(len(t["messages"]) for rid, t in self.data.threads.items() if rid in self.trace.request_ids)
        self.assertEqual(sum(e.source == "slack_threads.jsonl" for e in events), n_slack)
        marks = {e.mark for e in events}
        self.assertTrue({MISSED, WORKED, OFFER, WARN} <= marks)
        # within a request block the lines are newest first, and so are the blocks
        line_blocks = "\n".join(self.trace.chronology()).split("\n\n")
        newest = []
        for line_block in line_blocks:
            dates = [ln[3:13] for ln in line_block.splitlines() if ln[3:7].isdigit()]
            self.assertEqual(dates, sorted(dates, reverse=True))
            newest.append(dates[0])
        request_blocks = newest[:-1]  # the CRM touch is its own block, last
        self.assertEqual(request_blocks, sorted(request_blocks, reverse=True))
        self.assertIn("newest first", self.text)
        self.assertNotIn("Next steps", self.text)


class RoutingStageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = Data.load()
        cls.traced = [c for c in cls.data.companies if int(c["total_requests"] or 0)]

    def test_every_request_closed(self):
        c = find_company(self.data, "Quillon Pharma")
        t = Trace(self.data, c, AS_OF)
        self.assertTrue(all(r["status_as_filed"] == "Closed - no path" for r in t.requests))
        rt = t.as_dict()["header"]["routing"]
        self.assertEqual(rt["furthest"], "closed")
        self.assertEqual(rt["latest"], "closed")
        self.assertEqual(rt["counts"], {"closed": len(t.requests)})
        self.assertEqual(rt["awaiting_intro"], {"agreed": 0, "silent": 0})

    def test_counts_sum_to_total_requests(self):
        for c in self.traced:
            d = Trace(self.data, c, AS_OF).as_dict()
            rt = d["header"]["routing"]
            self.assertEqual(sum(rt["counts"].values()), int(c["total_requests"]), c["company_id"])
            self.assertEqual(sum(rt["counts"].values()), d["header"]["requests"], c["company_id"])
            self.assertIn(rt["furthest"], [*bg.STAGES, "closed"])
            self.assertIn(rt["latest"], [*bg.STAGES, "closed"], c["company_id"])
            if rt["furthest"] == "closed":
                self.assertEqual(set(rt["counts"]), {"closed"}, c["company_id"])
            if rt["furthest"] == "meeting booked":
                b = rt["booked"]
                self.assertTrue(b and b["request_id"] and b["connector"], c["company_id"])
                o = next(o for o in self.data.outcomes[b["request_id"]] if o["connector_asked"] == b["connector"])
                self.assertEqual((o["meeting_booked"], o["intro_date"]), ("Y", b["intro_date"]), "the intro that landed the meeting, dated by its intro_date")
            else:
                self.assertIsNone(rt["booked"], c["company_id"])

    def test_stage_of_agrees_with_live_priorities(self):
        """build_golden.stage_of is the one taxonomy: Live Priorities' stage_of is a
        delegate to it, and the trace's furthest stage is Live Priorities' company stage."""
        L = lp.Live(AS_OF)
        for r in bg.read_csv(ROOT / "golden" / "golden_requests.csv"):
            rid = r["request_id"]
            self.assertEqual(bg.stage_of(r, L.outcome_by_rid.get(rid), L.alloc_by_rid.get(rid)), L.stage_of(r), rid)
            self.assertEqual(bg.stage_of(r, self.data.outcome_by_rid.get(rid), self.data.alloc_by_rid.get(rid)),
                             L.stage_of(r), rid)
        for c in self.traced:
            self.assertEqual(Trace(self.data, c, AS_OF).routing()["furthest"], L.company_stage(c["company_id"]), c["company_id"])


class NoDisagreementTest(unittest.TestCase):
    def test_section_two_skipped_when_clean(self):
        data = Data.load()
        clean = [c for c in data.companies if int(c["total_requests"] or 0) and not Trace(data, c, AS_OF).disagreements()]
        self.assertTrue(clean, "expected at least one company with nothing to disagree about")
        self.assertNotIn("## 2.", Trace(data, clean[0], AS_OF).render())


if __name__ == "__main__":
    unittest.main()
