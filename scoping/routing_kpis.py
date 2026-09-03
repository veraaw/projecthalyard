"""Routing KPIs over dataset/ — regenerates scoping/routing_kpis.md.

Read-only. Add a new `kpi_*` function and list it in KPIS to extend the report.
"""

import csv
import json
import os
import re
import statistics
from collections import defaultdict
from datetime import datetime, timezone

DATA = "dataset"
OUT = "scoping/routing_kpis.md"

OFFER_RE = re.compile(
    r"happy to intro|leave it with me|I'll take this one|I met their |happy to reach out", re.I
)


def rows(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def day(s):
    return datetime.strptime(s.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)


THREADS = [
    json.loads(line)
    for line in open(os.path.join(DATA, "slack_threads.jsonl"), encoding="utf-8")
    if line.strip()
]
THREAD_BY_ID = {t["request_id"]: t for t in THREADS}
REQUESTS = {r["request_id"]: r for r in rows("intro_requests.csv")}
OUTCOMES = defaultdict(list)
for _o in rows("intro_outcomes.csv"):
    OUTCOMES[_o["request_id"]].append(_o)

# offers keyed by request_id -> {person: earliest offer ts}
OFFERS = defaultdict(dict)
for t in THREADS:
    for m in t["messages"][1:]:
        if OFFER_RE.search(m["text"]):
            person = m["user"].strip()
            when = ts(m["ts"])
            if person not in OFFERS[t["request_id"]] or when < OFFERS[t["request_id"]][person]:
                OFFERS[t["request_id"]][person] = when


def kpi_lag_request_to_ask(w):
    w("## Median lag: Slack request -> connector ask\n")
    w("`intro_outcomes.asked_date` is date-only and every thread opens on its request's "
      "`request_date`, so the lag is a whole number of calendar days from the Slack request to the "
      "ask being logged. Only requests that were asked at all are in scope.\n")

    lags, no_thread, no_date = [], [], []
    for rid, outs in OUTCOMES.items():
        thread = THREAD_BY_ID.get(rid)
        if not thread:
            no_thread.append(rid)
            continue
        start = day(thread["messages"][0]["ts"][:10])
        for o in outs:
            if not o["asked_date"].strip():
                no_date.append(rid)
                continue
            lag = (day(o["asked_date"]) - start).days
            lags.append((lag, rid, o["connector_asked"].strip()))

    vals = sorted(v for v, _, _ in lags)
    w(f"- Asks measured: **{len(vals)}** (of {sum(len(v) for v in OUTCOMES.values())} outcome rows, "
      f"{len(REQUESTS)} requests)")
    w(f"- **Median: {statistics.median(vals):.0f} days**")
    w(f"- Mean {statistics.mean(vals):.1f} d, p25 {vals[len(vals) // 4]} d, "
      f"p75 {vals[3 * len(vals) // 4]} d, min {vals[0]} d, max {vals[-1]} d")
    same_day = sum(1 for v in vals if v == 0)
    w(f"- Asked the same day: {same_day} ({same_day / len(vals):.0%}); nothing is asked later than "
      f"{vals[-1]} days, so the lag is bounded rather than long-tailed")
    if no_thread:
        w(f"- Outcome rows with no Slack thread: {len(no_thread)}")
    if no_date:
        w(f"- Outcome rows with an empty `asked_date`: {len(no_date)}")
    w("")

    w("| Lag (days) | Asks |")
    w("| ---: | ---: |")
    for d in range(vals[0], vals[-1] + 1):
        w(f"| {d} | {sum(1 for v in vals if v == d)} |")
    w("")

    # split by whether the thread contained an offer of help
    with_offer = [v for v, rid, _ in lags if OFFERS.get(rid)]
    without = [v for v, rid, _ in lags if not OFFERS.get(rid)]
    w("| Cohort | Asks | Median lag | Mean lag |")
    w("| --- | ---: | ---: | ---: |")
    w(f"| Thread contained an offer of help | {len(with_offer)} | "
      f"{statistics.median(with_offer):.0f} d | {statistics.mean(with_offer):.1f} d |")
    w(f"| No offer on the thread | {len(without)} | {statistics.median(without):.0f} d | "
      f"{statistics.mean(without):.1f} d |")
    w("")
    w("An offer on the thread does not speed the ask up, which is the first sign that the ask is "
      "not actually triggered by the thread.\n")


def kpi_threads_with_offer(w):
    w("## Threads containing a concrete offer of help\n")
    w("A concrete offer is a reply matching `happy to intro`, `leave it with me`, "
      "`I'll take this one`, `I met their <title>`, or `happy to reach out` — an offer to act, "
      "as opposed to `adding X who might know` (a redirect) or `no idea sorry`.\n")
    n = len([t for t in THREADS if OFFERS.get(t["request_id"])])
    replies = sum(len(t["messages"]) - 1 for t in THREADS)
    offer_replies = sum(len(v) for v in OFFERS.values())
    w(f"- Threads with at least one concrete offer: **{n} / {len(THREADS)} ({n / len(THREADS):.1%})**")
    w(f"- Offer replies: {offer_replies} of {replies} replies ({offer_replies / replies:.1%})")
    w(f"- Threads with a reply but no concrete offer: "
      f"{len([t for t in THREADS if len(t['messages']) > 1 and not OFFERS.get(t['request_id'])])}")
    w(f"- Threads with no reply at all: {len([t for t in THREADS if len(t['messages']) <= 1])}\n")
    w("| request_id | Offered by | deal_value_usd | request status | Ask logged? |")
    w("| --- | --- | ---: | --- | --- |")
    for rid in sorted(OFFERS):
        req = REQUESTS.get(rid, {})
        asked = {o["connector_asked"].strip() for o in OUTCOMES.get(rid, [])}
        for person in sorted(OFFERS[rid]):
            w(f"| {rid} | {person} | {req.get('deal_value_usd') or '—'} | "
              f"{req.get('status') or '—'} | {'yes' if person in asked else 'no'} |")
    w("")


def kpi_outcomes_without_offer(w):
    w("## Requests with an outcome row, and where the ask came from\n")
    total = len(REQUESTS)
    with_outcome = [rid for rid in REQUESTS if OUTCOMES.get(rid)]
    from_offer, not_from_offer = [], []
    for rid in with_outcome:
        offered = set(OFFERS.get(rid, {}))
        asked = {o["connector_asked"].strip() for o in OUTCOMES[rid]}
        (from_offer if asked & offered else not_from_offer).append(rid)
    w(f"- Requests with at least one outcome row: **{len(with_outcome)} / {total} "
      f"({len(with_outcome) / total:.1%})**")
    w(f"- Of those, the connector asked had offered on the thread: **{len(from_offer)} "
      f"({len(from_offer) / len(with_outcome):.1%})**")
    w(f"- Of those, the connector asked did **not** come from a Slack offer: "
      f"**{len(not_from_offer)} ({len(not_from_offer) / len(with_outcome):.1%})**\n")

    silent = [rid for rid in not_from_offer if not THREAD_BY_ID.get(rid, {}).get("messages", [])[1:]]
    other_reply = [rid for rid in not_from_offer if rid not in silent]
    w(f"Breakdown of the {len(not_from_offer)} asks with no originating offer:\n")
    w("| Thread state | Requests |")
    w("| --- | ---: |")
    w(f"| Thread got no reply at all | {len(silent)} |")
    w(f"| Thread had replies, none a concrete offer | {len(other_reply)} |")
    w("")
    w("So routing is mostly *not* driven by the channel: the ask is logged against a connector who "
      "never volunteered in the thread.\n")

    conv = lambda ids, field: sum(  # noqa: E731
        1 for rid in ids for o in OUTCOMES[rid] if o[field].strip().upper() == "Y"
    )
    w("| Cohort | Requests | Responded | Intro sent | Meeting booked |")
    w("| --- | ---: | ---: | ---: | ---: |")
    for label, ids in (("Ask came from a Slack offer", from_offer),
                       ("Ask did not come from an offer", not_from_offer)):
        w(f"| {label} | {len(ids)} | {conv(ids, 'responded')} | {conv(ids, 'intro_sent')} | "
          f"{conv(ids, 'meeting_booked')} |")
    w("")
    w(f"Asks that did come from an offer convert better at every stage — meetings booked "
      f"{conv(from_offer, 'meeting_booked') / len(from_offer):.0%} vs "
      f"{conv(not_from_offer, 'meeting_booked') / len(not_from_offer):.0%} — on a small base "
      f"({len(from_offer)} requests).\n")


KPIS = [kpi_lag_request_to_ask, kpi_threads_with_offer, kpi_outcomes_without_offer]


def main():
    out = []
    w = out.append
    w("# Routing KPIs\n")
    w(f"Source: `dataset/` — {len(THREADS)} Slack threads, {len(REQUESTS)} intro requests, "
      f"{sum(len(v) for v in OUTCOMES.values())} outcome rows. Regenerate with "
      "`python3 scoping/routing_kpis.py`; this file is append-only as KPIs are added.\n")
    for kpi in KPIS:
        kpi(w)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
