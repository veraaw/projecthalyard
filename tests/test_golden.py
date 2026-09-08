"""Tests for the golden dataset.

    python3 -m unittest tests.test_golden

Every assertion here corresponds to a bug that actually occurred while building
this, not a hypothetical. That is the point: a test suite written from
imagination tests what you already thought of.

Counts are derived from the files, never fixed: a rebuild merges (see
tests/test_rebuild.py), so golden_requests.csv grows over time. Run after every
regeneration and before every rehearsal.
"""
from __future__ import annotations

import csv
import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from golden import build_golden as bg  # noqa: E402

G = ROOT / "golden"
D = ROOT / "dataset"

# supply_reach was once the raw connection export: 4,975 of 5,075 rows pointed
# at companies nobody sells to.
DECOYS = {"Inglenook Bakery", "Tannerly Design", "Corbridge Realty",
          "Whitlock Staffing", "Bellchamber Media", "Elmsworth Tutors",
          "Ambrose Trading", "Fairbourne Fitness", "Yardley Print", "Zenner Foods"}
UNRESOLVED = {"empty", "unresolved", "fund-collision"}


def rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


class GoldenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.companies = rows(G / "golden_companies.csv")
        cls.requests = rows(G / "golden_requests.csv")
        cls.reach = rows(G / "supply_reach.csv")
        cls.allocation = rows(G / "golden_allocation.csv")
        cls.source = rows(D / "intro_requests.csv")
        cls.crm = rows(D / "crm_accounts.csv")
        cls.company_ids = {c["company_id"] for c in cls.companies}

    # ── 1. structure ───────────────────────────────────────────────────
    def test_every_row_has_the_headers_field_count(self):
        # A row with an unescaped comma in a multi-value cell has more fields
        # than the header, and every column after it silently shifts. This is
        # how a sample row showed an owner where the stage should be.
        for fn, data in [("golden_companies.csv", self.companies),
                         ("golden_requests.csv", self.requests),
                         ("supply_reach.csv", self.reach)]:
            with self.subTest(file=fn):
                with open(G / fn, newline="", encoding="utf-8") as fh:
                    r = csv.reader(fh)
                    header = next(r)
                    ragged = [i for i, row in enumerate(r, 2) if len(row) != len(header)]
                self.assertEqual(ragged, [], f"ragged rows at lines {ragged[:5]}")
                self.assertTrue(all(None not in d for d in data), "row longer than header")

    # ── 2. grain and uniqueness ────────────────────────────────────────
    def test_one_row_per_request_id(self):
        dupes = [k for k, n in Counter(r["request_id"] for r in self.requests).items() if n > 1]
        self.assertEqual(dupes, [])

    def test_one_row_per_company_id(self):
        dupes = [k for k, n in Counter(c["company_id"] for c in self.companies).items() if n > 1]
        self.assertEqual(dupes, [])

    def test_supply_reach_unique_on_connector_company_type_contact(self):
        key = lambda x: (x["connector"], x["company_id"], x["reach_type"], x["contact_name"])
        dupes = [k for k, n in Counter(map(key, self.reach)).items() if n > 1]
        self.assertEqual(dupes, [], f"{len(dupes)} duplicates")

    # ── 3. referential integrity ───────────────────────────────────────
    def test_every_requests_company_exists(self):
        orphans = {r["company_id"] for r in self.requests
                   if r["company_id"] and r["company_id"] not in self.company_ids}
        self.assertEqual(orphans, set())

    def test_every_reach_rows_company_exists(self):
        orphans = {x["company_id"] for x in self.reach
                   if x["company_id"] and x["company_id"] not in self.company_ids}
        self.assertEqual(orphans, set())

    # ── 4. conservation — nothing may vanish ───────────────────────────
    def test_every_source_request_is_present(self):
        # A rebuild merges: the file may hold more than the export (live routes,
        # ingested threads), never less.
        filed = {r["request_id"] for r in self.requests}
        missing = sorted({r["request_id"] for r in self.source} - filed)
        self.assertEqual(missing, [], f"{len(missing)} export rows missing from golden_requests.csv")

    def test_unresolvable_requests_have_no_company_and_vice_versa(self):
        no_company = {r["request_id"] for r in self.requests if not r["company_id"]}
        unresolved = {r["request_id"] for r in self.requests if r["resolved_by"] in UNRESOLVED}
        self.assertEqual(no_company, unresolved)
        self.assertTrue(unresolved, "every dataset so far has had unresolvable asks; none is suspicious")

    # ── 5. regression tests for bugs that actually happened ────────────
    def test_apex_logistics_and_apex_logistics_group_stay_separate(self):
        # The normaliser stripped "Group" and merged two different companies.
        apex = {c["company_id"] for c in self.companies
                if "Apex" in c["company_name"] or "Apex" in (c["also_known_as"] or "")}
        self.assertGreaterEqual(len(apex), 2, f"found {len(apex)} Apex companies")

    def test_blackwood_resolves_despite_crm_trading_name_mismatch(self):
        # Path lookup keyed on the CRM name missed the trading name.
        black = [c for c in self.companies if "Blackwood" in c["company_name"]
                 or "Blackwood" in (c["also_known_as"] or "")]
        self.assertTrue(black)

    def test_aliases_are_populated_where_the_crm_renames_a_company(self):
        n = sum(1 for c in self.companies if c["also_known_as"])
        self.assertGreaterEqual(n, 5, f"{n} companies with aliases")

    def test_duplicate_crm_clusters_match_the_crm(self):
        # The CRM holds the same company twice, sometimes under two owners.
        by_domain = defaultdict(list)
        for a in self.crm:
            by_domain[a["domain"].lower()].append(a)
        clusters = {d: v for d, v in by_domain.items() if len(v) > 1}
        disagree = {d for d, v in clusters.items() if len({a["owner"] for a in v}) > 1}
        self.assertTrue(clusters, "the CRM export has always held duplicates")
        flagged = {c["domain"]: c["duplicate_accounts"] for c in self.companies
                   if c["duplicate_accounts"] != "no"}
        self.assertEqual(set(flagged), set(clusters))
        self.assertEqual({d for d, v in flagged.items() if "disagree" in v}, disagree)

    def test_no_out_of_scope_companies_in_supply_reach(self):
        leaked = DECOYS & {x["company_name"] for x in self.reach}
        self.assertEqual(leaked, set())
        self.assertLess(len(self.reach), 500, "supply_reach is a filtered view, not the raw export")

    def test_all_path_kinds_survive_the_filter(self):
        # Board seats are investor paths (roster or investor_network) with
        # board_seat = yes (a strength modifier, not a separate mechanism).
        kinds = Counter(x["reach_type"] for x in self.reach)
        for k in ("direct", "alumni", "offer", "investor", bg.INVESTOR_NETWORK):
            with self.subTest(reach_type=k):
                self.assertGreater(kinds[k], 0)
        seats = [x for x in self.reach if x["board_seat"] == "yes"]
        self.assertTrue(seats)
        self.assertTrue(all(x["reach_type"] in ("investor", bg.INVESTOR_NETWORK) for x in seats))

    def test_every_connector_appears_at_least_once(self):
        # Every askable person must appear, even with no path.
        connectors = {x["connector"] for x in self.reach}
        self.assertGreaterEqual(len(connectors), 6, f"{len(connectors)} connectors present")

    # ── 6. cross-file agreement ────────────────────────────────────────
    def test_total_requests_matches_the_request_rows(self):
        by_company = Counter(r["company_id"] for r in self.requests if r["company_id"])
        mismatched = [c["company_name"] for c in self.companies
                      if int(c["total_requests"]) != by_company[c["company_id"]]]
        self.assertEqual(mismatched, [])
        self.assertEqual(sum(by_company.values()),
                         sum(int(c["total_requests"]) for c in self.companies))

    def test_paths_available_matches_supply_reach(self):
        by_company = Counter(x["company_id"] for x in self.reach)
        bad = [c["company_name"] for c in self.companies
               if int(c["paths_available"]) != by_company[c["company_id"]]]
        self.assertEqual(bad, [])

    def test_durable_paths_excludes_offers(self):
        durable = Counter(x["company_id"] for x in self.reach if x["reach_type"] != "offer")
        bad = [c["company_name"] for c in self.companies
               if int(c["durable_paths"]) != durable[c["company_id"]]]
        self.assertEqual(bad, [])

    # ── 7. the numbers the presentation rests on ───────────────────────
    def test_some_requests_are_routed(self):
        routed = [r for r in self.requests if r["routed_to"]]
        self.assertGreater(len(routed), 40, f"{len(routed)} routed")

    def test_offers_found_in_the_slack_threads(self):
        offers = [x for x in self.reach if x["reach_type"] == "offer"]
        self.assertEqual(len(offers), 15)

    def test_no_path_blocked_reason_says_who_was_tried(self):
        """'no path in the roster or investor network' only when supply_reach has
        nothing for the company; 'no path on the roster' only when what it has is
        all off-roster. Since routing follows the allocation, a request whose only
        paths are off-roster is normally routed to one of them, so the second label
        is checked on the function directly."""
        roster = bg.load_roster()
        reach = defaultdict(list)
        for x in self.reach:
            reach[x["company_id"]].append(x["connector"])
        by_reason = defaultdict(list)
        for r in self.requests:
            by_reason[r["blocked_reason"]].append(r)
        self.assertTrue(by_reason[bg.BLOCK_NO_PATH])
        self.assertEqual([r["request_id"] for r in by_reason[bg.BLOCK_NO_PATH] if reach[r["company_id"]]], [])
        self.assertEqual([r["request_id"] for r in by_reason[bg.BLOCK_NO_ROSTER_PATH]
                          if not reach[r["company_id"]] or any(n in roster for n in reach[r["company_id"]])], [])

        company = bg.Company("example.com")
        company.accounts.append({"account_id": "A0001", "account_name": "Example", "stage": "Open"})
        on, off = next(iter(roster)), "Someone Off Roster"
        self.assertNotIn(off, roster)
        self.assertEqual(bg.blocked_reason(company, [], roster, None), bg.BLOCK_NO_PATH)
        self.assertEqual(bg.blocked_reason(company, [{"connector": off}], roster, None), bg.BLOCK_NO_ROSTER_PATH)
        self.assertEqual(bg.blocked_reason(company, [{"connector": off}, {"connector": on}], roster, None),
                         bg.BLOCK_NEVER_ROUTED)

    def test_blocked_reason_reads_only_what_the_allocator_reads(self):
        """allocate() never looks at the CRM record or the account stage, so
        neither is a blocked_reason: a company with no CRM account and a roster
        path is 'path exists, never routed', a Closed Lost account nobody
        reaches is 'no path in the roster or investor network'. 24 requests used
        to stop at those two labels before the allocator's own reason was read."""
        roster = bg.load_roster()
        on = next(iter(roster))
        no_crm = bg.Company("example.com")
        self.assertEqual(no_crm.accounts, [])
        self.assertEqual(bg.blocked_reason(no_crm, [{"connector": on}], roster, None), bg.BLOCK_NEVER_ROUTED)
        closed_lost = bg.Company("lost.example")
        closed_lost.accounts.append({"account_id": "A0002", "account_name": "Lost", "stage": "Closed Lost"})
        self.assertEqual(bg.blocked_reason(closed_lost, [], roster, None), bg.BLOCK_NO_PATH)

        labels = Counter(r["blocked_reason"] for r in self.requests)
        self.assertNotIn("company has no CRM record", labels)
        self.assertNotIn("account is Closed Lost", labels)
        # the allocator's capacity verdict carries through on the rows nobody asked;
        # an asked row keeps its filed routing and so has no blocked_reason at all
        by_rid = {r["request_id"]: r for r in self.requests}
        capped = [by_rid[a["request_id"]] for a in bg.latest_cycle(self.allocation)
                  if a["exception_reason"] == bg.CAPACITY_EXHAUSTED]
        self.assertEqual(len(capped), 13)
        carried = [r for r in capped if r["blocked_reason"] == bg.CAPACITY_EXHAUSTED]
        blank = [r for r in capped if not r["blocked_reason"]]
        self.assertEqual((len(carried), len(blank)), (10, 3))
        self.assertEqual(sum(r["status_as_filed"] == "Closed - no path" for r in carried), 3,
                         "three reopened Closed - no path requests found every connector spent")
        self.assertEqual(len(carried) + len(blank), len(capped), "nothing else on a capacity-exhausted row")
        self.assertTrue(all(not r["asked_date"] for r in carried))
        self.assertTrue(all(r["asked_date"] for r in blank), "blank only because the ask went out")

    # ── 9. the status gate: what the allocator takes back ─────────────────
    def test_in_queue_reopens_only_what_the_ask_log_never_saw(self):
        """Filed open: in while never asked, or asked and its own intro fizzled.
        Filed Closed - no path or Intro sent: in only while the ask log has no row
        for it at all; once asked, the outcome row is the record and the retry
        rule does not apply. Every other status stays out."""
        for status in bg.OPEN_STATUSES:
            self.assertTrue(bg.in_queue(status, "R1", set(), set()), status)
            self.assertFalse(bg.in_queue(status, "R1", {"R1"}, set()), status)
            self.assertTrue(bg.in_queue(status, "R1", {"R1"}, {"R1"}), status)
        for status in bg.REOPEN_STATUSES:
            self.assertTrue(bg.in_queue(status, "R1", set(), set()), status)
            self.assertFalse(bg.in_queue(status, "R1", {"R1"}, set()), status)
            self.assertFalse(bg.in_queue(status, "R1", {"R1"}, {"R1"}), status)
        self.assertEqual(bg.REOPEN_STATUSES, {"Closed - no path", "Intro sent"})
        self.assertFalse(bg.in_queue("Meeting booked", "R1", set(), set()))
        self.assertFalse(bg.in_queue("", "R1", set(), set()))

    def test_repair_window_starts_the_day_the_file_first_flagged_the_claim(self):
        today = bg.parse_date("2026-09-07")
        self.assertEqual(bg.repair_until("R1", {}, today), (today, bg.parse_date("2026-10-07")))
        first = bg.parse_date("2026-08-20")
        self.assertEqual(bg.repair_until("R1", {"R1": first}, today), (first, bg.parse_date("2026-09-19")))
        self.assertEqual(bg.repair_until("R1", {"R1": bg.parse_date("2026-09-09")}, today), (today, bg.parse_date("2026-10-07")),
                         "a flag dated after this build's clock counts from the clock")
        self.assertEqual(bg.REPAIR_DAYS, 30)
        # the flag date is read back from the file: the earliest INTRO_CLAIMED_NOT_LOGGED row per request
        history = [{"cycle": "2026-08", "request_id": "R1", "decided_at": "2026-08-20T10:00:00Z", "allocated_to": "",
                    "exception_reason": f"{bg.INTRO_CLAIMED_NOT_LOGGED}: filed Intro sent, no intro in the log, flagged 2026-08-20, routed as Stalled from 2026-09-19"},
                   {"cycle": "2026-09", "request_id": "R1", "decided_at": "2026-09-06T10:00:00Z", "allocated_to": "",
                    "exception_reason": f"{bg.INTRO_CLAIMED_NOT_LOGGED}: filed Intro sent, no intro in the log, flagged 2026-08-20, routed as Stalled from 2026-09-19"},
                   {"cycle": "2026-09", "request_id": "R2", "decided_at": "2026-09-06T10:00:00Z", "allocated_to": "",
                    "exception_reason": bg.NO_PATH}]
        self.assertEqual(bg.history_signals(history, [], today).claimed, {"R1": first})

    def test_reopened_names_why_a_finished_request_is_in_the_allocator(self):
        row = {"status_as_filed": "Closed - no path", "exception_reason": ""}
        self.assertEqual(bg.reopened(row), "filed Closed - no path, never asked")
        self.assertEqual(bg.reopened({**row, "exception_reason": bg.NO_PATH}), "filed Closed - no path, never asked")
        self.assertEqual(bg.reopened({"status_as_filed": "Intro sent", "exception_reason": ""}),
                         f"filed Intro sent, no intro logged in {bg.REPAIR_DAYS} days")
        self.assertEqual(bg.reopened({"status_as_filed": "Intro sent", "exception_reason": f"{bg.INTRO_CLAIMED_NOT_LOGGED}: ..."}), "",
                         "in the repair queue: not reopened, held")
        self.assertEqual(bg.reopened({"status_as_filed": "Intro sent", "exception_reason": f"{bg.ALREADY_INTRODUCED}: X on 2026-08-10 (R1)"}), "",
                         "parked on the company's live intro, which may be the one claimed")
        self.assertEqual(bg.reopened({"status_as_filed": "Intro sent", "exception_reason": "company unresolved"}), "filed Intro sent, never asked")
        self.assertEqual(bg.reopened({"status_as_filed": "Stalled", "exception_reason": ""}), "")

    def test_a_reopened_request_keeps_its_filed_status_and_reads_as_routed(self):
        """status_as_filed is a source fact: the allocation row and the request
        row keep it. What changes is what the pipeline does with it: routed once
        allocated (stage_of), route_reason saying it was reopened, blocked_reason
        naming the repair queue while the claim waits there."""
        by_rid = {r["request_id"]: r for r in self.requests}
        current = bg.latest_cycle(self.allocation)
        reopened = [a for a in current if a["status_as_filed"] in bg.REOPEN_STATUSES]
        self.assertTrue(reopened)
        for a in reopened:
            r = by_rid[a["request_id"]]
            self.assertEqual(r["status_as_filed"], a["status_as_filed"])
            self.assertEqual(r["asked_date"], "")
            if a["allocated_to"]:
                self.assertEqual(bg.stage_of(r, None, a), "routed")
                self.assertEqual(r["routed_to"], a["allocated_to"])
                self.assertTrue(r["route_reason"].startswith(f"reopened ({bg.reopened(a)}); allocated to"), r["route_reason"])
                self.assertEqual(r["blocked_reason"], "")
            elif a["exception_reason"].startswith(bg.INTRO_CLAIMED_NOT_LOGGED):
                self.assertEqual(bg.stage_of(r, None, a), "introduced", "the claim stands until repaired or timed out")
                self.assertEqual(r["blocked_reason"], bg.INTRO_CLAIMED_NOT_LOGGED)
                self.assertEqual(r["contradicts_log"], bg.INTRO_CLAIMED_NOT_LOGGED)
                self.assertNotIn("reopened", r["route_reason"])
            elif not bg.reopened(a):
                self.assertEqual(a["status_as_filed"], "Intro sent")
                self.assertTrue(a["exception_reason"].startswith(bg.ALREADY_INTRODUCED))
                self.assertNotIn("reopened", r["route_reason"])
            else:
                self.assertTrue(r["route_reason"].startswith(f"reopened ({bg.reopened(a)}); not asked; "), r["route_reason"])
        self.assertTrue(any(a["allocated_to"] for a in reopened if a["status_as_filed"] == "Closed - no path"))
        self.assertTrue(any(a["exception_reason"].startswith(bg.INTRO_CLAIMED_NOT_LOGGED) for a in reopened))


if __name__ == "__main__":
    unittest.main()
