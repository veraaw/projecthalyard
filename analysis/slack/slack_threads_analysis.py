"""Slack thread analysis over dataset/slack_threads.jsonl.

Regenerates analysis/slack/slack_thread_findings.md.

    python3 -m analysis.slack.slack_threads_analysis      # from the repo root
"""
import csv
import json
import os
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime

from paths import DATASET, SLACK

DATA = str(DATASET)


def rows(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


threads = [json.loads(l) for l in open(os.path.join(DATA, "slack_threads.jsonl"), encoding="utf-8") if l.strip()]
requests = {r["request_id"]: r for r in rows("intro_requests.csv")}
outcomes = defaultdict(list)
for r in rows("intro_outcomes.csv"):
    outcomes[r["request_id"]].append(r)

# ---- name vocabulary -------------------------------------------------------
names = set()
for r in rows("connector_roster.csv"):
    names.add(r["name"].strip())
for r in rows("crm_accounts.csv"):
    names.add(r["owner"].strip())
for r in rows("intro_requests.csv"):
    names.add(r["requested_by"].strip())
    names.add(r["target_person_raw"].strip())
for r in rows("investor_network.csv"):
    names.add(r["person"].strip())
for f in os.listdir(DATA):
    if f.startswith("connections_"):
        for r in rows(f):
            names.add(r["name"].strip())
for t in threads:
    for m in t["messages"]:
        names.add(m["user"].strip())
names = {n for n in names if n and " " in n}
NAME_RE = re.compile("|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)))


def mask(text):
    return NAME_RE.sub("<NAME>", text)


# ---- 1. canned phrases -----------------------------------------------------
replies = [(t["request_id"], m) for t in threads for m in t["messages"][1:]]
masked = Counter(mask(m["text"]) for _, m in replies)
total_replies = len(replies)
canned = [(p, n) for p, n in masked.most_common() if n > 1]
canned_total = sum(n for _, n in canned)

# ---- 2. offers to help -----------------------------------------------------
OFFER_RE = re.compile(
    r"happy to intro|leave it with me|I'll take this one|I met their |happy to reach out", re.I
)
offers = [(rid, m) for rid, m in replies if OFFER_RE.search(m["text"])]

# ---- 3. offers not followed by an ask --------------------------------------
def asked_people(rid):
    return {o["connector_asked"].strip() for o in outcomes.get(rid, [])}


offer_gaps = []
for rid, m in offers:
    if m["user"].strip() not in asked_people(rid):
        req = requests.get(rid, {})
        offer_gaps.append((rid, m["user"].strip(), req.get("deal_value_usd", ""), req.get("status", ""), m["text"]))

# ---- 4. "adding X who might know" ------------------------------------------
ADD_RE = re.compile(r"adding (.+?) who might know", re.I)
adds = []
for rid, m in replies:
    g = ADD_RE.search(m["text"])
    if g:
        person = g.group(1).strip()
        adds.append((rid, person, person in asked_people(rid)))

# ---- 5. threads with no reply ----------------------------------------------
no_reply = [t for t in threads if len(t["messages"]) <= 1]
no_reply_asked = [t for t in no_reply if outcomes.get(t["request_id"])]

# ---- 6. median hours to first reply ----------------------------------------
def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


deltas = []
for t in threads:
    if len(t["messages"]) > 1:
        deltas.append((ts(t["messages"][1]["ts"]) - ts(t["messages"][0]["ts"])).total_seconds() / 3600)

out = []
w = out.append
w("# `dataset/slack_threads.jsonl` findings\n")
w(f"{len(threads)} threads, {sum(len(t['messages']) for t in threads)} messages, {total_replies} replies "
  f"(messages after the opening request).\n")

w("## 1. Distinct reply texts after name masking\n")
w(f"- Distinct masked reply texts: **{len(masked)}**")
w(f"- Replies that repeat a text seen more than once: **{canned_total} / {total_replies} "
  f"({canned_total / total_replies:.1%})**")
w(f"- The top 7 masked texts alone account for "
  f"{sum(n for _, n in masked.most_common(7))} replies "
  f"({sum(n for _, n in masked.most_common(7)) / total_replies:.1%}).\n")
w("| Masked reply text | Count |")
w("| --- | ---: |")
for p, n in masked.most_common():
    w(f"| {p} | {n} |")
w("")

w("## 2. Replies offering to help\n")
w(f"{len(offers)} replies across {len({r for r, _ in offers})} threads.\n")
w("| request_id | Person | Reply |")
w("| --- | --- | --- |")
for rid, m in sorted(offers):
    w(f"| {rid} | {m['user']} | {m['text']} |")
w("")

w("## 3. Offers never logged as asked in `intro_outcomes.csv`\n")
w(f"**{len(offer_gaps)} of {len(offers)}** offers have no matching `connector_asked` row for that request.\n")
w("| request_id | Offered by | deal_value_usd | request status | Reply |")
w("| --- | --- | ---: | --- | --- |")
for rid, person, dv, st, text in sorted(offer_gaps):
    w(f"| {rid} | {person} | {dv or '—'} | {st or '—'} | {text} |")
w("")
w(f"Total deal value attached to those requests: "
  f"${sum(int(dv) for _, _, dv, _, _ in offer_gaps if dv.isdigit()):,}\n")

w("## 4. \"adding X who might know\"\n")
asked_after = [a for a in adds if a[2]]
w(f"{len(adds)} such replies; the named person was subsequently logged as asked in "
  f"**{len(asked_after)}** case(s).\n")
w("| request_id | Person added | Later asked? |")
w("| --- | --- | --- |")
for rid, person, was in sorted(adds):
    w(f"| {rid} | {person} | {'yes' if was else 'no'} |")
w("")

w("## 5. Threads with no reply\n")
w(f"- Threads with zero replies: **{len(no_reply)}** of {len(threads)}")
w(f"- Of those, requests that were asked anyway (appear in `intro_outcomes.csv`): **{len(no_reply_asked)}**\n")
if no_reply_asked:
    w("| request_id | Connector(s) asked | deal_value_usd | status |")
    w("| --- | --- | ---: | --- |")
    for t in no_reply_asked:
        rid = t["request_id"]
        req = requests.get(rid, {})
        w(f"| {rid} | {', '.join(sorted(asked_people(rid)))} | {req.get('deal_value_usd', '—')} | "
          f"{req.get('status', '—')} |")
    w("")

w("## 6. Time to first reply\n")
w(f"- Threads with at least one reply: {len(deltas)}")
w(f"- Median: **{statistics.median(deltas):.1f} hours**")
w(f"- Mean {statistics.mean(deltas):.1f} h, min {min(deltas):.1f} h, max {max(deltas):.1f} h\n")

roster = {r["name"].strip() for r in rows("connector_roster.csv")}
asked_all = Counter(o["connector_asked"].strip() for o in rows("intro_outcomes.csv"))
w("## Caveats\n")
w(f"- `intro_outcomes.csv` has {sum(asked_all.values())} rows, one per request_id, so \"asked\" is "
  "single-connector per request: a second person offering on a thread can never appear.")
w("- The 6 roster connectors account for "
  f"{sum(n for p, n in asked_all.items() if p in roster)} of those rows; the other "
  f"{sum(n for p, n in asked_all.items() if p not in roster)} are non-roster people "
  f"({', '.join(sorted(p for p in asked_all if p not in roster))}) — each appears exactly once, and "
  "each is someone who offered on a thread.")
w("- Everyone named in \"adding X who might know\" is a CRM account owner / AE, not a roster "
  "connector, which is why the follow-through rate is 0.\n")

path = str(SLACK / "slack_thread_findings.md")
with open(path, "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print(path)
print(f"replies={total_replies} distinct_masked={len(masked)} canned={canned_total}")
print(f"offers={len(offers)} gaps={len(offer_gaps)} adds={len(adds)} adds_asked={len(asked_after)}")
print(f"no_reply={len(no_reply)} no_reply_asked={len(no_reply_asked)} median_h={statistics.median(deltas):.1f}")
