"""Tests for golden/golden_allocation.csv, the file the routing argument rests on.

    python3 -m unittest tests.test_allocation

The file is the connector history, one row per (cycle, request_id); the
current allocation is its latest cycle. Within a cycle: one row per live,
not-yet-asked request, plus one per asked request whose own intro fizzled with
no re-ask logged since (back as a retry); each row is either an allocation
(allocated_to + batch_id) or an exception (exception_reason), never both and
never neither. A company is one ask: its allocated rows share one connector,
path and contact, one of them is the lead (rides_with empty) and the rest ride
on it (rides_with = the lead's request_id); capacity and batch_size count asks.
Counts are derived from golden_requests.csv, golden_companies.csv and
dataset/, never fixed: the request file grows on every merge.
"""
from __future__ import annotations

import csv
import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from golden.build_golden import (  # noqa: E402
    ALREADY_INTRODUCED, CAPACITY_EXHAUSTED, HOLD_LAST, HOLD_NUDGE, HOLD_WINDOW, INTRO_LIVE_DAYS, MULTI, NOTIFY_STAGES,
    OPEN_STATUSES, STALE_ASK, UNANSWERED_ASK_DAYS, UNRESOLVED_ASK, URGENCY_RANK, Company, cycle_budget, history_signals,
    hold_reason, intro_of, introductions, is_lead, latest_cycle, load_roster, meeting_stalled, owner_to_notify, parse_date,
    path_rank, retriable, unresolved_asks,
)

G = ROOT / "golden"
D = ROOT / "dataset"

NO_PATH = "no path to this company in the network"
UNRESOLVED = "company unresolved"
ALWAYS_PRESENT = {NO_PATH, UNRESOLVED}
# STALE_ASK needs a prior cycle, ALREADY_INTRODUCED a live intro, CAPACITY_EXHAUSTED more
# companies asked for than the roster has slots and UNRESOLVED_ASK a company whose every
# path is held by an unresolved ask, so any of them may be absent
KNOWN_EXCEPTIONS = ALWAYS_PRESENT | {STALE_ASK, ALREADY_INTRODUCED, CAPACITY_EXHAUSTED, UNRESOLVED_ASK}
BATCH_COLUMNS = ("batch_id", "batch_size", "path_type", "route_score")


def rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


class AllocationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history = rows(G / "golden_allocation.csv")
        cls.alloc = latest_cycle(cls.history)
        cls.requests = {r["request_id"]: r for r in rows(G / "golden_requests.csv")}
        cls.companies = {c["company_id"]: c for c in rows(G / "golden_companies.csv")}
        cls.roster = {r["name"]: r for r in rows(D / "connector_roster.csv")}
        cls.roster_full = load_roster()
        cls.outcomes = rows(D / "intro_outcomes.csv")
        cls.asked = {o["request_id"] for o in cls.outcomes}
        cls.allocated = [a for a in cls.alloc if a["allocated_to"]]
        cls.leads = [a for a in cls.allocated if is_lead(a)]
        cls.riders = [a for a in cls.allocated if not is_lead(a)]
        cls.exceptions = [a for a in cls.alloc if a["exception_reason"]]
        cls.cycle = cls.alloc[0]["cycle"] if cls.alloc else ""
        decided = parse_date(cls.alloc[0]["decided_at"]) if cls.alloc else None
        cls.retry = {o["request_id"] for o in cls.outcomes if decided and retriable(o, decided)}
        cls.supply = defaultdict(list)
        for p in rows(G / "supply_reach.csv"):
            if p["reach_type"] != "none":
                cls.supply[p["company_id"]].append(p)
        # what the allocator should have covered
        cls.live = {rid for rid, r in cls.requests.items()
                    if r["status_as_filed"] in OPEN_STATUSES
                    and ((rid not in cls.asked and not r["asked_date"]) or rid in cls.retry)}

    # ── 1. structure ───────────────────────────────────────────────────
    def test_every_row_has_the_headers_field_count(self):
        with open(G / "golden_allocation.csv", newline="", encoding="utf-8") as fh:
            r = csv.reader(fh)
            header = next(r)
            ragged = [i for i, row in enumerate(r, 2) if len(row) != len(header)]
        self.assertEqual(ragged, [], f"ragged rows at lines {ragged[:5]}")
        self.assertTrue(all(None not in a for a in self.alloc), "row longer than header")

    def test_one_row_per_cycle_and_request_id(self):
        dupes = [k for k, n in Counter((a["cycle"], a["request_id"]) for a in self.history).items() if n > 1]
        self.assertEqual(dupes, [])
        self.assertEqual({a["cycle"] for a in self.alloc}, {self.cycle})

    def test_every_row_is_stamped_with_when_it_was_decided(self):
        for a in self.history:
            with self.subTest(cycle=a["cycle"], request_id=a["request_id"]):
                d = parse_date(a["decided_at"])
                self.assertIsNotNone(d, a["decided_at"])
                self.assertEqual(d.strftime("%Y-%m"), a["cycle"], "decided within its own cycle")
        self.assertEqual(len({a["decided_at"] for a in self.alloc}), 1, "one run decides the whole cycle")

    def test_cycles_are_in_order_and_the_latest_is_the_current_one(self):
        cycles = [a["cycle"] for a in self.history]
        self.assertEqual(cycles, sorted(cycles), "a cycle is appended after every earlier one")
        self.assertEqual(self.cycle, max(cycles))

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
        already = [a["request_id"] for a in self.alloc if a["request_id"] not in self.retry
                   and (a["request_id"] in self.asked or self.requests[a["request_id"]]["asked_date"])]
        self.assertEqual(already, [], "already asked")

    def test_an_asked_request_comes_back_only_once_its_own_intro_fizzled(self):
        # The retry rows are exactly the asked requests whose own intro went out,
        # booked nothing and is older than INTRO_LIVE_DAYS; an ask still waiting
        # on a reply, or an intro that booked a meeting, stays off the file.
        decided = parse_date(self.alloc[0]["decided_at"])
        back = {a["request_id"] for a in self.alloc} & self.asked
        self.assertTrue(back, "the golden allocation retries at least one asked request")
        self.assertEqual(back, self.retry & self.live, "every open retry, and nothing filed closed")
        for o in self.outcomes:
            if o["request_id"] in back:
                self.assertEqual(o["intro_sent"], "Y", f"{o['request_id']} back in the queue with no intro sent")
                self.assertEqual(o["meeting_booked"], "N", f"{o['request_id']} back in the queue after a meeting")
                self.assertGreater((decided - parse_date(o["intro_date"])).days, INTRO_LIVE_DAYS, o["request_id"])
        # R1154: Marcus Aldridge's 2026-03-11 Apex Holdings intro never booked, so
        # the request is back in the queue rather than parked behind his own ask.
        # It is not back on his plate: R1069 (Apex, 2025-11-01) is an ask he never
        # answered, so he ranks behind every other path into Apex (HOLD_LAST).
        apex = next(a for a in self.alloc if a["request_id"] == "R1154")
        self.assertEqual(apex["company_id"], "C003")
        self.assertTrue(apex["allocated_to"], apex["exception_reason"])
        self.assertNotEqual(apex["allocated_to"], "Marcus Aldridge")

    def test_every_live_request_has_exactly_one_row(self):
        # The other direction: nothing live is skipped. Together with one row
        # per request_id this is what keeps two reps wanting the same title
        # both on file even though the company is asked for once.
        self.assertEqual({a["request_id"] for a in self.alloc}, self.live)

    def test_every_company_id_exists_in_golden_companies(self):
        orphans = [a["request_id"] for a in self.alloc
                   if a["company_id"] and a["company_id"] not in self.companies]
        self.assertEqual(orphans, [])

    # ── 4. capacity ────────────────────────────────────────────────────
    def test_no_connector_exceeds_capacity_for_the_cycle(self):
        # Same budget the allocator uses: stated_monthly_capacity
        # (OFF_ROSTER_CAPACITY for anyone else) less the asks the prior cycles
        # of this file proposed to them in the trailing window beyond one
        # month's capacity. intro_outcomes.csv plays no part.
        # An ask is a company: riders on a lead's ask cost no slot.
        today = parse_date(self.alloc[0]["decided_at"])
        fatigue = history_signals(self.history, self.outcomes, today).fatigue
        load = Counter(a["allocated_to"] for a in self.leads)
        over = {n: (k, cycle_budget(self.roster_full, fatigue, n)) for n, k in load.items()
                if k > cycle_budget(self.roster_full, fatigue, n)}
        self.assertEqual(over, {}, "asks > budget")
        self.assertTrue(set(load) & set(self.roster), "no roster connector allocated to")
        rows_by = Counter(a["allocated_to"] for a in self.allocated)
        self.assertTrue(any(rows_by[n] > cycle_budget(self.roster_full, fatigue, n) for n in rows_by),
                        "the golden allocation has a connector carrying more requests than slots, thanks to riders")

    # ── 4b. a company is one ask ─────────────────────────────────────────
    def test_a_company_goes_to_one_connector_as_one_ask(self):
        by_company = defaultdict(list)
        for a in self.allocated:
            by_company[a["company_id"]].append(a)
        for cid, rows_ in by_company.items():
            with self.subTest(company_id=cid):
                self.assertEqual(len({(a["allocated_to"], a["batch_id"], a["path_type"], a["contact_name"], a["route_score"])
                                      for a in rows_}), 1, "one connector, path and contact for the company")
                leads = [a for a in rows_ if is_lead(a)]
                self.assertEqual(len(leads), 1, "exactly one row paid the slot")
                lead = leads[0]
                for a in rows_:
                    if a is not lead:
                        self.assertEqual(a["rides_with"], lead["request_id"])
                # the lead is the company's highest-priority request: urgency, value, age, id
                key = lambda a: (URGENCY_RANK.get(a["urgency_declared"], 9), -float(a["value_usd"] or 0),
                                 a["request_date"], a["request_id"])
                self.assertEqual(min(rows_, key=key)["request_id"], lead["request_id"])
        self.assertTrue(self.riders, "the golden allocation has a company with more than one live request")
        self.assertTrue(all(not a["rides_with"] for a in self.exceptions), "an exception rides on nothing")
        # Blackwood: three live requests, one ask
        blackwood = [a for a in self.allocated if a["company_id"] == "C006"]
        self.assertGreater(len(blackwood), 1)
        self.assertEqual(len({a["allocated_to"] for a in blackwood}), 1, "Blackwood asked of one connector, not three")

    # ── 5. batches ─────────────────────────────────────────────────────
    def test_batch_size_counts_the_companies_in_that_batch(self):
        sizes = Counter(a["batch_id"] for a in self.leads)
        wrong = [(a["request_id"], a["batch_size"], sizes[a["batch_id"]]) for a in self.allocated
                 if a["batch_size"] != str(sizes[a["batch_id"]])]
        self.assertEqual(wrong, [])
        companies = defaultdict(set)
        for a in self.allocated:
            companies[a["batch_id"]].add(a["company_id"])
        self.assertEqual({b: len(c) for b, c in companies.items()}, dict(sizes))
        self.assertTrue(any(a["batch_size"] != str(Counter(x["batch_id"] for x in self.allocated)[a["batch_id"]])
                            for a in self.allocated), "some batch carries more requests than asks")

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
        # Two reps asking for the same title at the same company are one ask
        # to the connector, but two requests to us: the file must list both
        # request_ids rather than collapsing them, each allocated on its own
        # row (one the lead, one riding on it).
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
        routed = Counter((a["company_id"], a["target_title"]) for a in self.allocated)
        self.assertTrue(any(routed[k] > 1 for k in contested),
                        "no contested title has both requests allocated")
        for k in contested:
            both = [a for a in self.allocated if (a["company_id"], a["target_title"]) == k]
            if len(both) > 1:
                self.assertEqual(sum(1 for a in both if is_lead(a)) + sum(1 for a in both if a["rides_with"]), len(both))
                self.assertLessEqual(sum(1 for a in both if is_lead(a)), 1, "one ask, not two")

    # ── 7. exception reasons ───────────────────────────────────────────
    def test_exception_reason_is_one_of_the_known_set(self):
        # STALE_ASK carries its detail after a colon: '<reason>: <connector> in <cycle>'
        reasons = Counter(a["exception_reason"].split(":")[0] for a in self.exceptions)
        self.assertEqual(set(reasons) - KNOWN_EXCEPTIONS, set())
        self.assertLessEqual(ALWAYS_PRESENT, set(reasons), "every reason a single cycle can produce occurs")
        for a in self.exceptions:
            if a["exception_reason"].startswith(STALE_ASK):
                connector, cycle = a["exception_reason"][len(STALE_ASK) + 2:].rsplit(" in ", 1)
                self.assertLess(cycle, a["cycle"], "proposed in an earlier cycle")
                prior = [h for h in self.history if h["cycle"] == cycle and h["allocated_to"] == connector
                         and h["company_id"] == a["company_id"]]
                self.assertTrue(prior, f"{a['request_id']}: {connector} was never proposed {a['company_id']} in {cycle}")
                self.assertTrue(all(h["request_id"] not in self.asked for h in prior), "no outcome logged")

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
                elif a["exception_reason"].startswith(ALREADY_INTRODUCED):
                    self.assertTrue(a["company_id"])  # parked on the company's intro, path or no path
                else:  # capacity exhausted, already proposed or every path held: a path exists and is named
                    self.assertNotEqual(self.companies[a["company_id"]]["paths_available"], "0")
                    self.assertTrue(a["best_path_if_unbudgeted"])
        no_company = [a["request_id"] for a in self.alloc
                      if not a["company_id"] and a["exception_reason"] != UNRESOLVED]
        self.assertEqual(no_company, [], "no company_id yet not flagged as unresolved")

    # ── 8. a company already introduced is not asked afresh ─────────────
    def test_live_intro_parks_the_company_and_a_fizzled_one_is_retried(self):
        """Every request on a company whose intro is live (meeting booked, or sent
        within INTRO_LIVE_DAYS of the decision) is parked as ALREADY_INTRODUCED,
        naming that intro; none is allocated. A company whose newest intro fizzled
        is routed like any other. The parking is per company, not per request."""
        decided = parse_date(self.alloc[0]["decided_at"])
        company_of = {rid: r["company_id"] for rid, r in self.requests.items()}
        open_since = defaultdict(list)
        for r in self.requests.values():
            if r["company_id"] and r["status_as_filed"] in OPEN_STATUSES:
                open_since[r["company_id"]].append(r["request_date"])
        intro_of = introductions(self.outcomes, company_of, decided, open_since)
        parked = [a for a in self.alloc if a["exception_reason"].startswith(ALREADY_INTRODUCED)]
        self.assertTrue(parked, "the golden allocation parks at least one request behind a live intro")
        for a in parked:
            with self.subTest(request_id=a["request_id"]):
                intro = intro_of[a["company_id"]]
                self.assertTrue(intro["live"])
                self.assertTrue(a["request_id"] not in self.asked or a["request_id"] in self.retry,
                                "parked rows are requests never asked themselves, or retries of their own fizzled intro")
                self.assertEqual(a["allocated_to"], "")
                self.assertIn(intro["connector"], a["exception_reason"])
                self.assertIn(intro["intro_date"], a["exception_reason"])
                self.assertIn(intro["request_id"], a["exception_reason"])
                self.assertEqual("meeting booked" in a["exception_reason"], intro["meeting_booked"])
                if not intro["meeting_booked"]:
                    self.assertLessEqual((decided - parse_date(intro["intro_date"])).days, INTRO_LIVE_DAYS)
        live_companies = {cid for cid, i in intro_of.items() if i["live"]}
        for a in self.alloc:
            if a["company_id"] in live_companies:
                self.assertTrue(a["exception_reason"].startswith(ALREADY_INTRODUCED), f"{a['request_id']} asked afresh behind a live intro")
        retried = [a for a in self.allocated if a["company_id"] in intro_of]
        self.assertTrue(retried, "a company whose intro fizzled is back in the queue")
        for a in retried:
            intro = intro_of[a["company_id"]]
            self.assertFalse(intro["live"])
            self.assertFalse(intro["opportunity"])
            self.assertGreater((decided - parse_date(intro["intro_date"])).days, INTRO_LIVE_DAYS, a["request_id"])
            if intro["meeting_booked"]:
                self.assertTrue(meeting_stalled(intro, open_since[a["company_id"]]), a["request_id"])

    # ── 8b. a connector sitting on an unresolved ask at the company ──────────
    def test_an_unresolved_ask_holds_the_connectors_paths_into_the_company(self):
        """A connector with an unresolved ask at a company is not asked there
        afresh: never while they agreed and sent no intro (HOLD_NUDGE: nudge
        them), not for UNANSWERED_ASK_DAYS while they never replied
        (HOLD_WINDOW: chase them), and after that only behind every path with
        no such ask (HOLD_LAST). A request whose every path is held is an
        exception naming each ask."""
        decided = parse_date(self.alloc[0]["decided_at"])
        company_of = {rid: r["company_id"] for rid, r in self.requests.items()}
        held = unresolved_asks(self.outcomes, company_of, decided)
        self.assertTrue(held)
        kinds = Counter(u["hold"] for u in held.values())
        self.assertTrue(kinds[HOLD_NUDGE] and kinds[HOLD_LAST], "the dataset has agreed-and-silent and long-unanswered asks")
        for (connector, cid), u in held.items():
            with self.subTest(connector=connector, company_id=cid):
                o = next(o for o in self.outcomes if o["request_id"] == u["request_id"])
                self.assertEqual((o["connector_asked"], company_of[o["request_id"]], o["intro_sent"]), (connector, cid, "N"))
                if u["hold"] == HOLD_NUDGE:
                    self.assertEqual(o["responded"], "Y")
                else:
                    self.assertEqual(o["responded"], "N")
                    days = (decided - parse_date(o["asked_date"])).days
                    self.assertEqual(u["hold"], HOLD_WINDOW if days <= UNANSWERED_ASK_DAYS else HOLD_LAST)
                # every other outcome of the pair binds no harder than the one chosen
                for other in self.outcomes:
                    if other["connector_asked"] == connector and company_of[other["request_id"]] == cid \
                            and other["intro_sent"] == "N" and other["responded"] == "Y":
                        self.assertEqual(u["hold"], HOLD_NUDGE, f"{other['request_id']} was agreed to")
        # the allocation honours the holds
        exceptions = [a for a in self.exceptions if a["exception_reason"].startswith(UNRESOLVED_ASK)]
        for a in self.alloc:
            if not a["company_id"] or a["exception_reason"].startswith(ALREADY_INTRODUCED):
                continue
            with self.subTest(request_id=a["request_id"]):
                u = held.get((a["allocated_to"], a["company_id"])) if a["allocated_to"] else None
                if u is not None:
                    self.assertEqual(u["hold"], HOLD_LAST, f"asked afresh while {hold_reason(u)}")
                    industry = self.companies[a["company_id"]]["industry"]
                    clean = [p for p in self.supply[a["company_id"]] if (p["connector"], a["company_id"]) not in held
                             and path_rank(p, self.roster_full, {}, industry)[1] < 0]
                    for p in clean:
                        self.assertLessEqual(int(p["idle_capacity"] or 0), 0, f"{p['connector']} had a clean path and a slot")
                if a in exceptions:
                    self.assertEqual(a["allocated_to"], "")
                    paths = {p["connector"] for p in self.supply[a["company_id"]]}
                    self.assertTrue(paths)
                    for who in paths:
                        u = held[(who, a["company_id"])]
                        self.assertIn(u["hold"], (HOLD_NUDGE, HOLD_WINDOW))
                        self.assertIn(hold_reason(u), a["exception_reason"])
        # Brightmoor Energy: Elena agreed to R1190 and never sent the intro; hers
        # is the only path, so R1123 waits on the nudge instead of a fresh ask
        r1123 = next(a for a in self.alloc if a["request_id"] == "R1123")
        self.assertIn("Elena Duvall agreed on", r1123["exception_reason"])
        self.assertTrue(r1123["exception_reason"].startswith(UNRESOLVED_ASK))
        # Hollowbrook Grocers: Priya never answered R1124 (well past the window), so
        # she ranks behind Dana Whitfield's clean path even though hers scores higher
        hollowbrook = [a for a in self.alloc if a["company_id"] == "C019"]
        self.assertTrue(hollowbrook)
        self.assertEqual(held[("Priya Raghunathan", "C019")]["hold"], HOLD_LAST)
        self.assertEqual({a["allocated_to"] for a in hollowbrook}, {"Dana Whitfield"})

    # ── 9. a meeting that went nowhere stops holding the company ──────────────
    def test_a_stalled_meeting_releases_the_requests_filed_after_it(self):
        """A booked meeting parks the company only until it has gone INTRO_LIVE_DAYS
        without an opportunity while open requests filed after the intro wait on
        it; then those requests are routed (as retries). A meeting that created an
        opportunity, or one nobody has asked about since, keeps parking."""
        decided = parse_date(self.alloc[0]["decided_at"])
        by_rid = {a["request_id"]: a for a in self.alloc}
        meetings = [(o, intro_of(o, decided)) for o in self.outcomes if o["meeting_booked"] == "Y"]
        stalled, held = [], []
        for o, i in meetings:
            cid = self.requests[o["request_id"]]["company_id"]
            after = [r for r in self.requests.values() if r["company_id"] == cid
                     and r["status_as_filed"] in OPEN_STATUSES and r["request_date"] > o["intro_date"]]
            (stalled if meeting_stalled(i, [r["request_date"] for r in after]) else held).append((o, i, cid, after))
        self.assertTrue(stalled, "the dataset has a meeting that stalled with newer requests waiting")
        self.assertTrue(held)
        for o, i, cid, after in stalled:
            with self.subTest(request_id=o["request_id"]):
                self.assertEqual(o["opportunity_created"], "N")
                self.assertGreater(i["days"], INTRO_LIVE_DAYS)
                self.assertTrue(after)
                self.assertIn("no opportunity", i["outcome"])
                self.assertNotIn(o["request_id"], by_rid, "the request that got the meeting is not itself re-asked")
                # nothing is parked behind this meeting; only a later, live intro on the company may still park
                for r in after:
                    if r["request_id"] in by_rid:
                        self.assertNotIn(f"({o['request_id']}", by_rid[r["request_id"]]["exception_reason"], r["request_id"])
        for o, i, cid, after in held:
            self.assertTrue(o["opportunity_created"] == "Y" or i["days"] is None or i["days"] <= INTRO_LIVE_DAYS or not after,
                            o["request_id"])
        # Apex Logistics: Elena's meeting on R1038 produced no opportunity, R1024 was filed after it
        r1038 = next(o for o in self.outcomes if o["request_id"] == "R1038")
        self.assertEqual((r1038["meeting_booked"], r1038["opportunity_created"]), ("Y", "N"))
        self.assertIn("R1038", [o["request_id"] for o, *_ in stalled])
        self.assertEqual(by_rid["R1024"]["company_id"], "C002")
        self.assertTrue(by_rid["R1024"]["allocated_to"], by_rid["R1024"]["exception_reason"])

    # ── 10. notify_owner: a heads-up to the AE, never a gate ────────────────────────
    def test_notify_owner_fires_on_a_late_stage_account_someone_else_asked_for(self):
        """An allocated request on a company whose CRM stage is in NOTIFY_STAGES,
        asked for by someone other than the account owner, names the owner(s) in
        notify_owner (both, pipe-separated, when duplicate accounts disagree).
        Blank when the requester is the owner, the stage is earlier, or the
        request is an exception. It changes nothing about who is allocated."""
        def company(*accounts: tuple[str, str, str]) -> Company:
            c = Company("x.com")
            c.accounts = [{"account_id": aid, "owner": owner, "stage": stage} for aid, owner, stage in accounts]
            return c
        late = company(("A1", "Imani Mkhize", "Pilot"))
        self.assertEqual(owner_to_notify(late, "Nadia Okonkwo"), "Imani Mkhize")
        self.assertEqual(owner_to_notify(late, "Imani Mkhize"), "", "the owner asking for their own account")
        self.assertEqual(owner_to_notify(company(("A1", "Imani Mkhize", "Discovery")), "Nadia Okonkwo"), "")
        self.assertEqual(owner_to_notify(company(("A1", "Imani Mkhize", "Closed Lost")), "Nadia Okonkwo"), "")
        self.assertEqual(owner_to_notify(Company("nowhere.com"), "Nadia Okonkwo"), "", "no CRM account, no owner")
        two = company(("A1", "Imani Mkhize", "Negotiation"), ("A91", "Nadia Okonkwo", "Prospect"))
        self.assertEqual(owner_to_notify(two, "Yusuf Petrossian"), f"Imani Mkhize{MULTI}Nadia Okonkwo", "both owners, neither picked")
        self.assertEqual(owner_to_notify(two, "Nadia Okonkwo"), "", "either owner counts as the owner")
        # the file agrees with the rule, row by row, and the rule never touched the routing
        flagged = []
        for a in self.alloc:
            with self.subTest(request_id=a["request_id"]):
                if not a["allocated_to"]:
                    self.assertEqual(a["notify_owner"], "", "only an allocated request is flagged")
                    continue
                c = self.companies[a["company_id"]]
                owners = [o for o in c["owner"].split(MULTI) if o]
                who = self.requests[a["request_id"]]["requested_by"]
                expected = MULTI.join(owners) if c["stage"] in NOTIFY_STAGES and owners and who not in owners else ""
                self.assertEqual(a["notify_owner"], expected)
                if expected:
                    flagged.append(a)
        self.assertTrue(flagged, "the dataset has a late-stage account someone other than its owner asked for")
        # Hollowbrook Grocers (Pilot): two accounts, two owners, Bertrand asked; both owners are named
        hollowbrook = [a for a in flagged if a["company_id"] == "C019"]
        self.assertTrue(hollowbrook)
        self.assertEqual({a["notify_owner"] for a in hollowbrook}, {f"Imani Mkhize{MULTI}Nadia Okonkwo"})
        self.assertEqual({a["allocated_to"] for a in hollowbrook}, {"Dana Whitfield"}, "flagged, still routed")


if __name__ == "__main__":
    unittest.main()
