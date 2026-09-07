"""Join-rate matrix between the CSVs in dataset/.

For every plausible entity link, reports the directional match rate under three
normalization tiers and lists the top unmatched values on each side.
Run from the repo root: python3 -m analysis.joins.join_rates
"""

import csv
import os
import re
from collections import Counter

from paths import DATASET, JOINS

DATA = str(DATASET)
OUT = str(JOINS / "join_rates.md")
TOP_N = 20

LEGAL_SUFFIXES = {
    "inc", "incorporated", "llc", "lp", "llp", "ltd", "limited", "corp", "corporation", "co",
    "company", "plc", "gmbh", "ag", "sa", "nv", "bv", "group", "holding", "holdings",
}


def rows(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


CONNECTION_FILES = sorted(f for f in os.listdir(DATA) if f.startswith("connections_") and f.endswith(".csv"))


def column(files, col):
    """All non-empty values of `col` across one or more CSVs, with duplicates kept."""
    if isinstance(files, str):
        files = [files]
    return [r[col].strip() for f in files for r in rows(f) if r.get(col, "").strip()]


# ---- normalization tiers ---------------------------------------------------
def tier1(v):
    """Exact: the value as written."""
    return v


def tier2(v):
    """Lowercase, drop punctuation and whitespace."""
    return re.sub(r"[^a-z0-9]+", "", v.lower())


def tier3(v):
    """Tier 2 plus trailing legal / generic corporate suffixes removed."""
    words = [w for w in re.split(r"[^a-z0-9]+", v.lower()) if w]
    while words and words[-1] in LEGAL_SUFFIXES:
        words.pop()
    return "".join(words)


TIERS = [("exact", tier1), ("+ lowercase, no punctuation", tier2), ("+ legal suffixes stripped", tier3)]


def strip_domain(v):
    """thornburyfinancial.com -> Thornbury Financial-ish key: host minus www and TLD."""
    host = re.sub(r"^https?://", "", v.strip().lower()).split("/")[0]
    host = re.sub(r"^www\.", "", host)
    labels = host.split(".")
    while len(labels) > 1 and labels[-1] in {"com", "co", "uk", "io", "net", "org", "ai", "de", "fr", "us"}:
        labels.pop()
    return ".".join(labels)


IDENTITY = ("as-is", lambda v: v)
DOMAIN = ("host minus www/TLD", strip_domain)


def analyse(label, left, right, left_prep=IDENTITY, right_prep=IDENTITY):
    lvals, rvals = left[1], right[1]
    lset_raw, rset_raw = set(lvals), set(rvals)
    result = {
        "label": label,
        "left_name": left[0],
        "right_name": right[0],
        "left_rows": len(lvals),
        "right_rows": len(rvals),
        "left_distinct": len(lset_raw),
        "right_distinct": len(rset_raw),
        "left_prep": left_prep[0],
        "right_prep": right_prep[0],
        "left_counts": Counter(lvals),
        "right_counts": Counter(rvals),
        "tiers": [],
    }
    for tname, fn in TIERS:
        lkeys = {v: fn(left_prep[1](v)) for v in lset_raw}
        rkeys = {v: fn(right_prep[1](v)) for v in rset_raw}
        rindex = set(rkeys.values()) - {""}
        lindex = set(lkeys.values()) - {""}
        l_hit = {v for v, k in lkeys.items() if k in rindex}
        r_hit = {v for v, k in rkeys.items() if k in lindex}
        l_rows_hit = sum(1 for v in lvals if lkeys[v] in rindex)
        r_rows_hit = sum(1 for v in rvals if rkeys[v] in lindex)
        result["tiers"].append(
            {
                "tier": tname,
                "l_distinct_rate": len(l_hit) / max(1, len(lset_raw)),
                "r_distinct_rate": len(r_hit) / max(1, len(rset_raw)),
                "l_row_rate": l_rows_hit / max(1, len(lvals)),
                "r_row_rate": r_rows_hit / max(1, len(rvals)),
                "l_unmatched": lset_raw - l_hit,
                "r_unmatched": rset_raw - r_hit,
            }
        )
    return result


PAIRS = [
    (
        "intro_requests.target_company_raw -> crm_accounts.account_name",
        ("intro_requests.target_company_raw", column("intro_requests.csv", "target_company_raw")),
        ("crm_accounts.account_name", column("crm_accounts.csv", "account_name")),
        IDENTITY,
        IDENTITY,
    ),
    (
        "intro_requests.target_company_raw -> crm_accounts.domain",
        ("intro_requests.target_company_raw", column("intro_requests.csv", "target_company_raw")),
        ("crm_accounts.domain", column("crm_accounts.csv", "domain")),
        IDENTITY,
        DOMAIN,
    ),
    (
        "investor_network.portfolio_company -> crm_accounts.account_name",
        ("investor_network.portfolio_company", column("investor_network.csv", "portfolio_company")),
        ("crm_accounts.account_name", column("crm_accounts.csv", "account_name")),
        IDENTITY,
        IDENTITY,
    ),
    (
        "investor_network.prior_employer -> crm_accounts.account_name",
        ("investor_network.prior_employer", column("investor_network.csv", "prior_employer")),
        ("crm_accounts.account_name", column("crm_accounts.csv", "account_name")),
        IDENTITY,
        IDENTITY,
    ),
    (
        "connections_*.company -> crm_accounts.account_name",
        ("connections_*.company", column(CONNECTION_FILES, "company")),
        ("crm_accounts.account_name", column("crm_accounts.csv", "account_name")),
        IDENTITY,
        IDENTITY,
    ),
    (
        "intro_outcomes.request_id -> intro_requests.request_id",
        ("intro_outcomes.request_id", column("intro_outcomes.csv", "request_id")),
        ("intro_requests.request_id", column("intro_requests.csv", "request_id")),
        IDENTITY,
        IDENTITY,
    ),
    (
        "intro_outcomes.connector_asked -> connector_roster.name",
        ("intro_outcomes.connector_asked", column("intro_outcomes.csv", "connector_asked")),
        ("connector_roster.name", column("connector_roster.csv", "name")),
        IDENTITY,
        IDENTITY,
    ),
    # additional plausible entity links
    (
        "connections_*.company -> intro_requests.target_company_raw",
        ("connections_*.company", column(CONNECTION_FILES, "company")),
        ("intro_requests.target_company_raw", column("intro_requests.csv", "target_company_raw")),
        IDENTITY,
        IDENTITY,
    ),
    (
        "investor_network.portfolio_company -> connections_*.company",
        ("investor_network.portfolio_company", column("investor_network.csv", "portfolio_company")),
        ("connections_*.company", column(CONNECTION_FILES, "company")),
        IDENTITY,
        IDENTITY,
    ),
    (
        "investor_network.person -> connector_roster.name",
        ("investor_network.person", column("investor_network.csv", "person")),
        ("connector_roster.name", column("connector_roster.csv", "name")),
        IDENTITY,
        IDENTITY,
    ),
    (
        "intro_requests.requested_by -> crm_accounts.owner",
        ("intro_requests.requested_by", column("intro_requests.csv", "requested_by")),
        ("crm_accounts.owner", column("crm_accounts.csv", "owner")),
        IDENTITY,
        IDENTITY,
    ),
    (
        "intro_requests.target_person_raw -> connections_*.name",
        ("intro_requests.target_person_raw", column("intro_requests.csv", "target_person_raw")),
        ("connections_*.name", column(CONNECTION_FILES, "name")),
        IDENTITY,
        IDENTITY,
    ),
    (
        "connector_roster.connections_file -> connections files on disk",
        ("connector_roster.connections_file", column("connector_roster.csv", "connections_file")),
        ("dataset/*.csv filenames", CONNECTION_FILES),
        IDENTITY,
        IDENTITY,
    ),
]


def pct(x):
    return f"{x * 100:.1f}%"


def main():
    results = [analyse(*p) for p in PAIRS]
    out = []
    w = out.append
    w("# Join rates across `dataset/`\n")
    w("Every link is measured in both directions under three cumulative normalization tiers:\n")
    w("1. **exact** — byte-for-byte equality of the trimmed value")
    w("2. **+ lowercase, no punctuation** — lowercased, all non-alphanumeric characters (including "
      "spaces) removed")
    w("3. **+ legal suffixes stripped** — tier 2, then trailing "
      f"`{'`, `'.join(sorted(LEGAL_SUFFIXES))}` removed\n")
    w("`domain` values are pre-reduced to the host minus `www.` and the TLD before the tiers apply "
      "(`ellerbysemi.com` -> `ellerbysemi`), otherwise a name-to-domain join is 0% by construction.\n")
    w("**Match rate (distinct)** = share of distinct values on that side that find at least one "
      "counterpart on the other side. **(rows)** = the same measured over every row, so it reflects "
      "how much of the actual data joins.\n")

    regressions = []
    for r in results:
        t = r["tiers"]
        for side, key in (("left", "l_distinct_rate"), ("right", "r_distinct_rate")):
            if t[2][key] < t[1][key]:
                regressions.append(
                    f"`{r['label']}` ({side} side): {pct(t[1][key])} -> {pct(t[2][key])} — stripping a "
                    "suffix on one side removes the token the other side still carries inside a "
                    "single unsegmented string (e.g. `Apex Holdings` -> `apex` no longer meets "
                    "`apexlogisticsgroup.co.uk`)"
                )
    if regressions:
        w("Normalization is not strictly monotonic — suffix stripping loses these matches:\n")
        for line in regressions:
            w(f"- {line}")
        w("")

    w("## Summary\n")
    w("| Link | Direction | Exact | +lower/punct | +legal suffix |")
    w("| --- | --- | ---: | ---: | ---: |")
    for r in results:
        t = r["tiers"]
        w(f"| {r['label']} | -> (left side matched) | {pct(t[0]['l_distinct_rate'])} | "
          f"{pct(t[1]['l_distinct_rate'])} | {pct(t[2]['l_distinct_rate'])} |")
        w(f"| | <- (right side matched) | {pct(t[0]['r_distinct_rate'])} | "
          f"{pct(t[1]['r_distinct_rate'])} | {pct(t[2]['r_distinct_rate'])} |")
    w("")

    for r in results:
        w(f"## {r['label']}\n")
        w(f"- left `{r['left_name']}`: {r['left_rows']} rows, {r['left_distinct']} distinct"
          + (f" (pre-reduced: {r['left_prep']})" if r["left_prep"] != "as-is" else ""))
        w(f"- right `{r['right_name']}`: {r['right_rows']} rows, {r['right_distinct']} distinct"
          + (f" (pre-reduced: {r['right_prep']})" if r["right_prep"] != "as-is" else ""))
        w("")
        w("| Tier | Left matched (distinct) | Left matched (rows) | Right matched (distinct) | Right matched (rows) |")
        w("| --- | ---: | ---: | ---: | ---: |")
        for t in r["tiers"]:
            w(f"| {t['tier']} | {pct(t['l_distinct_rate'])} | {pct(t['l_row_rate'])} | "
              f"{pct(t['r_distinct_rate'])} | {pct(t['r_row_rate'])} |")
        w("")

        final = r["tiers"][-1]
        for side, key, name, counts in (
            ("left", "l_unmatched", r["left_name"], r["left_counts"]),
            ("right", "r_unmatched", r["right_name"], r["right_counts"]),
        ):
            vals = sorted(final[key], key=lambda v: (-counts[v], v))
            w(f"Top {min(TOP_N, len(vals))} unmatched on the {side} by row count (`{name}`, after all "
              f"three tiers) — {len(vals)} unmatched distinct value(s):\n")
            if not vals:
                w("_none_\n")
                continue
            for v in vals[:TOP_N]:
                w(f"- `{v}` ({counts[v]} row{'s' if counts[v] != 1 else ''})")
            w("")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print(f"wrote {OUT}: {len(results)} links")


if __name__ == "__main__":
    main()
