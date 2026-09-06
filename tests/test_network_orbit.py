"""Tests for golden/network_orbit.csv and the trace section it feeds.

    python3 -m unittest tests.test_network_orbit

The orbit is context, not supply: every row in investor_network.csv whose
company resolves, whether or not the person is on the roster. It must never
leak into supply_reach.csv, the allocator, or a connector's capacity.
"""
from __future__ import annotations

import csv
import hashlib
import sys
import unittest
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from analysis.trace import NO_WARM_PATH, Data, Trace, find_company  # noqa: E402
from golden import build_golden as bg  # noqa: E402
from tests.test_rebuild import CYCLE_1, ScratchRootTest  # noqa: E402

G = ROOT / "golden"
D = ROOT / "dataset"
AS_OF = date(2026, 9, 5)


def rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def split_bar(s: str) -> list[str]:
    return [p.strip() for p in (s or "").split("|") if p.strip()]


class NetworkOrbitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orbit = rows(G / "network_orbit.csv")
        cls.companies = {c["company_id"]: c for c in rows(G / "golden_companies.csv")}
        cls.reach = rows(G / "supply_reach.csv")
        cls.allocation = rows(G / "golden_allocation.csv")
        cls.network = rows(D / "investor_network.csv")
        cls.roster = bg.load_roster()
        cls.connections = {name.split()[-1]: {c["name"] for c in rows(D / r["connections_file"])}
                           for name, r in cls.roster.items()}
        cls.spelling_to_id = {}
        for cid, c in cls.companies.items():
            for spelling in (c["company_name"], *split_bar(c["also_known_as"])):
                cls.spelling_to_id[spelling] = cid

    # ── shape ──────────────────────────────────────────────────────────
    def test_columns(self):
        with open(G / "network_orbit.csv", newline="", encoding="utf-8") as fh:
            self.assertEqual(next(csv.reader(fh)), bg.NETWORK_COLUMNS)

    def test_73_rows_across_30_companies(self):
        self.assertEqual(len(self.orbit), 73)
        self.assertEqual(len({r["company_id"] for r in self.orbit}), 30)

    def test_one_row_per_person_company_pair_per_source(self):
        keys = Counter((r["person"], r["company_id"], r["source"]) for r in self.orbit)
        self.assertEqual([k for k, n in keys.items() if n > 1], [])
        self.assertTrue(all(r["source"] in bg.NETWORK_SOURCES for r in self.orbit))

    def test_every_network_row_naming_a_company_is_in_the_orbit(self):
        want = sum(1 for inv in self.network for s in bg.NETWORK_SOURCES if inv[s])
        self.assertEqual(len(self.orbit), want, "every portfolio_company / prior_employer value resolves")

    # ── resolution ─────────────────────────────────────────────────────
    def test_every_company_exists_and_the_name_matches(self):
        for r in self.orbit:
            with self.subTest(person=r["person"], company=r["company_name"]):
                self.assertIn(r["company_id"], self.companies)
                self.assertEqual(r["company_name"], self.companies[r["company_id"]]["company_name"])

    def test_every_source_spelling_is_the_company_name_or_an_alias(self):
        """The orbit is exactly investor_network.csv re-keyed by company_id:
        every spelling there is a golden company name or alias, and the row
        lands on that company."""
        want = Counter()
        for inv in self.network:
            for s in bg.NETWORK_SOURCES:
                if inv[s]:
                    with self.subTest(spelling=inv[s]):
                        self.assertIn(inv[s], self.spelling_to_id)
                    want[(inv["person"], self.spelling_to_id[inv[s]], s)] += 1
        self.assertEqual(Counter((r["person"], r["company_id"], r["source"]) for r in self.orbit), want)

    def test_duncastle_hotels_resolves_to_c010(self):
        self.assertEqual(self.spelling_to_id["Duncastle Hotels"], "C010")
        self.assertEqual(self.companies["C010"]["company_name"], "Duncastle Holdings")
        people = {inv["person"] for inv in self.network if "Duncastle Hotels" in (inv[s] for s in bg.NETWORK_SOURCES)}
        self.assertTrue(people)
        hotels = [r for r in self.orbit if r["person"] in people and r["company_name"] == "Duncastle Holdings"]
        self.assertEqual({r["person"] for r in hotels}, people)
        self.assertEqual({r["company_id"] for r in hotels}, {"C010"})
        self.assertNotIn("Duncastle Hotels", {r["company_name"] for r in self.orbit})

    def test_companies_with_no_path_still_get_rows(self):
        for cid, name in (("C042", "Volney Industrial Systems"), ("C014", "Kestrel Airlines")):
            with self.subTest(company=cid):
                self.assertEqual(self.companies[cid]["company_name"], name)
                self.assertEqual(self.companies[cid]["paths_available"], "0")
                self.assertTrue([r for r in self.orbit if r["company_id"] == cid])

    # ── reachable_via ──────────────────────────────────────────────────
    def test_roster_people_are_reachable_as_connector(self):
        priya = [r for r in self.orbit if r["person"] == "Priya Raghunathan"]
        self.assertEqual(len(priya), 8)
        self.assertEqual({r["reachable_via"] for r in priya}, {bg.REACHABLE_AS_CONNECTOR})
        for r in self.orbit:
            with self.subTest(person=r["person"]):
                self.assertEqual(r["reachable_via"] == bg.REACHABLE_AS_CONNECTOR, r["person"] in self.roster)

    def test_off_roster_people_carry_the_surnames_whose_export_lists_them(self):
        for r in self.orbit:
            if r["person"] in self.roster:
                continue
            want = sorted(s for s, names in self.connections.items() if r["person"] in names)
            with self.subTest(person=r["person"]):
                self.assertEqual(split_bar(r["reachable_via"]), want)

    def test_cold_rows_exist_and_mean_no_warm_route(self):
        cold = [r for r in self.orbit if not r["reachable_via"]]
        self.assertTrue(cold)
        for r in cold:
            with self.subTest(person=r["person"]):
                self.assertNotIn(r["person"], self.roster)
                self.assertFalse(any(r["person"] in names for names in self.connections.values()))

    # ── never supply ───────────────────────────────────────────────────
    def test_orbit_people_off_the_roster_are_never_connectors(self):
        askable = {p["connector"] for p in self.reach} | {a["allocated_to"] for a in self.allocation}
        for r in self.orbit:
            if r["person"] not in self.roster:
                with self.subTest(person=r["person"]):
                    self.assertNotIn(r["person"], askable)

    def test_investor_supply_is_still_roster_only(self):
        """The orbit adds nothing to supply_reach.csv: investor rows there are
        exactly the roster people's portfolio companies, as before."""
        investor = [p for p in self.reach if p["reach_type"] == "investor"]
        roster_portfolio = [r for r in self.orbit if r["source"] == "portfolio_company" and r["person"] in self.roster]
        self.assertEqual(Counter((p["connector"], p["company_id"]) for p in investor),
                         Counter((r["person"], r["company_id"]) for r in roster_portfolio))


class OrbitIsIndependentOfTheDerivedFiles(ScratchRootTest):
    def test_the_other_golden_files_do_not_depend_on_the_orbit(self):
        self.build(CYCLE_1)
        derived = ["golden_companies.csv", "supply_reach.csv", "golden_allocation.csv", "golden_requests.csv"]
        before = {n: hashlib.sha256((self.root / "golden" / n).read_bytes()).hexdigest() for n in derived}
        orbit = self.root / "golden" / "network_orbit.csv"
        orbit_bytes = orbit.read_bytes()
        orbit.unlink()
        out = self.build(CYCLE_1)
        self.assertIn("network_orbit.csv     73 rows (rebuilt) across 30 companies", out)
        self.assertEqual(orbit.read_bytes(), orbit_bytes)
        self.assertEqual({n: hashlib.sha256((self.root / "golden" / n).read_bytes()).hexdigest() for n in derived}, before)


class OrbitTraceSectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = Data.load()

    def trace(self, q: str) -> Trace:
        return Trace(self.data, find_company(self.data, q), AS_OF)

    def test_sorted_board_seats_then_warm_then_cold(self):
        for t in (self.trace("C010"), self.trace("C042")):
            with self.subTest(company=t.cid):
                bands = [0 if r["board_seat"] == "yes" else 1 if r["reachable_via"] else 2 for r in t.orbit]
                self.assertEqual(bands, sorted(bands))
                self.assertEqual([r["person"] for r in t.orbit],
                                 [r["person"] for r in self.data.orbit if r["company_id"] == t.cid and r["board_seat"] == "yes"]
                                 + [r["person"] for r in self.data.orbit if r["company_id"] == t.cid and r["board_seat"] != "yes" and r["reachable_via"]]
                                 + [r["person"] for r in self.data.orbit if r["company_id"] == t.cid and r["board_seat"] != "yes" and not r["reachable_via"]])

    def test_cold_rows_are_labelled(self):
        t = self.trace("C042")
        self.assertFalse(t.paths, "C042 has no supply path")
        text = t.render()
        self.assertIn("## 6. Additional Investor and Operator Network", text)
        self.assertIn("nobody in the network reaches this company", text)
        d = t.as_dict()
        self.assertEqual(len(d["orbit"]), 4)
        self.assertEqual({r["route"] for r in d["orbit"] if not r["reachable_via"]}, {NO_WARM_PATH})
        self.assertEqual(text.count(f"| {NO_WARM_PATH} |"), sum(1 for r in t.orbit if not r["reachable_via"]))

    def test_connector_rows_say_so(self):
        d = self.trace("C010").as_dict()
        priya = next(r for r in d["orbit"] if r["person"] == "Priya Raghunathan")
        self.assertEqual((priya["reachable_via"], priya["route"], priya["board_seat"]), ("connector", "on the roster", True))
        self.assertEqual(d["orbit"][0]["board_seat"], True)

    def test_section_absent_when_nobody_orbits(self):
        empty = next(c for c in self.data.companies
                     if int(c["total_requests"] or 0) and not any(r["company_id"] == c["company_id"] for r in self.data.orbit))
        t = Trace(self.data, empty, AS_OF)
        self.assertEqual(t.orbit, [])
        self.assertNotIn("## 6.", t.render())
        self.assertEqual(t.as_dict()["orbit"], [])

    def test_the_orbit_changes_nothing_the_allocator_reads(self):
        """Sections 3-5 and the routing strip are computed without the orbit."""
        t = self.trace("C042")
        with_orbit = t.as_dict()
        bare = Trace(Data(**{**vars(self.data), "orbit": []}), t.c, AS_OF).as_dict()
        for key in ("header", "disagreements", "reach", "chronology", "next_steps"):
            with self.subTest(section=key):
                self.assertEqual(with_orbit[key], bare[key])


if __name__ == "__main__":
    unittest.main()
