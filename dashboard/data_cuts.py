"""Additional dashboard data cuts, computed from `dataset/` and `golden/`.

Each `*_cut()` function returns plain data (dicts/lists of tuples) for
`dashboard/build_dashboard.py` to render; nothing here touches HTML.

    python3 -m dashboard.data_cuts      # prints every cut as text
"""
import csv
import glob
import json
import os
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

from paths import DATASET, GOLDEN as GOLDEN_DIR, JOINS

DATA = str(DATASET)
GOLDEN = str(GOLDEN_DIR)

DUP_CHECK = re.compile(r"same as|already (?:lose|lost|ask|asked|have)|did we not already|didn'?t we|last month|duplicate", re.I)


def _rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def dataset(name):
    return _rows(os.path.join(DATA, name))


def golden(name):
    return _rows(os.path.join(GOLDEN, name))


def yes(row, col):
    return row[col].strip().upper() == "Y"


def money(v):
    return float(v) if str(v).strip() else 0.0


def d(v):
    return date.fromisoformat(v.strip()) if v.strip() else None


def load():
    """Everything the cuts need, joined on request_id / company_id."""
    requests = dataset("intro_requests.csv")
    outcomes = dataset("intro_outcomes.csv")
    with open(os.path.join(DATA, "slack_threads.jsonl"), encoding="utf-8") as f:
        threads = [json.loads(line) for line in f if line.strip()]
    return {
        "requests": requests,
        "outcomes": outcomes,
        "outcome_by_request": {o["request_id"].strip(): o for o in outcomes},
        "crm": dataset("crm_accounts.csv"),
        "roster": dataset("connector_roster.csv"),
        "investors": dataset("investor_network.csv"),
        "connections": [r for p in sorted(glob.glob(os.path.join(DATA, "connections_*.csv"))) for r in _rows(p)],
        "threads": threads,
        "golden_requests": {r["request_id"]: r for r in golden("golden_requests.csv")},
        "golden_companies": {c["company_id"]: c for c in golden("golden_companies.csv")},
        "supply": golden("supply_reach.csv"),
    }


# --------------------------------------------------------------------------- 1. scoped joins
JOIN_NOTES = {
    "intro_outcomes.request_id -> intro_requests.request_id":
        "Every outcome row points at a real request — the funnel can be trusted in that direction.",
    "intro_requests.requested_by -> crm_accounts.owner":
        "Requesters and account owners are the same eight people, spelled identically in both files.",
    "connector_roster.connections_file -> connections files on disk":
        "Roster and export files line up one-to-one; no orphan or missing connection export.",
    "intro_outcomes.connector_asked -> connector_roster.name":
        "Five people were asked who are not on the roster, so capacity and focus-area rules cannot be applied to them.",
    "intro_requests.target_person_raw -> connections_*.name":
        "Not one requested individual exists in any connection export — the person named in an ask is unverifiable.",
    "intro_requests.target_company_raw -> crm_accounts.account_name":
        "Company names are free text; roughly a third of request rows need normalization or aliasing to reach the CRM.",
    "connections_*.company -> intro_requests.target_company_raw":
        "Fewer than 60% of the companies in the network are ever requested, and vice versa — supply and demand barely overlap.",
    "investor_network.person -> connector_roster.name":
        "The investor network is almost entirely people who are not connectors, so those paths are unmanaged.",
}


def join_summary_cut(_):
    """(link, direction, tier-3 rate, note) parsed out of analysis/joins/join_rates.md."""
    with open(JOINS / "join_rates.md", encoding="utf-8") as f:
        text = f.read()
    body = text.split("## Summary", 1)[1]
    out, link = [], ""
    for line in body.splitlines():
        if not line.startswith("|"):
            if out:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5 or set("".join(cells)) <= set("-: ") or cells[0] == "Link":
            continue
        link = cells[0] or link
        out.append((link, cells[1], cells[-1]))
    per_link = defaultdict(dict)
    for link, direction, rate in out:
        per_link[link]["left" if direction.startswith("->") else "right"] = float(rate.rstrip("%"))
    joins = [(link, r.get("left", 0.0), r.get("right", 0.0), JOIN_NOTES.get(link, "")) for link, r in per_link.items()]
    perfect = [j for j in joins if j[1] == 100.0 and j[2] == 100.0]
    concerning = sorted((j for j in joins if j not in perfect), key=lambda j: min(j[1], j[2]))
    return {"joins": joins, "perfect": perfect, "concerning": concerning}


# --------------------------------------------------------------------------- 2/3. accounts
# a request with no company_id is grouped by why the resolver gave up, never by
# the name that was written (a refused bare name such as Thornbury is not a company)
UNRESOLVABLE_BUCKETS = {
    "unresolved": ("unresolvable:no-company", "(no company named)"),
    "empty": ("unresolvable:no-company", "(no company named)"),
    "fund-collision": ("unresolvable:fund-or-opco", "(fund or operating company named)"),
}


def company_key(g):
    """(row key, display name, unresolvable?) for a golden request row."""
    if g["company_id"]:
        return g["company_id"], "", False
    method = g["resolved_by"].split(":")[-1]
    key, name = UNRESOLVABLE_BUCKETS.get(method, ("unresolvable:other", "(unidentifiable)"))
    return key, name, True


def company_rows(data, since=None):
    """One row per resolved company plus one per unresolvable bucket:
    demand, routing and outcome counts. `since` (YYYY-MM-DD) keeps only
    requests dated on or after it, the same rolling window as the funnel."""
    by_company = {}
    for r in data["requests"]:
        g = data["golden_requests"][r["request_id"]]
        if since and g["request_date"].strip()[:10] < since:
            continue
        key, bucket_name, unresolvable = company_key(g)
        cid = g["company_id"]
        gc = data["golden_companies"].get(cid, {})
        b = by_company.setdefault(key, {
            "company_id": cid,
            "unresolvable": unresolvable,
            "name": bucket_name or gc.get("company_name") or g["company_as_written"],
            "industry": gc.get("industry", ""),
            "in_crm": bool(gc.get("crm_account_ids")),
            "owner": gc.get("owner", ""),
            "stage": gc.get("stage", ""),
            "crm_value": money(gc.get("value_usd", 0)) if gc.get("crm_account_ids") else 0.0,
            "deal_value": 0.0, "requests": 0, "routed": 0, "requesters": set(), "connectors": set(),
            "responded": 0, "intros": 0, "meetings": 0, "opps": 0, "paths": int(gc.get("paths_available") or 0),
        })
        b["requests"] += 1
        b["requesters"].add(r["requested_by"].strip())
        b["deal_value"] = max(b["deal_value"], money(r["deal_value_usd"]))
        o = data["outcome_by_request"].get(r["request_id"])
        if o:
            b["routed"] += 1
            b["connectors"].add(o["connector_asked"].strip())
            b["responded"] += yes(o, "responded")
            b["intros"] += yes(o, "intro_sent")
            b["meetings"] += yes(o, "meeting_booked")
            b["opps"] += yes(o, "opportunity_created")
    for b in by_company.values():
        b["value"] = b["crm_value"] or b["deal_value"]
        b["value_source"] = "CRM" if b["crm_value"] else "deal"
    return list(by_company.values())


def account_demand_cut(data, since=None):
    """Companies ranked by number of asks, split routed vs never routed.
    `companies` holds the resolved companies; `unresolvable` the buckets of
    asks that never got a company_id. `since` restricts to requests dated on
    or after it (the last-12-months view); `asks` is the total in the window."""
    rows = sorted(company_rows(data, since), key=lambda b: (-b["requests"], b["name"]))
    companies = [b for b in rows if not b["unresolvable"]]
    asks = sum(b["requests"] for b in rows)
    return {"companies": companies,
            "unresolvable": [b for b in rows if b["unresolvable"]],
            "asks": asks, "since": since,
            "singletons": sum(1 for b in companies if b["requests"] == 1),
            "repeat_share": (sum(b["requests"] for b in companies if b["requests"] > 1) / asks) if asks else 0.0}


def top_accounts_cut(data, n=20):
    """Top accounts by value (CRM ARR potential first, latest deal value as fallback)."""
    internal = {r["name"].strip() for r in data["roster"] if r["type"] == "Internal"}
    rows = sorted((b for b in company_rows(data) if not b["unresolvable"]),
                  key=lambda b: (-b["value"], b["name"]))[:n]
    for b in rows:
        b["internal_connectors"] = sorted(c for c in b["connectors"] if c in internal)
        b["outside_connectors"] = sorted(c for c in b["connectors"] if c not in internal)
    return {"companies": rows}


# --------------------------------------------------------------------------- 4. connectors
def connector_cut(data):
    """Per-roster-connector funnel, capacity, focus-area hit rate and roster note."""
    focus = {r["name"].strip(): {f.strip() for f in r["focus_areas"].split(";") if f.strip()} for r in data["roster"]}
    industry_of = {cid: c["industry"] for cid, c in data["golden_companies"].items()}
    stats = {}
    for r in data["roster"]:
        stats[r["name"].strip()] = {
            "name": r["name"].strip(), "role": r["role"], "type": r["type"], "notes": r["notes"],
            "focus_areas": r["focus_areas"], "capacity": int(r["stated_monthly_capacity"] or 0),
            "asked": 0, "responded": 0, "intros": 0, "meetings": 0, "opps": 0,
            "value": 0.0, "opp_value": 0.0, "in_focus": 0, "in_focus_intros": 0, "off_focus_intros": 0,
        }
    request_by_id = {r["request_id"]: r for r in data["requests"]}
    off_roster = Counter()
    for o in data["outcomes"]:
        name = o["connector_asked"].strip()
        if name not in stats:
            off_roster[name] += 1
            continue
        s = stats[name]
        s["asked"] += 1
        s["responded"] += yes(o, "responded")
        s["intros"] += yes(o, "intro_sent")
        s["meetings"] += yes(o, "meeting_booked")
        s["opps"] += yes(o, "opportunity_created")
        s["value"] += money(request_by_id[o["request_id"]]["deal_value_usd"])
        s["opp_value"] += money(o["opportunity_value_usd"])
        cid = data["golden_requests"][o["request_id"]]["company_id"]
        if industry_of.get(cid, "") in focus[name]:
            s["in_focus"] += 1
            s["in_focus_intros"] += yes(o, "intro_sent")
        else:
            s["off_focus_intros"] += yes(o, "intro_sent")
    rows = sorted(stats.values(), key=lambda s: -s["asked"])
    asked = sum(s["asked"] for s in rows)
    in_focus = sum(s["in_focus"] for s in rows)
    return {"connectors": rows, "off_roster": off_roster.most_common(),
            "asked": asked, "in_focus": in_focus,
            "in_focus_intro_rate": sum(s["in_focus_intros"] for s in rows) / in_focus if in_focus else 0,
            "off_focus_intro_rate": sum(s["off_focus_intros"] for s in rows) / (asked - in_focus) if asked > in_focus else 0,
            "months": len({r["request_date"][:7] for r in data["requests"]})}


# --------------------------------------------------------------------------- 5. target person provenance
def target_person_cut(data):
    """Where — if anywhere — the individual named in `target_person_raw` shows up."""
    people = [r["target_person_raw"].strip() for r in data["requests"] if r["target_person_raw"].strip()]
    distinct = set(people)
    sources = {
        "connections_*.name (5,075 contacts)": {c["name"].strip() for c in data["connections"]},
        "investor_network.person": {i["person"].strip() for i in data["investors"]},
        "connector_roster.name": {r["name"].strip() for r in data["roster"]},
        "crm_accounts.owner": {c["owner"].strip() for c in data["crm"]},
        "intro_outcomes.connector_asked": {o["connector_asked"].strip() for o in data["outcomes"]},
        "slack_threads.jsonl (message authors)": {m["user"].strip() for t in data["threads"] for m in t["messages"]},
    }
    hits = [(label, sum(1 for p in distinct if p in names)) for label, names in sources.items()]
    thread_by_request = {t["request_id"]: t for t in data["threads"]}
    in_thread = sum(1 for r in data["requests"]
                    if r["target_person_raw"].strip()
                    and any(r["target_person_raw"].strip() in m["text"]
                            for m in thread_by_request.get(r["request_id"], {"messages": []})["messages"]))
    surnames = {tok for c in data["connections"] for tok in re.split(r"[\s-]+", c["name"].strip())[1:]}
    recombined = sum(1 for p in distinct if set(re.split(r"[\s-]+", p)[1:]) <= surnames)
    titles_at_company = 0
    contacts_by_company = defaultdict(list)
    for c in data["connections"]:
        contacts_by_company[c["company"].strip()].append(c)
    for r in data["requests"]:
        target = r["target_company_raw"].strip()
        title = r["target_title_raw"].strip()
        if target and title and any(c["title"].strip() == title for c in contacts_by_company.get(target, [])):
            titles_at_company += 1
    return {"named": len(people), "requests": len(data["requests"]), "distinct": len(distinct),
            "hits": hits, "in_own_thread": in_thread, "recombined": recombined,
            "title_reachable": titles_at_company,
            "blank": len(data["requests"]) - len(people)}


# --------------------------------------------------------------------------- 6. routing latency & completion
def routing_time_cut(data):
    """Days from request to ask/intro, completion rate, and the monthly trend."""
    to_ask, to_intro = [], []
    monthly = defaultdict(lambda: {"requests": 0, "asked": 0, "intros": 0, "to_ask": []})
    weekly = defaultdict(lambda: {"requests": 0, "asked": 0, "intros": 0, "to_ask": []})
    for r in data["requests"]:
        requested = d(r["request_date"])
        buckets = [monthly[requested.strftime("%Y-%m")], weekly[requested - timedelta(days=requested.weekday())]]
        for b in buckets:
            b["requests"] += 1
        o = data["outcome_by_request"].get(r["request_id"])
        if not o:
            continue
        asked, intro = d(o["asked_date"]), d(o["intro_date"])
        for b in buckets:
            b["asked"] += 1
            b["intros"] += yes(o, "intro_sent")
        if asked:
            to_ask.append((asked - requested).days)
            for b in buckets:
                b["to_ask"].append((asked - requested).days)
        if intro and yes(o, "intro_sent"):
            to_intro.append((intro - requested).days)

    def series(bucket):
        return [(k, v["requests"], v["asked"], v["intros"],
                 statistics.mean(v["to_ask"]) if v["to_ask"] else None)
                for k, v in sorted(bucket.items())]

    intros = sum(1 for o in data["outcomes"] if yes(o, "intro_sent"))
    return {"to_ask": to_ask, "to_intro": to_intro,
            "mean_to_ask": statistics.mean(to_ask), "median_to_ask": statistics.median(to_ask),
            "mean_to_intro": statistics.mean(to_intro), "median_to_intro": statistics.median(to_intro),
            "completion_rate": intros / len(data["requests"]),
            "completion_rate_routed": intros / len(data["outcomes"]),
            "monthly": series(monthly), "weekly": series(weekly)}


# --------------------------------------------------------------------------- 7. slack overview
def slack_cut(data):
    """Message volume plus the duplicate-checking replies."""
    threads = data["threads"]
    replies = [(t["request_id"], m) for t in threads for m in t["messages"][1:]]
    dups = [(rid, m) for rid, m in replies if DUP_CHECK.search(m["text"])]
    dup_threads = {rid for rid, _ in dups}
    resolved = 0
    for rid in dup_threads:
        o = data["outcome_by_request"].get(rid)
        resolved += bool(o) and yes(o, "intro_sent")
    return {"threads": len(threads), "messages": sum(len(t["messages"]) for t in threads),
            "replies": len(replies), "dups": len(dups), "dup_threads": len(dup_threads),
            "dup_phrases": Counter(m["text"] for _, m in dups).most_common(),
            "dup_threads_with_intro": resolved,
            "no_reply": sum(1 for t in threads if len(t["messages"]) == 1)}


# --------------------------------------------------------------------------- 8. flag / status noise
def flag_noise_cut(data):
    """`path_found_flag` and `status` against what the outcome rows and the network actually show."""
    cross = Counter()
    flag_reality = defaultdict(lambda: {"requests": 0, "paths": 0, "asked": 0, "intros": 0})
    for r in data["requests"]:
        flag = r["path_found_flag"].strip() or "(blank)"
        cross[(flag, r["status"].strip())] += 1
        cid = data["golden_requests"][r["request_id"]]["company_id"]
        gc = data["golden_companies"].get(cid, {})
        b = flag_reality[flag]
        b["requests"] += 1
        b["paths"] += int(gc.get("paths_available") or 0) > 0
        o = data["outcome_by_request"].get(r["request_id"])
        if o:
            b["asked"] += 1
            b["intros"] += yes(o, "intro_sent")
    contradictions = []

    def count(predicate):
        return sum(1 for r in data["requests"] if predicate(r, data["outcome_by_request"].get(r["request_id"])))
    contradictions.append(("status <code>Intro sent</code> with no <code>intro_sent=Y</code> outcome row",
                           count(lambda r, o: r["status"] == "Intro sent" and not (o and yes(o, "intro_sent")))))
    contradictions.append(("<code>intro_sent=Y</code> while status is still Open/Stalled/Routed",
                           count(lambda r, o: o and yes(o, "intro_sent") and r["status"] != "Intro sent")))
    contradictions.append(("flag <code>No path found</code> yet an intro was sent",
                           count(lambda r, o: r["path_found_flag"] == "No path found" and o and yes(o, "intro_sent"))))
    contradictions.append(("flag <code>Path found</code> yet nobody was ever asked",
                           count(lambda r, o: r["path_found_flag"] == "Path found" and not o)))
    contradictions.append(("status <code>Closed - no path</code> yet the flag says <code>Path found</code>",
                           count(lambda r, o: r["status"] == "Closed - no path" and r["path_found_flag"] == "Path found")))
    contradictions.append(("status <code>Closed - no path</code> yet a connector was asked",
                           count(lambda r, o: r["status"] == "Closed - no path" and o is not None)))
    return {"cross": cross, "flag_reality": dict(flag_reality), "contradictions": contradictions,
            "flags": Counter((r["path_found_flag"].strip() or "(blank)") for r in data["requests"]),
            "statuses": Counter(r["status"].strip() for r in data["requests"])}


# --------------------------------------------------------------------------- 9. outcomes vs requests delta
def outcome_delta_cut(data):
    """Whether intro_outcomes is a clean subset of intro_requests or a coverage hole."""
    matched = {o["request_id"].strip() for o in data["outcomes"]}
    missing = [r for r in data["requests"] if r["request_id"] not in matched]
    by_status = Counter(r["status"].strip() for r in missing)
    should_exist = [r for r in missing if r["status"] in ("Intro sent", "Routed")]
    offered = 0
    for t in data["threads"]:
        if t["request_id"] in matched:
            continue
        if any(re.search(r"happy to intro|leave it with me|I'll take this one|happy to reach out", m["text"], re.I)
               for m in t["messages"][1:]):
            offered += 1
    return {"requests": len(data["requests"]), "outcomes": len(data["outcomes"]),
            "matched": len(matched), "missing": len(missing), "by_status": by_status.most_common(),
            "should_exist": len(should_exist),
            "should_exist_value": sum(money(r["deal_value_usd"]) for r in should_exist),
            "offered_in_slack": offered,
            "orphan_outcomes": len([o for o in data["outcomes"]
                                    if o["request_id"].strip() not in {r["request_id"] for r in data["requests"]}])}


# --------------------------------------------------------------------------- 10. requesters
def requester_cut(data):
    """Per requester (the SDR and the AEs): asks filed, distinct accounts asked for and
    the CRM value of the ones with an account, intros landed, and how often the ask
    was declared Critical or High. Companies come from golden/ so a repeat ask for
    the same account counts one account and its CRM value once."""
    by = {}
    for r in data["requests"]:
        name = r["requested_by"].strip()
        role = r["requester_role"].strip()
        b = by.setdefault(name, {
            "name": name, "role": role, "kind": "SDR" if "SDR" in role.upper() else "AE",
            "requests": 0, "routed": 0, "intros": 0, "unresolved": 0,
            "companies": set(), "crm_values": {}, "urgency": Counter(),
        })
        b["requests"] += 1
        b["urgency"][r["urgency"].strip().title()] += 1
        cid = data["golden_requests"][r["request_id"]]["company_id"]
        if cid:
            b["companies"].add(cid)
            gc = data["golden_companies"][cid]
            if gc["crm_account_ids"]:
                b["crm_values"][cid] = money(gc["value_usd"])
        else:
            b["unresolved"] += 1
        o = data["outcome_by_request"].get(r["request_id"])
        if o:
            b["routed"] += 1
            b["intros"] += yes(o, "intro_sent")
    for b in by.values():
        b["accounts"] = len(b["companies"])
        b["crm_accounts"] = len(b["crm_values"])
        b["crm_value"] = sum(b["crm_values"].values())
        b["intro_rate"] = b["intros"] / b["requests"]
        b["critical"] = b["urgency"]["Critical"]
        b["critical_high"] = b["urgency"]["Critical"] + b["urgency"]["High"]
        b["critical_share"] = b["critical"] / b["requests"]
        b["critical_high_share"] = b["critical_high"] / b["requests"]
    rows = sorted(by.values(), key=lambda b: (-b["requests"], b["name"]))
    n = sum(b["requests"] for b in rows)
    crm_values = {cid: v for b in rows for cid, v in b["crm_values"].items()}
    return {"requesters": rows, "requests": n,
            "intros": sum(b["intros"] for b in rows),
            "intro_rate": sum(b["intros"] for b in rows) / n if n else 0.0,
            "critical_share": sum(b["critical"] for b in rows) / n if n else 0.0,
            "critical_high_share": sum(b["critical_high"] for b in rows) / n if n else 0.0,
            "accounts": len({c for b in rows for c in b["companies"]}),
            "crm_accounts": len(crm_values), "crm_value": sum(crm_values.values()),
            "shared_accounts": sum(1 for c in Counter(c for b in rows for c in b["companies"]).values() if c > 1)}


CUTS = [("Scoped joins", join_summary_cut), ("Account demand", account_demand_cut),
        ("Top accounts by value", top_accounts_cut), ("Connectors", connector_cut),
        ("Target person provenance", target_person_cut), ("Routing time", routing_time_cut),
        ("Slack threads", slack_cut), ("Flag / status noise", flag_noise_cut),
        ("Outcomes vs requests", outcome_delta_cut), ("Requesters", requester_cut)]


if __name__ == "__main__":
    data = load()
    for label, cut in CUTS:
        result = cut(data)
        print(f"\n=== {label}")
        for key, value in result.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                print(f"{key}: {len(value)} rows, first = { {k: v for k, v in list(value[0].items())[:6]} }")
            elif isinstance(value, list) and len(value) > 12:
                print(f"{key}: {len(value)} values")
            else:
                print(f"{key}: {value}")
