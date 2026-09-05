"""Tests for golden/golden_allocation.csv, the file the routing argument rests on.

    python3 -m unittest tests.test_allocation

One row per live, not-yet-asked request; each row is either an allocation
(allocated_to + batch_id) or an exception (exception_reason), never both and
never neither. Counts are derived from golden_requests.csv, golden_companies.csv
and dataset/, never fixed: the request file grows on every merge.
"""
from __future__ import annotations

import csv
import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from golden.build_golden import CAPACITY_EXHAUSTED, OFF_ROSTER_CAPACITY, OPEN_STATUSES  # noqa: E402

G = ROOT / "golden"
D = ROOT / "dataset"

NO_PATH = "no path to this company in the network"
UNRESOLVED = "company unresolved"
KNOWN_EXCEPTIONS = {NO_PATH, CAPACITY_EXHAUSTED, UNRESOLVED}
BATCH_COLUMNS = ("batch_id", "batch_size", "path_type", "route_score")


def rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


class AllocationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.alloc = rows(G / "golden_allocation.csv")
        cls.requests = {r["request_id"]: r for r in rows(G / "golden_requests.csv")}
        cls.companies = {c["company_id"]: c for c in rows(G / "golden_companies.csv")}
        cls.roster = {r["name"]: r for r in rows(D / "connector_roster.csv")}
        cls.outcomes = rows(D / "intro_outcomes.csv")
        cls.asked = {o["request_id"] for o in cls.outcomes}
        cls.allocated = [a for a in cls.alloc if a["allocated_to"]]
        cls.exceptions = [a for a in cls.alloc if a["exception_reason"]]
        cls.cycle = cls.alloc[0]["cycle"] if cls.alloc else ""
        # what the allocator should have covered
        cls.live = {rid for rid, r in cls.requests.items()
                    if r["status_as_filed"] in OPEN_STATUSES and rid not in cls.asked and not r["asked_date"]}

    # ── 1. structure ───────────────────────────────────────────────────
    def test_every_row_has_the_headers_field_count(self):
        with open(G / "golden_allocation.csv", newline="", encoding="utf-8") as fh:
            r = csv.reader(fh)
            header = next(r)
            ragged = [i for i, row in enumerate(r, 2) if len(row) != len(header)]
        self.assertEqual(ragged, [], f"ragged rows at lines {ragged[:5]}")
        self.assertTrue(all(None not in a for a in self.alloc), "row longer than header")

    def test_one_row_per_request_id(self):
        dupes = [k for k, n in Counter(a["request_id"] for a in self.alloc).items() if n > 1]
        self.assertEqual(dupes, [])

    def test_one_cycle_per_file(self):
        self.assertEqual({a["cycle"] for a in self.alloc}, {self.cycle})

    # ── 2. allocation xor exception ────────────────────────────────────
    def test_exactly_one_of_allocated_to_or_exception_reason(self):
        both = [a["request_id"] for a in self.alloc if a["allocated_to"] and a["exception_reason"]]
        neither = [a["request_id"] for a in self.alloc if not a["allocated_to"] and not a["exception_reason"]]
        self.assertEqual(both, [], "allocated and an exception")
        self.assertEqual(neither, [], "neither allocated nor an exception")
        self.assertEqual(len(self.allocated) + len(self.exceptions), len(self.alloc))

    def test_allocated_rows_carry_their_batch_and_exceptions_do_not(self):
        half = [a["request_id"] for a in self.allocated if not all(a[c] for c in BATCH_COLUMNS)]
        self.assertEqual(half, [], "allocated without batch_id/batch_size/path_type/route_score")
        leaked = [a["request_id"] for a in self.exceptions
                  if any(a[c] for c in BATCH_COLUMNS + ("contact_name",))]
        self.assertEqual(leaked, [], "exception carrying batch or path columns")

    # ── 3. referential integrity ───────────────────────────────────────
    def test_every_request_id_exists_in_golden_requests(self):
        missing = [a["request_id"] for a in self.alloc if a["request_id"] not in self.requests]
        self.assertEqual(missing, [])

    def test_every_request_is_live_and_not_yet_asked(self):
        not_live = [a["request_id"] for a in self.alloc
                    if self.requests[a["request_id"]]["status_as_filed"] not in OPEN_STATUSES]
        self.assertEqual(not_live, [], f"not in {sorted(OPEN_STATUSES)}")
        already = [a["request_id"] for a in self.alloc
                   if a["request_id"] in self.asked or self.requests[a["request_id"]]["asked_date"]]
        self.assertEqual(already, [], "already asked")

    def test_every_live_request_has_exactly_one_row(self):
        # The other direction: nothing live is skipped. Together with one row
        # per request_id this is what makes two reps wanting the same title
        # both show up rather than collapsing into one ask.
        self.assertEqual({a["request_id"] for a in self.alloc}, self.live)

    def test_every_company_id_exists_in_golden_companies(self):
        orphans = [a["request_id"] for a in self.alloc
                   if a["company_id"] and a["company_id"] not in self.companies]
        self.assertEqual(orphans, [])

    # ── 4. capacity ────────────────────────────────────────────────────
    def test_no_connector_exceeds_capacity_for_the_cycle(self):
        # Same budget the allocator uses: stated_monthly_capacity minus asks
        # already dated in the cycle; OFF_ROSTER_CAPACITY for anyone else.
        budget: dict[str, int] = defaultdict(lambda: OFF_ROSTER_CAPACITY)
        budget.update({n: int(r["stated_monthly_capacity"]) for n, r in self.roster.items()})
        for o in self.outcomes:
            if o["asked_date"].startswith(self.cycle):
                budget[o["connector_asked"]] -= 1
        load = Counter(a["allocated_to"] for a in self.allocated)
        over = {n: (k, budget[n]) for n, k in load.items() if k > budget[n]}
        self.assertEqual(over, {}, "allocated > budget")
        self.assertTrue(set(load) & set(self.roster), "no roster connector allocated to")

    # ── 5. batches ─────────────────────────────────────────────────────
    def test_batch_size_equals_the_rows_in_that_batch(self):
        sizes = Counter(a["batch_id"] for a in self.allocated)
        wrong = [(a["request_id"], a["batch_size"], sizes[a["batch_id"]]) for a in self.allocated
                 if a["batch_size"] != str(sizes[a["batch_id"]])]
        self.assertEqual(wrong, [])

    def test_one_batch_per_connector_per_cycle(self):
        per_connector = defaultdict(set)
        for a in self.allocated:
            per_connector[(a["cycle"], a["allocated_to"])].add(a["batch_id"])
        split = {k: sorted(v) for k, v in per_connector.items() if len(v) != 1}
        self.assertEqual(split, {})
        misnamed = [a["batch_id"] for a in self.allocated
                    if a["batch_id"] != f"{a['cycle']} {a['allocated_to']}"]
        self.assertEqual(misnamed, [], "batch_id is not '<cycle> <connector>'")

    # ── 6. target_title survives into the batch ────────────────────────
    def test_target_title_matches_golden_requests(self):
        blank = [a["request_id"] for a in self.allocated if not a["target_title"]]
        self.assertEqual(blank, [], "allocated with no target_title")
        drifted = [(a["request_id"], a["target_title"], self.requests[a["request_id"]]["target_title"])
                   for a in self.alloc if a["target_title"] != self.requests[a["request_id"]]["target_title"]]
        self.assertEqual(drifted, [])

    def test_two_reps_wanting_the_same_title_are_both_present(self):
        # Two reps asking for the same title at the same company are two asks,
        # not one: the file must list both request_ids rather than collapsing
        # them, and a batch may therefore repeat a (company, title).
        wanted = defaultdict(set)
        for rid in self.live:
            r = self.requests[rid]
            wanted[(r["company_id"], r["target_title"])].add(rid)
        contested = {k: v for k, v in wanted.items() if len(v) > 1}
        self.assertTrue(contested, "no two live requests share a (company, title)")
        present = defaultdict(set)
        for a in self.alloc:
            present[(a["company_id"], a["target_title"])].add(a["request_id"])
        collapsed = {k: sorted(v - present[k]) for k, v in contested.items() if v - present[k]}
        self.assertEqual(collapsed, {}, "request_ids dropped for a contested title")
        repeated = Counter((a["batch_id"], a["company_id"], a["target_title"]) for a in self.allocated)
        self.assertTrue(any(n > 1 for n in repeated.values()),
                        "no batch lists the same title twice")

    # ── 7. exception reasons ───────────────────────────────────────────
    def test_exception_reason_is_one_of_the_known_set(self):
        reasons = Counter(a["exception_reason"] for a in self.exceptions)
        self.assertEqual(set(reasons) - KNOWN_EXCEPTIONS, set())
        self.assertEqual(set(reasons), KNOWN_EXCEPTIONS, "every known reason occurs")

    def test_each_exception_reason_is_explained_by_the_other_files(self):
        # unresolved: no company. no path: the company has no path in
        # golden_companies.csv. capacity exhausted: a path exists and is named.
        for a in self.exceptions:
            with self.subTest(request_id=a["request_id"], reason=a["exception_reason"]):
                if a["exception_reason"] == UNRESOLVED:
                    self.assertEqual(a["company_id"], "")
                    self.assertEqual(a["best_path_if_unbudgeted"], "")
                elif a["exception_reason"] == NO_PATH:
                    self.assertEqual(self.companies[a["company_id"]]["paths_available"], "0")
                    self.assertEqual(a["best_path_if_unbudgeted"], "")
                else:
                    self.assertNotEqual(self.companies[a["company_id"]]["paths_available"], "0")
                    self.assertTrue(a["best_path_if_unbudgeted"])
        no_company = [a["request_id"] for a in self.alloc
                      if not a["company_id"] and a["exception_reason"] != UNRESOLVED]
        self.assertEqual(no_company, [], "no company_id yet not flagged as unresolved")


if __name__ == "__main__":
    unittest.main()
