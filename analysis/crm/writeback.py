#!/usr/bin/env python3
"""What the CRM needs to learn from the routing data.

    python3 analysis/crm/writeback.py                     # writes analysis/crm/, prints counts
    python3 analysis/crm/writeback.py --as-of 2026-09-05

Five groups, every one derived from golden/ (never from dataset/ directly,
except crm_accounts.csv for last_touch_date), ordered by whether the CRM being
wrong is costing something right now:

  1. create    companies with requests and no CRM account: every request against
               them is blocked because there is nowhere to log it
  2. merge     one company, two CRM accounts: pipeline is double counted and the
               requests split across two records
  3. owners    of those duplicates, the ones where the two owners disagree: two
               reps both think they own it
  4. reopen    live requests against a Closed Lost account: either the account is
               wrong (reopen) or the requests are (close them) - both can be true
  5. stale     open requests against an account nobody has touched in 90+ days:
               nothing is blocked yet, the CRM is just falling behind

Two exports, and nothing in either has been executed - they are recommendations:

  crm_import.csv   the machine artifact: group 1 only, in the shape a CRM
                   importer accepts and nothing else - account_name, domain,
                   owner, stage, source, plus blocked_requests and
                   requested_value_usd so whoever imports it can see why. Owner
                   is the rep who asked first, stage Prospect.
  crm_review.csv   the human record of what the run recommended: all five groups,
                   one row per recommendation - what to do, why, the evidence, the
                   value at stake and the request ids behind it. Merges and owner
                   reassignments never go into the import file.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from golden.build_golden import MULTI, OPEN_STATUSES, parse_date, read_csv, write_csv  # noqa: E402
from paths import CRM, DATASET, GOLDEN  # noqa: E402

IMPORT_OUT = CRM / "crm_import.csv"
REVIEW_OUT = CRM / "crm_review.csv"

STALE_TOUCH_DAYS = 90
CLOSED_LOST = "Closed Lost"
DEFAULT_STAGE = "Prospect"
SOURCE = "Halyard intro requests"
STATUS = "recommended"  # this file never executes anything

CREATE, MERGE, OWNERS, REOPEN, STALE = "create", "merge", "owners", "reopen", "stale"
GROUPS = [CREATE, MERGE, OWNERS, REOPEN, STALE]  # costing something now -> falling behind
GROUP_TITLES = {
    CREATE: "create these accounts",
    MERGE: "merge these duplicates",
    OWNERS: "two people own this",
    REOPEN: "reopen or close",
    STALE: "nobody has touched these",
}

IMPORT_COLUMNS = ["account_name", "domain", "owner", "stage", "source", "blocked_requests", "requested_value_usd"]
REVIEW_COLUMNS = [
    "rank", "group", "company_id", "company_name", "crm_account_ids", "owner", "stage",
    "action", "why", "evidence", "value_at_stake_usd", "request_ids", "status", "executed_on",
]


@dataclass
class Row:
    rank: int
    group: str
    company_id: str
    company_name: str
    crm_account_ids: str
    owner: str
    stage: str
    action: str
    why: str
    evidence: str
    value_at_stake_usd: int
    request_ids: str
    status: str = STATUS
    executed_on: str = ""


def split_bar(s: str) -> list[str]:
    return [p.strip() for p in (s or "").split("|") if p.strip()]


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def money(v: int | str) -> str:
    return f"${int(v or 0):,}"


def value(rows: list[dict]) -> int:
    return sum(int(r["value_usd"] or 0) for r in rows)


def ids(rows: list[dict]) -> str:
    return MULTI.join(r["request_id"] for r in rows)


class Writeback:
    def __init__(self, today: date):
        self.today = today
        self.companies = [c for c in read_csv(GOLDEN / "golden_companies.csv") if int(c["total_requests"] or 0)]
        self.accounts = {a["account_id"]: a for a in read_csv(DATASET / "crm_accounts.csv")}
        by_company: dict[str, list[dict]] = {}
        for r in read_csv(GOLDEN / "golden_requests.csv"):
            if r["company_id"]:
                by_company.setdefault(r["company_id"], []).append(r)
        self.requests = {cid: sorted(rs, key=lambda r: (r["request_date"], r["request_id"]))
                         for cid, rs in by_company.items()}

    # -- helpers --------------------------------------------------------------
    def reqs(self, c: dict) -> list[dict]:
        return self.requests.get(c["company_id"], [])

    def live(self, c: dict) -> list[dict]:
        return [r for r in self.reqs(c) if r["status_as_filed"] in OPEN_STATUSES]

    def accts(self, c: dict) -> list[dict]:
        return [self.accounts[a] for a in split_bar(c["crm_account_ids"]) if a in self.accounts]

    def last_touch(self, c: dict) -> date | None:
        touches = [parse_date(a["last_touch_date"]) for a in self.accts(c)]
        return max((t for t in touches if t), default=None)

    def requesters(self, rows: list[dict]) -> str:
        counts = Counter(r["requested_by"] for r in rows)
        return ", ".join(f"{who} ({n})" if n > 1 else who for who, n in counts.most_common())

    def row(self, group: str, c: dict, action: str, why: str, evidence: str, at_stake: int, rows: list[dict]) -> Row:
        return Row(GROUPS.index(group) + 1, group, c["company_id"], c["company_name"], c["crm_account_ids"],
                   c["owner"], c["stage"], action, why, evidence, at_stake, ids(rows))

    # -- groups ---------------------------------------------------------------
    def create(self) -> list[Row]:
        out = []
        for c in self.companies:
            if c["crm_account_ids"]:
                continue
            reqs, live = self.reqs(c), self.live(c)
            first = reqs[0]
            blocked = [r for r in reqs if r["blocked_reason"] == "company has no CRM record"]
            evidence = (f"{plural(len(reqs), 'request')} from {plural(int(c['distinct_requesters']), 'rep')}"
                        f" since {first['request_date']} ({self.requesters(reqs)}); {len(live)} still live"
                        + (f"; {len(blocked)} filed as blocked for no CRM record" if blocked else "")
                        + (f"; domain {c['domain']}" if c["domain"] else "; no domain on record")
                        + (f"; {plural(int(c['paths_available']), 'path')} into the company" if int(c["paths_available"] or 0) else ""))
            why = (f"{plural(len(live), 'live request')} worth {money(value(live))} have no account to log against" if live
                   else f"{plural(len(reqs), 'request')} were filed with no account to log against; none still live")
            out.append(self.row(
                CREATE, c, f"create account, owner {first['requested_by']}, stage {DEFAULT_STAGE}",
                why, evidence, value(live), live or reqs))
        return out

    def duplicates(self) -> list[dict]:
        return [c for c in self.companies if c["duplicate_accounts"] != "no"]

    def merge(self) -> list[Row]:
        out = []
        for c in self.duplicates():
            accts = self.accts(c)
            # same survivor rule as golden.build_golden.Company.survivor: the non-A9 account
            survivor, *others = sorted(accts, key=lambda a: (a["account_id"].startswith("A9"), a["account_id"]))
            reqs = self.reqs(c)
            names = "; ".join(f"{a['account_id']} \"{a['account_name']}\" ({a['owner'] or 'nobody'}, {a['stage']},"
                              f" {money(a['arr_potential_usd'])})" for a in accts)
            out.append(self.row(
                MERGE, c, f"merge {', '.join(a['account_id'] for a in others)} into {survivor['account_id']}",
                f"{plural(len(accts), 'account')} for one company, {c['duplicate_accounts'][6:]}: "
                f"{money(c['value_usd'])} is counted {len(accts)} times and {plural(len(reqs), 'request')} split across them",
                f"same domain {c['domain']}: {names}", int(c["value_usd"] or 0), reqs))
        return out

    def owners(self) -> list[Row]:
        out = []
        for c in self.duplicates():
            owners = split_bar(c["owner"])
            if len(owners) < 2:
                continue
            reqs = self.reqs(c)
            askers = Counter(r["requested_by"] for r in reqs)
            asked = [o for o in owners if askers[o]]
            if len(asked) == 1:
                silent = " and ".join(o for o in owners if o not in asked)
                lean = f"{asked[0]} raised {plural(askers[asked[0]], 'request')} here, {silent} none"
            elif not asked:
                lean = "neither owner has asked for an intro here"
            else:
                lean = "both have asked (" + ", ".join(f"{o}: {askers[o]}" for o in asked) + ")"
            who_owns = "; ".join(f"{a['account_id']} -> {a['owner']}" for a in self.accts(c))
            out.append(self.row(
                OWNERS, c, f"pick one owner: {' or '.join(owners)}",
                f"two reps both own a {money(c['value_usd'])} {c['stage']} account",
                f"{who_owns}; {lean}", int(c["value_usd"] or 0), reqs))
        return out

    def reopen(self) -> list[Row]:
        out = []
        for c in self.companies:
            live = self.live(c)
            if c["stage"] != CLOSED_LOST or not live:
                continue
            paths = int(c["paths_available"] or 0)
            touch = self.last_touch(c)
            lean = (f"{plural(paths, 'path')} into the company, so reopening is possible" if paths
                    else "nobody in the network reaches them, so closing the requests loses nothing")
            out.append(self.row(
                REOPEN, c, "reopen the account or close the requests",
                f"{plural(len(live), 'live request')} worth {money(value(live))} against a {CLOSED_LOST} account: "
                "either the stage is wrong or the requests are",
                f"{c['crm_account_ids']} {CLOSED_LOST}, owner {c['owner'] or 'nobody'}, last touch "
                f"{touch.isoformat() if touch else 'never'}; requests from {self.requesters(live)}, "
                f"latest {live[-1]['request_date']}; {lean}",
                value(live), live))
        return out

    def stale(self) -> list[Row]:
        out = []
        for c in self.companies:
            live = self.live(c)
            touch = self.last_touch(c)
            if not live or not touch or c["stage"] == CLOSED_LOST:
                continue
            days = (self.today - touch).days
            if days < STALE_TOUCH_DAYS:
                continue
            out.append(self.row(
                STALE, c, f"log a touch or hand off ({c['owner'] or 'no owner'})",
                f"{plural(len(live), 'open request')} worth {money(value(live))} but the account has not moved in {days} days",
                f"{c['crm_account_ids']} last touched {touch.isoformat()} ({days} days ago), stage {c['stage']}; "
                f"requests from {self.requesters(live)}, latest {live[-1]['request_date']}",
                value(live), live))
        return out

    # -- exports --------------------------------------------------------------
    def review_rows(self) -> list[Row]:
        rows = [*self.create(), *self.merge(), *self.owners(), *self.reopen(), *self.stale()]
        return sorted(rows, key=lambda r: (r.rank, -r.value_at_stake_usd, r.company_name))

    def import_rows(self) -> list[dict]:
        out = []
        for c in sorted((c for c in self.companies if not c["crm_account_ids"]), key=lambda c: c["company_name"]):
            live = self.live(c)
            out.append({
                "account_name": c["company_name"],
                "domain": c["domain"],
                "owner": self.reqs(c)[0]["requested_by"],
                "stage": DEFAULT_STAGE,
                "source": SOURCE,
                "blocked_requests": len(live),
                "requested_value_usd": value(live),
            })
        return out


def counts(rows: list[Row]) -> list[str]:
    n = Counter(r.group for r in rows)
    return [f"{i}. {GROUP_TITLES[g]:<26} {n[g]:>3}  ({money(sum(r.value_at_stake_usd for r in rows if r.group == g))})"
            for i, g in enumerate(GROUPS, 1)]


def write_all(today: date | None = None) -> tuple[list[dict], list[Row]]:
    """crm_import.csv (account creation only) and crm_review.csv (every recommendation) -> analysis/crm/."""
    wb = Writeback(today or date.today())
    review = wb.review_rows()
    imports = wb.import_rows()
    CRM.mkdir(exist_ok=True)
    write_csv(IMPORT_OUT, IMPORT_COLUMNS, imports)
    write_csv(REVIEW_OUT, REVIEW_COLUMNS, [asdict(r) for r in review])
    print("\n".join(counts(review)))
    print(f"wrote {len(imports)} accounts to {IMPORT_OUT.name}, "
          f"{len(review)} recommendations to {REVIEW_OUT.name} in {CRM}/")
    return imports, review


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as-of", default=date.today().isoformat())
    args = ap.parse_args(argv)
    write_all(parse_date(args.as_of) or date.today())


if __name__ == "__main__":
    main(sys.argv[1:])
