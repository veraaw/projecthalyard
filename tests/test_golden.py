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


if __name__ == "__main__":
    unittest.main()
