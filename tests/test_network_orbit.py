"""Tests for golden/network_orbit.csv and the trace section it feeds.

    python3 -m unittest tests.test_network_orbit

The orbit is a view, not supply: every row in investor_network.csv whose
company resolves, whether or not the person is on the roster. The file itself
feeds nothing. What it points at does: an off-roster person's own portfolio
company is an investor_network path in supply_reach.csv (connector_type
"investor network", OFF_ROSTER_CAPACITY, prior delivery rate, NETWORK_HAIRCUT
on route score), allocated roster-first: asked only for requests where the
roster has no path or every roster path is out of capacity this cycle.
"""
from __future__ import annotations

import csv
import hashlib
import sys
import unittest
from collections import Counter, defaultdict
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

    def test_companies_nobody_on_the_roster_reaches_are_reached_through_the_network(self):
        """C042 and C014 have no roster path at all: every path they have is an
        investor_network one, and the orbit is where those people show up."""
        for cid, name in (("C042", "Volney Industrial Systems"), ("C014", "Kestrel Airlines")):
            with self.subTest(company=cid):
                self.assertEqual(self.companies[cid]["company_name"], name)
                paths = [p for p in self.reach if p["company_id"] == cid]
                self.assertTrue(paths)
                self.assertEqual({p["reach_type"] for p in paths}, {bg.INVESTOR_NETWORK})
                self.assertEqual(self.companies[cid]["paths_available"], str(len(paths)))
                self.assertEqual(self.companies[cid]["durable_paths"], str(len(paths)))
                self.assertEqual(self.companies[cid]["best_path_type"], bg.INVESTOR_NETWORK)
                orbit = [r for r in self.orbit if r["company_id"] == cid]
                self.assertEqual({r["person"] for r in orbit}, {p["connector"] for p in paths})
                self.assertEqual({r["reachable_via"] for r in orbit}, {bg.INVESTOR_NETWORK})

    # ── reachable_via ──────────────────────────────────────────────────
    def test_roster_people_are_reachable_as_connector(self):
        priya = [r for r in self.orbit if r["person"] == "Priya Raghunathan"]
        self.assertEqual(len(priya), 8)
        self.assertEqual({r["reachable_via"] for r in priya}, {bg.REACHABLE_AS_CONNECTOR})
        for r in self.orbit:
            with self.subTest(person=r["person"]):
                self.assertEqual(r["reachable_via"] == bg.REACHABLE_AS_CONNECTOR, r["person"] in self.roster)

    def test_off_roster_people_carry_the_surnames_whose_export_lists_them(self):
        """A connector's export is the warmer route and wins; only a person no
        export lists falls through to their own investor_network path, and only
        on their portfolio-company row."""
        for r in self.orbit:
            if r["person"] in self.roster:
                continue
            surnames = sorted(s for s, names in self.connections.items() if r["person"] in names)
            with self.subTest(person=r["person"], company=r["company_id"], source=r["source"]):
                if surnames:
                    self.assertEqual(split_bar(r["reachable_via"]), surnames)
                elif r["source"] == "portfolio_company":
                    self.assertEqual(r["reachable_via"], bg.INVESTOR_NETWORK)
                else:
                    self.assertEqual(r["reachable_via"], "")

    def test_empty_means_no_warm_route_and_no_path(self):
        """An empty reachable_via is a person nobody knows and no path reaches:
        not on the roster, in no export, and not a connector in supply_reach.csv
        for that company. (Every such row in the fixture is a portfolio company,
        so today there are none; the rule is what is tested.)"""
        connectors_for = {(p["connector"], p["company_id"]) for p in self.reach}
        for r in self.orbit:
            if r["reachable_via"]:
                continue
            with self.subTest(person=r["person"]):
                self.assertNotIn(r["person"], self.roster)
                self.assertFalse(any(r["person"] in names for names in self.connections.values()))
                self.assertNotIn((r["person"], r["company_id"]), connectors_for)

    # ── the paths the orbit points at ──────────────────────────────────
    def network_paths(self) -> list[dict]:
        return [p for p in self.reach if p["reach_type"] == bg.INVESTOR_NETWORK]

    def test_investor_network_paths_are_exactly_the_off_roster_portfolio_rows(self):
        """One investor_network path per (off-roster person, portfolio company),
        whether or not a connector's export also lists the person; never for a
        prior_employer row (that is the alumni path, through the connector)."""
        want = Counter((r["person"], r["company_id"]) for r in self.orbit
                       if r["source"] == "portfolio_company" and r["person"] not in self.roster)
        self.assertTrue(want)
        self.assertEqual(Counter((p["connector"], p["company_id"]) for p in self.network_paths()), want)
        off_roster = {r["person"] for r in self.orbit if r["person"] not in self.roster}
        for p in self.reach:
            if p["connector"] in off_roster and p["reach_type"] not in (bg.INVESTOR_NETWORK, "offer"):
                self.fail(f"{p['connector']} is a {p['reach_type']} connector at {p['company_id']}")

    def test_investor_supply_is_still_roster_only(self):
        """Roster investors keep reach_type = investor; the two are distinguishable."""
        investor = [p for p in self.reach if p["reach_type"] == "investor"]
        roster_portfolio = [r for r in self.orbit if r["source"] == "portfolio_company" and r["person"] in self.roster]
        self.assertEqual(Counter((p["connector"], p["company_id"]) for p in investor),
                         Counter((r["person"], r["company_id"]) for r in roster_portfolio))
        self.assertTrue(all(p["connector"] in self.roster for p in investor))

    def test_investor_network_path_fields(self):
        """Our circle, not our roster: OFF_ROSTER_CAPACITY, the prior delivery
        rate (never asked), focus unknown, connector_type 'investor network';
        strength reads like a roster investor's (board seat or not)."""
        seats = {(inv["person"].strip(), self.spelling_to_id[inv["portfolio_company"]]): inv["board_seat"].lower() == "true"
                 for inv in self.network if inv["portfolio_company"]}
        for p in self.network_paths():
            with self.subTest(connector=p["connector"], company=p["company_id"]):
                self.assertEqual(p["connector_type"], bg.NETWORK_TYPE)
                self.assertEqual(p["monthly_capacity"], str(bg.OFF_ROSTER_CAPACITY))
                self.assertEqual(p["delivery_rate"], f"{bg.PRIOR_RATE:.3f}")
                self.assertEqual(p["in_focus_area"], "unknown")
                self.assertEqual((p["contact_name"], p["observed_date"]), ("CEO / exec team", ""))
                seat = seats[(p["connector"], p["company_id"])]
                self.assertEqual(p["board_seat"], "yes" if seat else "no")
                self.assertEqual(p["strength"], f"{bg.BOARD_SEAT_STRENGTH if seat else bg.PATH_BASE['investor']:.3f}")
                self.assertIn("investor_network.csv:", p["evidence"])
        self.assertIn(bg.INVESTOR_NETWORK, bg.DURABLE_REACH)

    def test_haircut_is_on_the_route_score_not_the_strength(self):
        rates = {}
        for p in self.network_paths():
            with self.subTest(connector=p["connector"], company=p["company_id"]):
                industry = self.companies[p["company_id"]]["industry"]
                score = bg.path_score(p, self.roster, rates, industry)
                bare = float(p["strength"]) * 0.7 * bg.PRIOR_RATE
                self.assertAlmostEqual(score, bare * bg.NETWORK_HAIRCUT)
                self.assertAlmostEqual(bg.path_score({**p, "reach_type": "investor"}, self.roster, rates, industry), bare)
        self.assertEqual(bg.NETWORK_HAIRCUT, 0.90)

    def test_roster_paths_rank_before_the_network_whatever_the_score(self):
        rates = {}
        for p in self.network_paths():
            industry = self.companies[p["company_id"]]["industry"]
            for reach in ("direct", "alumni", "investor", "offer"):
                weak = {**p, "reach_type": reach, "strength": "0.05"}
                with self.subTest(connector=p["connector"], company=p["company_id"], reach=reach):
                    self.assertLess(bg.path_score(weak, self.roster, rates, industry),
                                    bg.path_score(p, self.roster, rates, industry))
                    self.assertLess(bg.path_rank(weak, self.roster, rates, industry),
                                    bg.path_rank(p, self.roster, rates, industry))
            self.assertEqual(bg.path_rank(p, self.roster, rates, industry),
                             (1, -bg.path_score(p, self.roster, rates, industry)))

    def test_the_network_fills_only_when_the_roster_cannot(self):
        """Roster-first: every request allocated to the network had no roster path or
        every roster connector with one was out of capacity by then; every request
        with a roster connector still in budget went to the roster (so C042 and
        C014, roster-unreachable, route now); nobody in the network is allocated past
        OFF_ROSTER_CAPACITY; an allocation's route_score is the haircut score;
        Nadia Okonkwo's Slack offer (the off-roster precedent) is untouched."""
        cycle = bg.latest_cycle(self.allocation)
        network = [a for a in cycle if a["path_type"] == bg.INVESTOR_NETWORK]
        self.assertTrue(network)
        self.assertTrue({a["company_id"] for a in network} >= {"C042", "C014"})
        for a in cycle:
            if a["company_id"] in ("C042", "C014"):
                self.assertEqual(a["path_type"], bg.INVESTOR_NETWORK, a["request_id"])
        roster_paths = defaultdict(set)
        for p in self.reach:
            if p["reach_type"] != bg.INVESTOR_NETWORK:
                roster_paths[p["company_id"]].add(p["connector"])
        used = Counter(a["allocated_to"] for a in cycle if a["allocated_to"])
        by_path = {(p["connector"], p["company_id"]): p for p in self.network_paths()}
        for a in network:
            with self.subTest(request=a["request_id"]):
                p = by_path[(a["allocated_to"], a["company_id"])]
                self.assertNotIn(a["allocated_to"], self.roster)
                self.assertEqual(float(a["route_score"]),
                                 round(bg.path_score(p, self.roster, {}, self.companies[a["company_id"]]["industry"]), 3))
                for n in roster_paths[a["company_id"]]:
                    self.assertGreaterEqual(used[n], bg.capacity(self.roster, n),
                                            f"{n} still had capacity for {a['company_id']}")
        for a in cycle:
            if a["allocated_to"] and a["path_type"] != bg.INVESTOR_NETWORK:
                self.assertIn(a["allocated_to"], roster_paths[a["company_id"]], a["request_id"])
        load = Counter(a["allocated_to"] for a in network)
        self.assertLessEqual(max(load.values()), bg.OFF_ROSTER_CAPACITY)
        nadia = next(a for a in cycle if a["request_id"] == "R1034")
        self.assertEqual((nadia["allocated_to"], nadia["path_type"]), ("Nadia Okonkwo", "offer"))


class OrbitIsIndependentOfTheDerivedFiles(ScratchRootTest):
    def test_the_other_golden_files_do_not_depend_on_the_orbit(self):
        """The orbit file is a view: delete it and rebuild, and nothing else moves."""
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

    def test_network_rows_point_at_their_section_3_path(self):
        t = self.trace("C042")
        self.assertEqual({p["reach_type"] for p in t.paths}, {bg.INVESTOR_NETWORK})
        text = t.render()
        self.assertIn("## 5. Additional Investor and Operator Network", text)
        self.assertNotIn("nobody in the network reaches this company", text)
        self.assertIn("investor_network rows rank below every roster path and take a 10% haircut on route score", text)
        self.assertIn("4 askable as investor_network paths, 0 with no warm path", text)
        d = t.as_dict()
        self.assertEqual(len(d["orbit"]), 4)
        self.assertEqual({r["reachable_via"] for r in d["orbit"]}, {bg.INVESTOR_NETWORK})
        self.assertEqual({r["route"] for r in d["orbit"]}, {"investor_network path (section 3, 10% haircut)"})
        self.assertNotIn(f"| {NO_WARM_PATH} |", text)
        self.assertEqual({p["connector"] for p in d["reach"]}, {r["person"] for r in d["orbit"]})

    def test_cold_rows_are_labelled(self):
        """A person no route reaches (reachable_via empty) prints the no-warm-path
        label and sorts last; the fixture has none today, so one is made."""
        base = self.trace("C042")
        cold = {**base.orbit[-1], "person": "Nobody Knows-Her", "board_seat": "no", "reachable_via": ""}
        data = Data(**{**vars(self.data), "orbit": [*self.data.orbit, cold]})
        t = Trace(data, base.c, AS_OF)
        self.assertEqual(t.orbit[-1]["person"], "Nobody Knows-Her")
        text = t.render()
        self.assertIn("5 people from investor_network.csv, 4 askable as investor_network paths, 1 with no warm path", text)
        self.assertEqual(text.count(f"| {NO_WARM_PATH} |"), 1)
        d = t.as_dict()
        self.assertEqual([r["route"] for r in d["orbit"] if not r["reachable_via"]], [NO_WARM_PATH])
        self.assertEqual(d["reach"], base.as_dict()["reach"], "an orbit row is never a path")

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
        self.assertNotIn("## 5.", t.render())
        self.assertEqual(t.as_dict()["orbit"], [])

    def test_the_orbit_changes_nothing_the_allocator_reads(self):
        """Sections 1-4 and the routing strip are computed without the orbit."""
        t = self.trace("C042")
        with_orbit = t.as_dict()
        bare = Trace(Data(**{**vars(self.data), "orbit": []}), t.c, AS_OF).as_dict()
        for key in ("header", "disagreements", "reach", "chronology"):
            with self.subTest(section=key):
                self.assertEqual(with_orbit[key], bare[key])


if __name__ == "__main__":
    unittest.main()
