"""Funnel overview: assign every intro request to exactly one dropoff bucket.

A request drops out at the first stage that fails, so the eight buckets partition
`intro_requests.csv` and their `deal_value_usd` sums partition the requested pipeline.

    python3 -m dashboard.funnel_overview     # prints the table
"""
import csv
import glob
import os
import re

from paths import DATASET

DATA = str(DATASET)
DOMAIN = re.compile(r"\b([a-z0-9-]+)\.(?:com|net|io|ai|co\.uk)\b", re.I)


def rows(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def norm(v):
    return re.sub(r"[^a-z0-9]", "", v.lower())


def company_index():
    """Known company names, plus the connection companies and a domain stem -> name map."""
    connection_companies = set()
    for path in sorted(glob.glob(os.path.join(DATA, "connections_*.csv"))):
        with open(path, newline="", encoding="utf-8-sig") as f:
            connection_companies |= {r["company"].strip() for r in csv.DictReader(f)}
    crm = rows("crm_accounts.csv")
    names = {c["account_name"].strip() for c in crm} | connection_companies
    names |= {r["target_company_raw"].strip() for r in rows("intro_requests.csv") if r["target_company_raw"].strip()}
    by_stem = {norm(n): n for n in names}
    for c in crm:
        by_stem.setdefault(norm(c["domain"].split(".")[0]), c["account_name"].strip())
    return names, connection_companies, by_stem


def resolve_target(request, names_by_length, by_stem):
    """The company a request is aimed at, or None when no company can be recovered at all."""
    stated = request["target_company_raw"].strip()
    if stated:
        return stated
    ask = request["raw_ask"]
    lowered = ask.lower()
    for name in names_by_length:
        if name.lower() in lowered:
            return name
    for m in DOMAIN.finditer(ask):
        if norm(m.group(1)) in by_stem:
            return by_stem[norm(m.group(1))]
    return None


def dropoff_rows():
    """[(category, dropoff, requests, deal value usd)] — one bucket per request."""
    requests = rows("intro_requests.csv")
    outcomes = rows("intro_outcomes.csv")
    names, connection_companies, by_stem = company_index()
    names_by_length = sorted(names, key=len, reverse=True)

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
            target = resolve_target(r, names_by_length, by_stem)
            i = 0 if target is None else (2 if target in connection_companies else 1)
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
