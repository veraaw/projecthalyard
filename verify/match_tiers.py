"""Three matching tiers over intro_requests.target_company_raw, so the value of
each layer of normalisation is measured against a baseline that has none.

    python3 verify/match_tiers.py

Tier 1  byte for byte: target_company_raw == crm_accounts.account_name.
Tier 2  lowercase and strip spaces on both sides. Nothing else.
Tier 3  full resolution (golden/resolver.py): domain, domain stem, legal and
        holdco suffixes removed, prefix on an 8+ character shared stem, and the
        fund-collision guard refusing bare names such as "Thornbury".

A "company" is a CRM domain group (the resolver's C### id), so two account rows
sharing a domain count once. Whenever a match needed a transformation both
sides are printed as  request string -> CRM account_name.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from golden.resolver import REVIEW_THRESHOLD, Resolver  # noqa: E402

DATASET = ROOT / "dataset"


def read_csv(name: str) -> list[dict]:
    with open(DATASET / name, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def tier2_key(s: str) -> str:
    return s.lower().replace(" ", "")


def main() -> None:
    accounts = read_csv("crm_accounts.csv")
    funds = [r["fund"] for r in read_csv("investor_network.csv")]
    requests = read_csv("intro_requests.csv")
    resolver = Resolver(accounts, funds)

    company_of: dict[str, str] = {}          # account_name -> company id
    for row in resolver.crm_rows():
        company_of[row["account_name"]] = row["company_id"]

    exact: dict[str, str] = {}               # account_name -> company id
    folded: dict[str, set[tuple[str, str]]] = defaultdict(set)  # key -> {(account_name, company id)}
    for name, cid in company_of.items():
        exact[name] = cid
        folded[tier2_key(name)].add((name, cid))

    # matched[tier][request_id] = (request string, CRM account_name matched, company id, how)
    matched: list[dict[str, tuple[str, str, str, str]]] = [{}, {}, {}]
    refused: list[tuple[str, str, str, str]] = []   # request_id, string, method, candidates
    unmatched: Counter = Counter()
    blank = 0
    for r in requests:
        rid, s = r["request_id"], r["target_company_raw"]
        if s in exact:
            matched[0][rid] = (s, s, exact[s], "")
        hits = folded.get(tier2_key(s), set()) if s.strip() else set()
        if len(hits) == 1:
            name, cid = next(iter(hits))
            matched[1][rid] = (s, name, cid, "")
        res = resolver.resolve(s)
        if res.entity is not None and not res.needs_review:
            e = res.entity
            how = f"{res.method} {res.confidence:.2f}" + (f" via {e.domain}" if res.method == "domain-stem" else "")
            matched[2][rid] = (s, e.name, e.entity_id, how)
        elif res.method == "empty":
            blank += 1
        elif res.candidates:
            refused.append((rid, s, res.method, " | ".join(f"{c.entity_id} {c.name} ({c.kind})" for c in res.candidates)))
        else:
            unmatched[s] += 1

    labels = ["Tier 1  byte for byte", "Tier 2  lowercase + strip spaces", "Tier 3  full resolution"]
    prev: dict[str, tuple[str, str, str, str]] = {}
    for i, label in enumerate(labels):
        cur = matched[i]
        companies = {cid for _, _, cid, _ in cur.values()}
        print(f"\n{label}: {len(cur)} requests matched, {len(companies)} distinct companies")
        gained = sorted(set(cur) - set(prev))
        lost = sorted(set(prev) - set(cur))
        print(f"  gained over previous tier: {len(gained)}" + (" -> " + ", ".join(gained) if gained else ""))
        for rid in gained:
            s, name, cid, how = cur[rid]
            arrow = s if s == name else f"{s} -> {name}"
            print(f"    {rid}: {arrow}  [{cid}]" + (f"  {how}" if how else ""))
        if lost:
            print(f"  LOST from previous tier: {len(lost)} -> " + ", ".join(lost))
            for rid in lost:
                s, name, cid, _ = prev[rid]
                print(f"    {rid}: {s} (was {name} [{cid}])")
        prev = cur

    print("\nCompanies tier 2 adds over tier 1 (request string -> CRM account_name):")
    t1_companies = {cid for _, _, cid, _ in matched[0].values()}
    added: dict[str, Counter] = defaultdict(Counter)
    for s, name, cid, _ in matched[1].values():
        if cid not in t1_companies:
            added[cid][(s, name)] += 1
    for cid in sorted(added):
        for (s, name), n in sorted(added[cid].items()):
            print(f"  {s} -> {name}  [{cid}] x{n}")
    if not added:
        print("  (none)")

    print(f"\nTier 3 deliberately refuses {len(refused)} requests (candidates found, confidence < {REVIEW_THRESHOLD:.2f}):")
    for rid, s, method, cands in refused:
        print(f"  {rid}: {s!r}  {method}  ->  {cands}")

    print(f"\nTier 3 unmatched (no CRM candidate at all): {sum(unmatched.values())} requests")
    for s, n in sorted(unmatched.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {s} x{n}")
    print(f"\nBlank target_company_raw: {blank}")

    total = len(matched[2]) + len(refused) + sum(unmatched.values()) + blank
    print(f"\nReconciliation: {len(matched[2])} matched + {len(refused)} refused + "
          f"{sum(unmatched.values())} unmatched + {blank} blank = {total} of {len(requests)} requests")
    assert total == len(requests), total


if __name__ == "__main__":
    main()
