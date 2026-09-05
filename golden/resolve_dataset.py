"""Feed the resolver from disk: the two files it is built from, then every
company string the dataset holds, then the opening message of each Slack thread.

    python3 golden/resolve_dataset.py                          # write the CSVs below
    python3 golden/resolve_dataset.py "Apex Logistics Group" "Thornbury"   # one-off lookups

The resolver itself (resolver.py) is a pure string -> ID function built from
crm_accounts.csv rows and the investor_network.csv fund column. This script is
the historical-import caller; a live Slack listener would call the same
Resolver with the same two inputs.

Writes:
  golden/company_ids.csv           one row per entity, CRM survivor / duplicates by domain
  golden/company_resolutions.csv   every distinct company string in dataset/ and where it came from
  golden/company_review_queue.csv  the subset a human has to decide
  golden/slack_resolutions.csv     one row per Slack thread
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from golden.resolver import Resolution, Resolver  # noqa: E402

DATASET = ROOT / "dataset"
OUT = ROOT / "golden"

ENTITIES_OUT = OUT / "company_ids.csv"
RESOLUTIONS_OUT = OUT / "company_resolutions.csv"
REVIEW_OUT = OUT / "company_review_queue.csv"
SLACK_OUT = OUT / "slack_resolutions.csv"


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\r\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_resolver() -> Resolver:
    """The two inputs the resolver is built from: CRM accounts and the fund column."""
    funds = [r["fund"] for r in read_csv(DATASET / "investor_network.csv")]
    res = Resolver(read_csv(DATASET / "crm_accounts.csv"), funds)
    res.learn_spellings(sorted(company_strings()))  # readable names for all-caps CRM rows
    return res


def company_strings() -> dict[str, set[str]]:
    """Every distinct company string in dataset/, with the files it appears in."""
    seen: dict[str, set[str]] = defaultdict(set)
    for r in read_csv(DATASET / "crm_accounts.csv"):
        seen[r["account_name"]].add("crm_accounts")
    for r in read_csv(DATASET / "intro_requests.csv"):
        if r["target_company_raw"].strip():
            seen[r["target_company_raw"].strip()].add("intro_requests")
    for r in read_csv(DATASET / "investor_network.csv"):
        for col in ("fund", "portfolio_company", "prior_employer"):
            if r[col].strip():
                seen[r[col].strip()].add(f"investor_network.{col}")
    for p in sorted(DATASET.glob("connections_*.csv")):
        for r in read_csv(p):
            if r["company"].strip():
                seen[r["company"].strip()].add(p.stem)
    return seen


# ---------------------------------------------------------------------------
# slack threads: the opening message names the target company (or doesn't)
# ---------------------------------------------------------------------------
_C = r"(?P<c>[A-Z][\w&'-]*(?: [A-Z&][\w&'-]*)*)"
_SLACK_PATTERNS = [re.compile(p) for p in (
    r"email domain is (?P<d>[a-z0-9.-]+\.[a-z]{2,})",
    r"account I actually need is " + _C + r"\s*\(",
    r"^" + _C + r" is the target\.",
    r"^we need " + _C + r"\.",
    r"^asking again: " + _C + r"\.",
    r"^long shot — " + _C + r"\.",
    r"^trying to reach .+? at " + _C + r"(?: —|\.)",
    r"^(?:any connections|path) into " + _C + r"\?",
    r"^(?:who do we know|does anyone know anyone|who knows someone|need an intro) at " + _C + r"(?:\?| —)",
    r"^need help getting to " + _C + r"\.",
)]


def company_from_slack(text: str) -> tuple[str, str]:
    """-> (company string, domain hint); both empty when the message names only a person."""
    for pat in _SLACK_PATTERNS:
        m = pat.search(text)
        if m:
            d = m.groupdict()
            return d.get("c") or "", d.get("d") or ""
    return "", ""


def resolve_slack_threads(res: Resolver) -> list[dict]:
    rows = []
    with open(DATASET / "slack_threads.jsonl", encoding="utf-8") as f:
        for line in f:
            t = json.loads(line)
            text = t["messages"][0]["text"]
            written, hint = company_from_slack(text)
            if not written and not hint:
                r = Resolution("", None, "no-company-named", 0.0)
            else:
                r = res.resolve(written, hint)
            rows.append({"request_id": t["request_id"], "opening_message": text,
                         "extracted": written or hint, **r.row()})
    return rows


SLACK_COLUMNS = ["request_id", "company_id", "company_name", "kind", "method", "confidence",
                 "needs_review", "candidates", "extracted", "opening_message"]
RESOLUTION_COLUMNS = ["company_string", "sources", "company_id", "company_name", "kind",
                      "method", "confidence", "needs_review", "candidates"]
ENTITY_COLUMNS = ["company_id", "kind", "company_name", "domain", "also_known_as",
                  "crm_account_ids", "survivor_account_id", "duplicate_account_ids"]


def main(argv: list[str]) -> None:
    res = load_resolver()
    if argv:
        for s in argv:
            print(json.dumps(res.resolve(s).row(), ensure_ascii=False))
        return

    write_csv(ENTITIES_OUT, ENTITY_COLUMNS, res.entity_rows())
    rows = []
    for s, sources in sorted(company_strings().items(), key=lambda kv: kv[0].lower()):
        rows.append({**res.resolve(s).row(), "sources": " | ".join(sorted(sources))})
    write_csv(RESOLUTIONS_OUT, RESOLUTION_COLUMNS, rows)
    review = [r for r in rows if r["needs_review"] == "yes"]
    write_csv(REVIEW_OUT, RESOLUTION_COLUMNS, review)

    dupes = [r for r in res.crm_rows() if r["survivor"] == "no"]
    by_method = defaultdict(int)
    for r in rows:
        by_method[r["method"]] += 1
    print(f"company_ids.csv            {len(res.entities)} entities "
          f"({sum(e.kind == 'company' for e in res.entities)} companies, "
          f"{sum(e.kind == 'fund' for e in res.entities)} funds); "
          f"{len(dupes)} CRM rows are non-survivor duplicates by domain")
    print(f"company_resolutions.csv    {len(rows)} distinct strings: "
          + ", ".join(f"{m} {n}" for m, n in sorted(by_method.items(), key=lambda kv: -kv[1])))
    print(f"company_review_queue.csv   {len(review)} for a human")
    for r in review:
        print(f"  {r['company_string']!r:32} {r['method']:17} {r['candidates'] or '-'}")

    slack = resolve_slack_threads(res)
    write_csv(SLACK_OUT, SLACK_COLUMNS, slack)
    exact = sum(r["method"] in ("name-exact", "domain") for r in slack)
    confident = sum(r["needs_review"] == "no" for r in slack) - exact
    escalated = [r for r in slack if r["needs_review"] == "yes"]
    print(f"slack_resolutions.csv      {len(slack)} threads: {exact} exact string/domain, "
          f"{confident} joined with confidence < 1.00, {len(escalated)} escalated")
    slack_methods = defaultdict(int)
    for r in slack:
        slack_methods[r["method"]] += 1
    for m, n in sorted(slack_methods.items(), key=lambda kv: -kv[1]):
        print(f"  {m:18} {n}")


if __name__ == "__main__":
    # under build.py (runpy) argv belongs to build.py, not to us
    main(sys.argv[1:] if Path(sys.argv[0]).name == "resolve_dataset.py" else [])
