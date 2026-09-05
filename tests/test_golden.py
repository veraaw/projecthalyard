"""Tests for the golden dataset.

Every assertion here corresponds to a bug that actually occurred while building
this, not a hypothetical. That is the point: a test suite written from
imagination tests what you already thought of.

    python3 tests/test_golden.py

Plain asserts, no framework, exits non-zero on failure. Run it after every
regeneration and before every rehearsal.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
G = ROOT / "golden"

PASS, FAIL = [], []


def check(name: str, condition, detail: str = "") -> None:
    (PASS if condition else FAIL).append((name, detail))


def rows(filename: str) -> list[dict]:
    with open(G / filename, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    companies = rows("golden_companies.csv")
    requests = rows("golden_requests.csv")
    reach = rows("supply_reach.csv")

    # ── 1. structure ───────────────────────────────────────────────────
    # A row with an unescaped comma in a multi-value cell has more fields than
    # the header, and every column after it silently shifts. This is how a
    # sample row showed an owner where the stage should be.
    for fn, data in [("golden_companies.csv", companies),
                     ("golden_requests.csv", requests),
                     ("supply_reach.csv", reach)]:
        with open(G / fn, newline="", encoding="utf-8") as fh:
            r = csv.reader(fh)
            header = next(r)
            ragged = [i for i, row in enumerate(r, 2) if len(row) != len(header)]
        check(f"{fn}: every row has {len(header)} fields",
              not ragged, f"ragged rows at lines {ragged[:5]}")
        check(f"{fn}: no None keys (row longer than header)",
              all(None not in d for d in data))

    # ── 2. grain and uniqueness ────────────────────────────────────────
    check("one row per request_id",
          len({r["request_id"] for r in requests}) == len(requests),
          f"{len(requests)} rows, {len({r['request_id'] for r in requests})} ids")
    check("one row per company_id",
          len({c["company_id"] for c in companies}) == len(companies))
    key = lambda x: (x["connector"], x["company_id"], x["reach_type"], x["contact_name"])
    dupes = [k for k, n in Counter(map(key, reach)).items() if n > 1]
    check("supply_reach unique on connector+company+type+contact",
          not dupes, f"{len(dupes)} duplicates")

    # ── 3. referential integrity ───────────────────────────────────────
    company_ids = {c["company_id"] for c in companies}
    orphan_req = {r["company_id"] for r in requests
                  if r["company_id"] and r["company_id"] not in company_ids}
    check("every request's company_id exists in companies",
          not orphan_req, f"orphans: {sorted(orphan_req)[:5]}")
    orphan_reach = {x["company_id"] for x in reach
                    if x["company_id"] and x["company_id"] not in company_ids}
    check("every reach row's company_id exists in companies",
          not orphan_reach, f"orphans: {sorted(orphan_reach)[:5]}")

    # ── 4. conservation — nothing may vanish ───────────────────────────
    check("200 requests preserved", len(requests) == 200, f"got {len(requests)}")
    blanks = [r for r in requests if not r["company_as_written"]]
    check("13 requests are genuinely unresolvable",
          len([r for r in requests if r["resolved_by"] in ("empty", "unresolved")]) == 13,
          f"got {len([r for r in requests if r['resolved_by'] in ('empty','unresolved')])}")

    # ── 5. regression tests for bugs that actually happened ────────────
    named = {c["company_name"] for c in companies}

    # The normaliser stripped "Group" and merged two different companies.
    apex = [c for c in companies if "Apex" in c["company_name"]
            or "Apex" in (c["also_known_as"] or "")]
    check("Apex Logistics and Apex Logistics Group stay separate",
          len({c["company_id"] for c in apex}) >= 2,
          f"found {len({c['company_id'] for c in apex})} Apex companies")

    # Path lookup keyed on the CRM name missed the trading name.
    black = [c for c in companies if "Blackwood" in c["company_name"]
             or "Blackwood" in (c["also_known_as"] or "")]
    check("Blackwood resolves despite CRM/trading name mismatch", bool(black))
    check("aliases are populated where the CRM renames a company",
          sum(1 for c in companies if c["also_known_as"]) >= 5,
          f"{sum(1 for c in companies if c['also_known_as'])} companies with aliases")

    # The CRM holds the same company twice, sometimes under two owners.
    dup = [c for c in companies if c["duplicate_accounts"] != "no"]
    check("6 duplicate CRM clusters detected", len(dup) == 6, f"got {len(dup)}")
    check("5 of them have disagreeing owners",
          sum(1 for c in dup if "disagree" in c["duplicate_accounts"]) == 5)

    # supply_reach was the raw connection export: 4,975 of 5,075 rows pointed at
    # companies nobody sells to.
    DECOYS = {"Inglenook Bakery", "Tannerly Design", "Corbridge Realty",
              "Whitlock Staffing", "Bellchamber Media", "Elmsworth Tutors",
              "Ambrose Trading", "Fairbourne Fitness", "Yardley Print", "Zenner Foods"}
    leaked = DECOYS & {x["company_name"] for x in reach}
    check("no out-of-scope companies in supply_reach",
          not leaked, f"leaked: {sorted(leaked)}")
    check("supply_reach is a filtered view, not the raw export",
          len(reach) < 500, f"{len(reach)} rows — the six exports total 5,075")

    # All path kinds must survive the filter. Board seats are investor paths
    # with board_seat = yes (a strength modifier, not a separate mechanism).
    kinds = Counter(x["reach_type"] for x in reach)
    for k in ("direct", "alumni", "offer", "investor"):
        check(f"supply_reach contains {k} paths", kinds[k] > 0, f"{k}={kinds[k]}")
    seats = [x for x in reach if x["board_seat"] == "yes"]
    check("supply_reach contains board seats",
          seats and all(x["reach_type"] == "investor" for x in seats),
          f"{len(seats)} rows with board_seat = yes")

    # Every askable person must appear, even with no path.
    check("every connector appears at least once",
          len({x["connector"] for x in reach}) >= 6,
          f"{len({x['connector'] for x in reach})} connectors present")

    # ── 6. cross-file agreement ────────────────────────────────────────
    by_company = Counter(r["company_id"] for r in requests if r["company_id"])
    mismatched = [c["company_name"] for c in companies
                  if int(c["total_requests"]) != by_company[c["company_id"]]]
    check("total_requests matches the request rows",
          not mismatched, f"mismatched: {mismatched[:5]}")

    reach_by_company = Counter(x["company_id"] for x in reach)
    bad_paths = [c["company_name"] for c in companies
                 if int(c["paths_available"]) != reach_by_company[c["company_id"]]]
    check("paths_available matches supply_reach",
          not bad_paths, f"mismatched: {bad_paths[:5]}")

    if any("durable_paths" in c for c in companies):
        durable = Counter(x["company_id"] for x in reach if x["reach_type"] != "offer")
        bad = [c["company_name"] for c in companies
               if int(c["durable_paths"]) != durable[c["company_id"]]]
        check("durable_paths excludes offers", not bad, f"mismatched: {bad[:5]}")

    # ── 7. the numbers the presentation rests on ───────────────────────
    routed = [r for r in requests if r["routed_to"]]
    check("some requests are routed", len(routed) > 40, f"{len(routed)} routed")
    offers = [x for x in reach if x["reach_type"] == "offer"]
    check("15 offers found in the Slack threads", len(offers) == 15, f"got {len(offers)}")

    # ── report ─────────────────────────────────────────────────────────
    for name, detail in PASS:
        print(f"  ok    {name}")
    for name, detail in FAIL:
        print(f"  FAIL  {name}" + (f"\n          {detail}" if detail else ""))
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
