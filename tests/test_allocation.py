"""Tests for golden/golden_allocation.csv, the file the routing argument rests on.

    python3 tests/test_allocation.py

One row per live, not-yet-asked request; each row is either an allocation
(allocated_to + batch_id) or an exception (exception_reason), never both and
never neither. Same shape as tests/test_golden.py: plain asserts, no framework,
exits non-zero on failure.
"""
from __future__ import annotations

import csv
import sys
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

PASS, FAIL = [], []


def check(name: str, condition, detail: str = "") -> None:
    (PASS if condition else FAIL).append((name, detail))


def rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    alloc = rows(G / "golden_allocation.csv")
    requests = {r["request_id"]: r for r in rows(G / "golden_requests.csv")}
    companies = {c["company_id"] for c in rows(G / "golden_companies.csv")}
    roster = {r["name"]: r for r in rows(D / "connector_roster.csv")}
    outcomes = rows(D / "intro_outcomes.csv")

    # ── 1. structure ───────────────────────────────────────────────────
    with open(G / "golden_allocation.csv", newline="", encoding="utf-8") as fh:
        r = csv.reader(fh)
        header = next(r)
        ragged = [i for i, row in enumerate(r, 2) if len(row) != len(header)]
    check(f"every row has {len(header)} fields", not ragged, f"ragged rows at lines {ragged[:5]}")
    check("no None keys (row longer than header)", all(None not in d for d in alloc))
    check("one row per request_id",
          len({a["request_id"] for a in alloc}) == len(alloc),
          f"{len(alloc)} rows, {len({a['request_id'] for a in alloc})} ids")
    cycles = {a["cycle"] for a in alloc}
    check("one cycle per file", len(cycles) == 1, f"cycles: {sorted(cycles)}")
    cycle = next(iter(cycles), "")

    # ── 2. allocation xor exception ────────────────────────────────────
    both = [a["request_id"] for a in alloc if a["allocated_to"] and a["exception_reason"]]
    neither = [a["request_id"] for a in alloc if not a["allocated_to"] and not a["exception_reason"]]
    check("no row is both allocated and an exception", not both, f"both: {both[:5]}")
    check("no row is neither allocated nor an exception", not neither, f"neither: {neither[:5]}")
    allocated = [a for a in alloc if a["allocated_to"]]
    exceptions = [a for a in alloc if a["exception_reason"]]
    check("33 allocated + 50 exceptions = 83 rows",
          (len(allocated), len(exceptions), len(alloc)) == (33, 50, 83),
          f"got {len(allocated)} + {len(exceptions)} = {len(alloc)}")

    # An allocation carries its batch and path; an exception carries none of them.
    half = [a["request_id"] for a in allocated
            if not (a["batch_id"] and a["batch_size"] and a["path_type"] and a["route_score"])]
    check("every allocated row has batch_id, batch_size, path_type, route_score",
          not half, f"incomplete: {half[:5]}")
    leaked = [a["request_id"] for a in exceptions
              if a["batch_id"] or a["batch_size"] or a["path_type"] or a["route_score"] or a["contact_name"]]
    check("no exception row carries batch or path columns", not leaked, f"leaked: {leaked[:5]}")

    # ── 3. referential integrity ───────────────────────────────────────
    missing = [a["request_id"] for a in alloc if a["request_id"] not in requests]
    check("every request_id exists in golden_requests.csv", not missing, f"missing: {missing[:5]}")
    asked = {o["request_id"] for o in outcomes}
    not_live = [a["request_id"] for a in alloc if a["request_id"] in requests
                and requests[a["request_id"]]["status_as_filed"] not in OPEN_STATUSES]
    check("every request is live (Open / Routed / Stalled)", not not_live, f"not live: {not_live[:5]}")
    already = [a["request_id"] for a in alloc if a["request_id"] in asked
               or (a["request_id"] in requests and requests[a["request_id"]]["asked_date"])]
    check("no request has already been asked", not already, f"asked: {already[:5]}")
    orphan = [a["request_id"] for a in alloc if a["company_id"] and a["company_id"] not in companies]
    check("every company_id exists in golden_companies.csv", not orphan, f"orphans: {orphan[:5]}")

    # The other direction: every live, not-yet-asked request has a row. This is
    # what makes "both request_ids must be present" hold when two reps want
    # the same title at the same company.
    live = {rid for rid, r in requests.items()
            if r["status_as_filed"] in OPEN_STATUSES and rid not in asked and not r["asked_date"]}
    unallocated = live - {a["request_id"] for a in alloc}
    check("every live, not-yet-asked request has an allocation row",
          not unallocated, f"missing: {sorted(unallocated)[:5]}")

    # ── 4. capacity ────────────────────────────────────────────────────
    budget: dict[str, int] = defaultdict(lambda: OFF_ROSTER_CAPACITY)
    budget.update({n: int(r["stated_monthly_capacity"]) for n, r in roster.items()})
    for o in outcomes:
        if o["asked_date"].startswith(cycle):
            budget[o["connector_asked"]] -= 1
    load = Counter(a["allocated_to"] for a in allocated)
    over = {n: (k, budget[n]) for n, k in load.items() if k > budget[n]}
    check("no connector exceeds stated_monthly_capacity minus asks already made this cycle",
          not over, f"over: {over}")
    on_roster = {n: k for n, k in load.items() if n in roster}
    check("at least one roster connector is allocated to", bool(on_roster), f"load: {dict(load)}")

    # ── 5. batches ─────────────────────────────────────────────────────
    sizes = Counter(a["batch_id"] for a in allocated)
    wrong = [(a["request_id"], a["batch_size"], sizes[a["batch_id"]]) for a in allocated
             if a["batch_size"] != str(sizes[a["batch_id"]])]
    check("batch_size equals the row count for that batch_id", not wrong, f"wrong: {wrong[:5]}")
    per_connector = defaultdict(set)
    for a in allocated:
        per_connector[(a["cycle"], a["allocated_to"])].add(a["batch_id"])
    split = {k: sorted(v) for k, v in per_connector.items() if len(v) != 1}
    check("one batch_id per connector per cycle", not split, f"split: {split}")
    misnamed = [a["batch_id"] for a in allocated if a["batch_id"] != f"{a['cycle']} {a['allocated_to']}"]
    check("batch_id is '<cycle> <connector>'", not misnamed, f"misnamed: {misnamed[:5]}")

    # ── 6. target_title survives into the batch ────────────────────────
    blank = [a["request_id"] for a in allocated if not a["target_title"]]
    check("every allocated row names a target_title", not blank, f"blank: {blank[:5]}")
    drifted = [(a["request_id"], a["target_title"], requests[a["request_id"]]["target_title"])
               for a in alloc if a["request_id"] in requests
               and a["target_title"] != requests[a["request_id"]]["target_title"]]
    check("target_title matches golden_requests.csv", not drifted, f"drifted: {drifted[:3]}")
    # Two reps asking for the same title at the same company are two asks, not
    # one: the batch must list both request_ids rather than collapsing them.
    wanted = defaultdict(set)
    for rid in live:
        r = requests[rid]
        wanted[(r["company_id"], r["target_title"])].add(rid)
    contested = {k: v for k, v in wanted.items() if len(v) > 1}
    check("some live requests contest the same title at the same company",
          bool(contested), "no shared (company, title) among live requests")
    in_alloc = defaultdict(set)
    for a in alloc:
        in_alloc[(a["company_id"], a["target_title"])].add(a["request_id"])
    collapsed = {k: sorted(v - in_alloc[k]) for k, v in contested.items() if v - in_alloc[k]}
    check("when two reps want the same title, both request_ids are present",
          not collapsed, f"dropped: {collapsed}")
    repeated = Counter((a["batch_id"], a["company_id"], a["target_title"]) for a in allocated)
    check("at least one batch lists the same title twice (two request_ids, one ask)",
          any(n > 1 for n in repeated.values()),
          f"{sum(1 for n in repeated.values() if n > 1)} batches with a repeated title")

    # ── 7. exception reasons ───────────────────────────────────────────
    reasons = Counter(a["exception_reason"] for a in exceptions)
    unknown = set(reasons) - KNOWN_EXCEPTIONS
    check("exception_reason is one of the known set", not unknown, f"unknown: {sorted(unknown)}")
    check("32 no path, 10 capacity exhausted, 8 company unresolved",
          (reasons[NO_PATH], reasons[CAPACITY_EXHAUSTED], reasons[UNRESOLVED]) == (32, 10, 8),
          f"got {dict(reasons)}")
    check("company unresolved rows have no company_id",
          all(not a["company_id"] for a in exceptions if a["exception_reason"] == UNRESOLVED))
    check("every other row has a company_id",
          all(a["company_id"] for a in alloc if a["exception_reason"] != UNRESOLVED))
    check("capacity exhausted rows name the path they would have taken",
          all(a["best_path_if_unbudgeted"] for a in exceptions if a["exception_reason"] == CAPACITY_EXHAUSTED))
    check("no-path and unresolved rows have no best_path_if_unbudgeted",
          all(not a["best_path_if_unbudgeted"] for a in exceptions
              if a["exception_reason"] in (NO_PATH, UNRESOLVED)))

    # ── report ─────────────────────────────────────────────────────────
    for name, detail in PASS:
        print(f"  ok    {name}")
    for name, detail in FAIL:
        print(f"  FAIL  {name}" + (f"\n          {detail}" if detail else ""))
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
