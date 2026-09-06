"""Batched-ask composer: one plain-text message per (cycle, connector).

    python3 -m dashboard.batch_ask            # print every message
    python3 -m dashboard.batch_ask 2026-09    # one cycle

Reads four files and nothing else: golden/golden_allocation.csv (who each
request routes to, in which batch, over which path), golden/golden_requests.csv
(who asked, and the thread date of any offer made on the company),
dataset/connector_roster.csv (stated capacity, notes, type) and
dataset/intro_outcomes.csv (the intro a company already had, when the ask is a
retry after it fizzled). `compose()` returns
one record per (cycle, connector) holding an allocation, with the message text
under `message` and everything the message may not say — dollar values, route
scores, request ids, urgency — kept in the structured fields for the page.

The message groups the batch by company, then by contact within the company,
one block per company ordered by the batch's highest route score. Two requests
for the same company and title render once with ", asked twice" (or "Nx"); both
request ids stay on the record. A company whose earlier intro went nowhere
(the allocator only routes such a company afresh once that intro has fizzled)
carries a retry line naming who introduced whom and when. The wording lives in
config/batch_ask_templates.json — the roster template for connectors on the
roster, the offerer template for someone off the roster who is being asked
because they offered in a thread, the network template for an investor_network
person (our circle, not our roster) asked as a favour over their own portfolio
or prior-employer path — so no names and no copy live in this file.

This is a drafting aid. It writes nothing; the existing ask_sent tick stays the
record that an ask went out.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from golden import build_golden as bg
from paths import CONFIG, DATASET, GOLDEN

TEMPLATES = CONFIG / "batch_ask_templates.json"
ALLOCATION = GOLDEN / "golden_allocation.csv"
REQUESTS = GOLDEN / "golden_requests.csv"
ROSTER = DATASET / "connector_roster.csv"
OUTCOMES = DATASET / "intro_outcomes.csv"

ROSTER_TEMPLATE, OFFERER_TEMPLATE, NETWORK_TEMPLATE = "roster", "offerer", "network"
OFFER = "offer"
INDIRECT = {"investor", "board", bg.INVESTOR_NETWORK}


def load_templates(path: Path = TEMPLATES) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def score(v: str) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def offer_dates(requests: list[dict]) -> dict[str, list[tuple[str, str]]]:
    """company_id -> [(thread date, connector who offered)] for every request
    whose thread carried an offer, earliest first. The thread date is the
    request's own date; routed_to names the offerer where the log recorded one."""
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in requests:
        if r.get("offer_in_thread") == "Y" and r.get("request_date"):
            out[r["company_id"]].append((r["request_date"][:10], r.get("routed_to", "")))
    return {cid: sorted(v) for cid, v in out.items()}


def offer_date(offers: dict[str, list[tuple[str, str]]], company_id: str, connector: str, fallback: str) -> str:
    """The date of the thread in which `connector` offered on the company: their
    own offer if the log names them, else the company's earliest offer thread,
    else the allocated request's own date."""
    mine = [d for d, who in offers.get(company_id, []) if who == connector]
    if mine:
        return mine[0]
    if offers.get(company_id):
        return offers[company_id][0][0]
    return fallback[:10]


def prior_intros(outcomes: list[dict], requests: list[dict]) -> dict[str, dict]:
    """company_id -> the newest intro sent on the company: who sent it, to which
    rep, on what date. Which of these count as fizzled is the allocator's call
    (build_golden.introductions); anything it allocated afresh is by construction
    a retry, so the composer only has to name the intro."""
    by_rid = {r["request_id"]: r for r in requests}
    out: dict[str, dict] = {}
    for o in outcomes:
        r = by_rid.get(o["request_id"])
        if not r or not r["company_id"] or o["intro_sent"].strip() != "Y":
            continue
        intro = {"connector": o["connector_asked"], "date": o["intro_date"][:10], "requester": r["requested_by"],
                 "request_id": o["request_id"], "meeting_booked": o["meeting_booked"].strip() == "Y"}
        cur = out.get(r["company_id"])
        if cur is None or (intro["date"], intro["request_id"]) > (cur["date"], cur["request_id"]):
            out[r["company_id"]] = intro
    return out


def retry_text(t: dict, intro: dict | None, who: str, template: str = ROSTER_TEMPLATE) -> str:
    if not intro:
        return ""
    b = t["block"]
    tpl = (b["retry_own"] if intro["connector"] == who
           else b["retry_network"] if template == NETWORK_TEMPLATE else b["retry"])
    return tpl.format(connector=intro["connector"], requester=intro["requester"] or b["requester_unknown"],
                      date=intro["date"] or b["retry_undated"])


def path_text(t: dict, path_type: str, contact: str, date: str) -> str:
    p = t["path"]
    if path_type == "direct":
        return p["direct"].format(contact=contact) if contact else p["unknown"]
    if path_type == bg.INVESTOR_NETWORK:
        return p["investor_network"]
    if path_type in INDIRECT:
        return p["investor"]
    if path_type == OFFER:
        return p["offer"].format(date=date) if date else p["offer_undated"]
    return p["unknown"]


def repeat_suffix(t: dict, n: int) -> str:
    if n <= 1:
        return ""
    return t["block"]["asked_twice"] if n == 2 else t["block"]["asked_n"].format(n=n)


def compose(allocation: list[dict] | None = None, requests: list[dict] | None = None,
            roster: dict[str, dict] | None = None, templates: dict | None = None,
            outcomes: list[dict] | None = None) -> list[dict]:
    """One record per (cycle, connector) with at least one allocated row, ordered
    by cycle then connector. Deterministic for a given input."""
    allocation = bg.read_allocation(ALLOCATION) if allocation is None else allocation
    requests = bg.read_csv(REQUESTS) if requests is None else requests
    roster = bg.load_roster() if roster is None else roster
    t = load_templates() if templates is None else templates
    outcomes = bg.read_csv(OUTCOMES) if outcomes is None else outcomes
    by_rid = {r["request_id"]: r for r in requests}
    offers = offer_dates(requests)
    intros = prior_intros(outcomes, requests)

    batches: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for a in allocation:
        if a.get("allocated_to"):
            batches[(a["cycle"], a["allocated_to"])].append(a)
    return [_record(cycle, who, rows, by_rid, offers, intros, roster, t) for (cycle, who), rows in sorted(batches.items())]


def pick_template(on_roster: bool, path_types: list[str]) -> str:
    """Roster people get the work-queue wording. Off the roster, the whole batch
    decides: all offer paths -> offerer (they volunteered), all investor_network
    paths -> network (a favour asked of our circle), anything mixed -> roster."""
    if on_roster:
        return ROSTER_TEMPLATE
    if all(p == OFFER for p in path_types):
        return OFFERER_TEMPLATE
    if all(p == bg.INVESTOR_NETWORK for p in path_types):
        return NETWORK_TEMPLATE
    return ROSTER_TEMPLATE


def _record(cycle: str, who: str, rows: list[dict], by_rid: dict, offers: dict, intros: dict, roster: dict, t: dict) -> dict:
    r = roster.get(who)
    rows = sorted(rows, key=lambda a: (-score(a["route_score"]), a["company_id"], a["target_title"], a["request_id"]))
    reqs = []
    for a in rows:
        q = by_rid.get(a["request_id"], {})
        reqs.append({
            "request_id": a["request_id"], "company_id": a["company_id"], "company_name": a["company_name"],
            "target_title": a["target_title"], "requested_by": q.get("requested_by", ""),
            "path_type": a["path_type"], "contact_name": a["contact_name"], "route_score": a["route_score"],
            "value_usd": a.get("value_usd", ""), "urgency": a.get("urgency_declared", ""),
            "offer_date": offer_date(offers, a["company_id"], who, q.get("request_date", "")) if a["path_type"] == OFFER else "",
        })

    on_roster = r is not None
    template = pick_template(on_roster, [q["path_type"] for q in reqs])
    companies: list[dict] = []
    for q in reqs:  # rows arrive best-score-first, so first sight of a company fixes block order
        c = next((c for c in companies if c["company_id"] == q["company_id"]), None)
        if c is None:
            intro = intros.get(q["company_id"])
            if intro and intro["date"][:7] >= cycle:  # sent after this cycle's asks went out
                intro = None
            c = {"company_id": q["company_id"], "company_name": q["company_name"], "route_score": q["route_score"],
                 "request_ids": [], "contacts": [], "retry": intro, "retry_line": retry_text(t, intro, who, template)}
            companies.append(c)
        c["request_ids"].append(q["request_id"])
        key = (q["path_type"], q["contact_name"])
        g = next((g for g in c["contacts"] if (g["path_type"], g["contact_name"]) == key), None)
        if g is None:
            g = {"path_type": q["path_type"], "contact_name": q["contact_name"], "offer_date": q["offer_date"],
                 "path": path_text(t, q["path_type"], q["contact_name"], q["offer_date"]), "titles": []}
            c["contacts"].append(g)
        title = next((x for x in g["titles"] if x["target_title"] == q["target_title"]), None)
        if title is None:
            title = {"target_title": q["target_title"], "requesters": [], "request_ids": []}
            g["titles"].append(title)
        title["request_ids"].append(q["request_id"])
        if q["requested_by"] and q["requested_by"] not in title["requesters"]:
            title["requesters"].append(q["requested_by"])
    for c in companies:
        for g in c["contacts"]:
            for x in g["titles"]:
                x["count"] = len(x["request_ids"])

    rec = {
        "cycle": cycle, "connector": who, "slug": slug(who), "first_name": who.split()[0] if who.split() else who,
        "batch_id": rows[0]["batch_id"], "template": template, "on_roster": on_roster,
        "type": r["type"] if r else "", "notes": r["notes"] if r else "",
        "capacity": int(r["stated_monthly_capacity"] or 0) if r else None,
        "request_ids": [q["request_id"] for q in reqs], "request_count": len(reqs), "company_count": len(companies),
        "over_capacity": bool(r) and len(reqs) > int(r["stated_monthly_capacity"] or 0),
        "requests": reqs, "companies": companies,
        "offers": [{"company_id": c["company_id"], "company_name": c["company_name"], "date": g["offer_date"]}
                   for c in companies for g in c["contacts"][:1] if g["path_type"] == OFFER],
    }
    rec["message"] = render(rec, t)
    return rec


def render(rec: dict, t: dict) -> str:
    tpl, b = t[rec["template"]], t["block"]
    lines = [tpl["greeting"].format(first_name=rec["first_name"])]
    if rec["template"] == OFFERER_TEMPLATE:
        offers = tpl["offer_join"].join(tpl["offer"].format(company=o["company_name"], date=o["date"]) for o in rec["offers"])
        lines += [tpl["opening"].format(offers=offers), ""]
    else:
        lines += [tpl["opening"], ""]
    for c in rec["companies"]:
        nested = len(c["contacts"]) > 1
        lines.append((b["company_many_paths"] if nested else b["company"]).format(company=c["company_name"], path=c["contacts"][0]["path"]))
        if c["retry_line"]:
            lines.append(c["retry_line"])
        for g in c["contacts"]:
            if nested:
                lines.append(b["path_line"].format(path=g["path"]))
            for x in g["titles"]:
                lines.append((b["title_nested"] if nested else b["title"]).format(
                    title=x["target_title"],
                    requesters=b["requester_join"].join(x["requesters"]) or b["requester_unknown"],
                    repeat=repeat_suffix(t, x["count"])))
        lines.append("")
    lines.append(tpl["closing"])
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str]) -> None:
    for rec in compose():
        if argv and rec["cycle"] not in argv:
            continue
        print(f"=== {rec['cycle']} · {rec['connector']} · {rec['template']} · {rec['request_count']} requests")
        print(rec["message"])


if __name__ == "__main__":
    main(sys.argv[1:])
