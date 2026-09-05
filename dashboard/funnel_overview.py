"""Funnel overview: assign every intro request to exactly one dropoff bucket.

A request drops out at the first stage that fails, so the eight buckets partition
`intro_requests.csv` and their `deal_value_usd` sums partition the requested pipeline.
Unrouted requests are split using the golden company resolution (`golden/`), so the
split agrees with the company and supply cuts elsewhere in the dashboard.

    python3 -m dashboard.funnel_overview     # prints the table
"""
import csv
import os

from paths import DATASET, GOLDEN

DATA = str(DATASET)


def rows(name, base=DATA):
    with open(os.path.join(base, name), newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def paths_by_request():
    """request_id -> number of network paths to its resolved company, or None when unresolved."""
    paths = {c["company_id"]: int(c["paths_available"] or 0) for c in rows("golden_companies.csv", str(GOLDEN))}
    out = {}
    for g in rows("golden_requests.csv", str(GOLDEN)):
        cid = g["company_id"].strip()
        out[g["request_id"].strip()] = paths.get(cid) if cid else None
    return out


def dropoff_rows():
    """[(category, dropoff, requests, deal value usd)] — one bucket per request."""
    requests = rows("intro_requests.csv")
    outcomes = rows("intro_outcomes.csv")
    paths = paths_by_request()

    asked = {o["request_id"].strip(): o for o in outcomes}
    yes = lambda o, col: o[col].strip().upper() == "Y"

    buckets = [
        ("Data Entry", "Target not Identifiable", []),
        ("Never Routed", "No Path in Network", []),
        ("Never Routed", "Warm Path Existed, Never Routed", []),
        ("Routed", "Routed, No Response", []),
        ("Routed", "Responded, No Intro", []),
        ("Intro'ed", "Intro Sent, No Meeting", []),
        ("Intro'ed", "Meeting, No Opportunity", []),
        ("Intro'ed", "Opportunity Created", []),
    ]
    for r in requests:
        o = asked.get(r["request_id"].strip())
        if o is None:
            rid = r["request_id"].strip()
            if rid not in paths:
                raise KeyError(f"{rid} missing from golden/golden_requests.csv; run golden/build_golden.py")
            n_paths = paths[rid]
            i = 0 if n_paths is None else (2 if n_paths > 0 else 1)
        elif not yes(o, "responded"):
            i = 3
        elif not yes(o, "intro_sent"):
            i = 4
        elif not yes(o, "meeting_booked"):
            i = 5
        elif not yes(o, "opportunity_created"):
            i = 6
        else:
            i = 7
        buckets[i][2].append(r)

    return [(category, dropoff, len(rs), sum(float(r["deal_value_usd"] or 0) for r in rs))
            for category, dropoff, rs in buckets]


def ratios(rows_):
    """The two summary ratios under the table."""
    by_dropoff = {dropoff: (n, v) for _, dropoff, n, v in rows_}
    total = sum(n for _, _, n, _ in rows_)
    unrouted_identifiable = (by_dropoff["No Path in Network"][0]
                             + by_dropoff["Warm Path Existed, Never Routed"][0])
    intros = (by_dropoff["Intro Sent, No Meeting"][0] + by_dropoff["Meeting, No Opportunity"][0]
              + by_dropoff["Opportunity Created"][0])
    meetings = by_dropoff["Meeting, No Opportunity"][0] + by_dropoff["Opportunity Created"][0]
    return [("% Identifiable Unrouted Requests / Requests", unrouted_identifiable / total),
            ("% Intro to Meeting / Intros", meetings / intros)]


if __name__ == "__main__":
    data = dropoff_rows()
    total_n = sum(n for _, _, n, _ in data)
    total_v = sum(v for _, _, _, v in data)
    print(f"{'Category':<14}{'Funnel Dropoff':<34}{'#':>5}{'% Total':>9}{'Value':>9}{'% Total':>9}")
    for category, dropoff, n, v in data:
        print(f"{category:<14}{dropoff:<34}{n:>5}{n / total_n:>9.1%}${v / 1e6:>8.1f}{v / total_v:>9.1%}")
    print(f"{'Total':<48}{total_n:>5}{1:>9.1%}${total_v / 1e6:>8.1f}{1:>9.1%}")
    for label, value in ratios(data):
        print(f"{label:<48}{value:>9.1%}")
