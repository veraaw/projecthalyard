"""Build the resolver from its two inputs and resolve strings from argv or stdin.

    python3 golden/resolve_cli.py "Apex Logistics Group" "Thornbury"
    python3 golden/resolve_cli.py < strings.txt        # one company string per line

Prints a table (company_string, company_id, company_name, method, confidence,
needs_review, candidates). This is the only file that knows where the CSVs are;
resolver.py itself has no file paths.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from golden.resolver import Resolver  # noqa: E402

DATASET = ROOT / "dataset"


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_resolver() -> Resolver:
    funds = [r["fund"] for r in read_csv(DATASET / "investor_network.csv")]
    return Resolver(read_csv(DATASET / "crm_accounts.csv"), funds)


COLUMNS = ["company_string", "company_id", "company_name", "method", "confidence", "needs_review", "candidates"]


def main(argv: list[str]) -> None:
    strings = argv or [line.rstrip("\n") for line in sys.stdin if line.strip()]
    res = load_resolver()
    w = csv.DictWriter(sys.stdout, fieldnames=COLUMNS, extrasaction="ignore", delimiter="\t")
    w.writeheader()
    for s in strings:
        w.writerow(res.resolve(s).row())


if __name__ == "__main__":
    main(sys.argv[1:])
