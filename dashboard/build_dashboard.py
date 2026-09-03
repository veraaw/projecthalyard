"""Build dashboard/halyardscoping.html: one page summarising the scoping (Slack thread) findings,
the verification (CSV profile) findings, the intro funnel Sankey, and the integrity audit.

Every number is recomputed from dataset/ so the page stays in step with the data;
the narrative findings mirror scoping/slack_thread_findings.md and verify/profile.md.

    pip install plotly
    python3 dashboard/build_dashboard.py      # from the repo root
"""
import csv
import html
import json
import os
import re
import statistics
import sys
from collections import Counter
from datetime import datetime

import plotly.graph_objects as go
import plotly.io as pio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "dataset")
sys.path.insert(0, os.path.join(ROOT, "scoping"))
sys.path.insert(0, os.path.join(ROOT, "audit"))
from sankey_funnel import build_figure, funnel_stages  # noqa: E402
from integrity_audit import fragment as integrity_fragment  # noqa: E402


def rows(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def usd(d):
    return f"${d/1e6:.1f}M" if d >= 1e6 else f"${d/1e3:.0f}K"


def esc(s):
    return html.escape(str(s))


# --------------------------------------------------------------------------- funnel
stages = funnel_stages()
sankey_fig = build_figure(stages)
sankey_fig.update_layout(width=None, height=560, autosize=True, title=None,
                         margin=dict(l=10, r=10, t=20, b=20))

# --------------------------------------------------------------------------- slack scoping
requests = {r["request_id"]: r for r in rows("intro_requests.csv")}
outcomes = rows("intro_outcomes.csv")
asked_by = {}
for o in outcomes:
    asked_by.setdefault(o["request_id"], set()).add(o["connector_asked"].strip())

with open(os.path.join(DATA, "slack_threads.jsonl"), encoding="utf-8") as f:
    threads = [json.loads(line) for line in f if line.strip()]

names = {m["user"].strip() for t in threads for m in t["messages"]}
names |= {r["requested_by"].strip() for r in requests.values()}
names |= {o["connector_asked"].strip() for o in outcomes}
names = {n for n in names if n and " " in n}
NAME_RE = re.compile("|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)))

replies = [(t["request_id"], m) for t in threads for m in t["messages"][1:]]
masked = Counter(NAME_RE.sub("<NAME>", m["text"]) for _, m in replies)
canned = [(p, n) for p, n in masked.most_common() if n > 1]
canned_total = sum(n for _, n in canned)

OFFER_RE = re.compile(r"happy to intro|leave it with me|I'll take this one|I met their |happy to reach out", re.I)
offers = [(rid, m) for rid, m in replies if OFFER_RE.search(m["text"])]
offers_unlogged = [(rid, m) for rid, m in offers if m["user"].strip() not in asked_by.get(rid, set())]
offers_unlogged_value = sum(float(requests[rid]["deal_value_usd"] or 0) for rid, _ in offers_unlogged)

ADD_RE = re.compile(r"adding (.+?) who might know", re.I)
adds = [(rid, ADD_RE.search(m["text"]).group(1).strip()) for rid, m in replies if ADD_RE.search(m["text"])]
adds_followed = sum(p in asked_by.get(rid, set()) for rid, p in adds)

no_reply = [t for t in threads if len(t["messages"]) <= 1]
no_reply_asked = [t for t in no_reply if t["request_id"] in asked_by]

first_reply_h = []
for t in threads:
    if len(t["messages"]) > 1:
        t0 = datetime.fromisoformat(t["messages"][0]["ts"].replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(t["messages"][1]["ts"].replace("Z", "+00:00"))
        first_reply_h.append((t1 - t0).total_seconds() / 3600)

reply_fig = go.Figure(go.Bar(
    y=[p for p, _ in canned[:8]][::-1], x=[n for _, n in canned[:8]][::-1], orientation="h",
    marker_color=["#1f5f8b" if p.startswith("adding") else "#b8b8b8" for p, _ in canned[:8]][::-1],
    text=[n for _, n in canned[:8]][::-1], textposition="outside",
))
reply_fig.update_layout(height=330, margin=dict(l=10, r=40, t=10, b=30), autosize=True,
                        xaxis=dict(title="replies", range=[0, max(n for _, n in canned[:8]) * 1.15]),
                        yaxis=dict(automargin=True), font=dict(size=13))

# --------------------------------------------------------------------------- csv verification
def norm_entity(v):
    v = re.sub(r"[,.]?\s*(inc|llc|ltd|corp|co|group)\.?$", "", v.strip().lower())
    return re.sub(r"[^a-z0-9]", "", v)


def md_table(text, heading):
    """Return the rows of the first markdown table under `heading` in verify/profile.md."""
    body = text.split(heading, 1)[1]
    out = []
    for line in body.splitlines()[1:]:
        if line.startswith("|"):
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            out.append(cells)
        elif out:
            break
    return out


with open(os.path.join(ROOT, "verify", "profile.md"), encoding="utf-8") as f:
    profile_md = f.read()
inventory = [(fn, int(r), int(c), int(fl)) for fn, r, c, fl in md_table(profile_md, "## Files")[1:]]
flags = [(fn, col, re.sub(r"`", "", issue)) for fn, col, issue in md_table(profile_md, "## All flags, by file")[1:]]
CATEGORY = [("non-ASCII", "non-ASCII characters"), ("mixed case", "mixed case conventions"),
            ("stray punctuation", "stray leading/trailing punctuation"), ("outside 2020-2027", "dates outside 2020-2027"),
            ("near-duplicate", "near-duplicate values (case/punctuation/legal suffix)")]
flag_categories = Counter(next(label for key, label in CATEGORY if key in issue) for _, _, issue in flags)
crm = rows("crm_accounts.csv")
crm_dupes = [k for k, n in Counter(norm_entity(r["account_name"]) for r in crm).items() if n > 1]
crm_dup_owner_conflicts = sum(
    len({r["owner"] for r in crm if norm_entity(r["account_name"]) == k}) > 1 for k in crm_dupes)
req_missing_company = sum(1 for r in requests.values() if not r["target_company_raw"].strip())
req_missing_person = sum(1 for r in requests.values() if not r["target_person_raw"].strip())
req_missing_flag = sum(1 for r in requests.values() if not r["path_found_flag"].strip())
outcome_dup_ids = len(outcomes) - len({o["request_id"] for o in outcomes})
opp_status_mismatch = [o["request_id"] for o in outcomes
                       if o["opportunity_created"] == "Y" and requests[o["request_id"]]["status"] in ("Open", "Stalled", "Routed")]

# --------------------------------------------------------------------------- integrity audit
integrity_div = integrity_fragment()  # also refreshes audit/results.json and audit/integrity.html

# --------------------------------------------------------------------------- render
def kpi(value, label, sub=""):
    return f'<div class="kpi"><div class="v">{value}</div><div class="l">{esc(label)}</div>' + (f'<div class="s">{esc(sub)}</div>' if sub else "") + "</div>"


def table(headers, body_rows, cls=""):
    h = "".join(f"<th>{esc(x)}</th>" for x in headers)
    b = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in body_rows)
    return f'<table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>'


counts = [c for _, c, _ in stages]
dollars = [d for _, _, d in stages]
funnel_rows = [(name, c, usd(d), f"{c/counts[0]:.0%}", f"{c/counts[i-1]:.0%}" if i else "—")
               for i, (name, c, d) in enumerate(stages)]

sankey_div = pio.to_html(sankey_fig, include_plotlyjs=False, full_html=False, div_id="sankey",
                         config={"displayModeBar": False, "responsive": True})
reply_div = pio.to_html(reply_fig, include_plotlyjs=False, full_html=False, div_id="replies",
                        config={"displayModeBar": False, "responsive": True})

page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Halyard — scoping &amp; verification dashboard</title>
<script src="https://cdn.plot.ly/plotly-3.0.1.min.js"></script>
<style>
:root{{--ink:#1c2430;--mute:#6b7480;--blue:#1f5f8b;--line:#e4e7eb;--bg:#f6f7f9;--warn:#b4541c}}
*{{box-sizing:border-box}}
body{{margin:0;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg)}}
header{{background:#fff;border-bottom:1px solid var(--line);padding:28px 40px}}
header h1{{margin:0 0 4px;font-size:26px}}
header p{{margin:0;color:var(--mute)}}
nav a{{margin-right:18px;color:var(--blue);text-decoration:none;font-weight:600}}
main{{max-width:1240px;margin:0 auto;padding:24px 40px 60px}}
section{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:26px 30px;margin:0 0 24px}}
h2{{margin:0 0 6px;font-size:21px}}
h3{{margin:26px 0 10px;font-size:16px;color:var(--mute);text-transform:uppercase;letter-spacing:.04em}}
.lede{{color:var(--mute);margin:0 0 18px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;margin:12px 0 6px}}
.kpi{{background:var(--bg);border-radius:8px;padding:14px 16px}}
.kpi .v{{font-size:28px;font-weight:700;color:var(--blue);line-height:1.1}}
.kpi.warn .v{{color:var(--warn)}}
.kpi .l{{margin-top:4px;font-weight:600}}
.kpi .s{{color:var(--mute);font-size:13px}}
table{{border-collapse:collapse;width:100%;font-size:14px}}
th,td{{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--mute);font-weight:600;font-size:13px}}
td:nth-child(n+2):not(:last-child).num,th.num{{text-align:right}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:28px}}
@media(max-width:900px){{.grid2{{grid-template-columns:1fr}}}}
.finding{{border-left:3px solid var(--blue);padding:4px 14px;margin:12px 0;background:var(--bg);border-radius:0 6px 6px 0}}
.finding.warn{{border-color:var(--warn)}}
.finding b{{display:block}}
.foot{{color:var(--mute);font-size:13px}}
code{{background:var(--bg);padding:1px 5px;border-radius:4px;font-size:13px}}
</style></head>
<body>
<header>
  <h1>Halyard — scoping &amp; verification dashboard</h1>
  <p>200 warm-intro requests · Aug 2025 – Jul 2026 · sources: <code>dataset/</code> · built {datetime.now():%Y-%m-%d}</p>
  <nav style="margin-top:12px"><a href="#funnel">Funnel</a><a href="#scoping">Scoping: Slack threads</a><a href="#verify">Verification: CSV profile</a><a href="#integrity">Integrity audit</a></nav>
</header>
<main>

<section id="funnel">
  <h2>Where the requests go</h2>
  <p class="lede">Each request carries its <code>deal_value_usd</code>; node labels show how many requests and how much pipeline survive each step.</p>
  <div class="kpis">
    {kpi(counts[0], "requests", usd(dollars[0]) + " of pipeline")}
    {kpi(counts[1], "asked", f"{counts[1]/counts[0]:.0%} of requests · {usd(dollars[1])}")}
    {kpi(counts[3], "intros sent", f"{counts[3]/counts[1]:.0%} of asks · {usd(dollars[3])}")}
    {kpi(counts[4], "meetings", f"{counts[4]/counts[3]:.0%} of intros · {usd(dollars[4])}")}
    {kpi(counts[5], "opportunities", f"{usd(dollars[5])} · {dollars[5]/dollars[0]:.1%} of requested $")}
  </div>
  {sankey_div}
  <div class="grid2">
    <div>
      <h3>Stage table</h3>
      {table(["Stage", "Count", "Pipeline $", "of requests", "step conversion"], funnel_rows)}
    </div>
    <div>
      <h3>Reading it</h3>
      <div class="finding warn"><b>The biggest leak is before anyone is asked.</b>{counts[0]-counts[1]} of {counts[0]} requests ({(counts[0]-counts[1])/counts[0]:.0%}, {usd(dollars[0]-dollars[1])}) never reach a connector — larger than every downstream drop combined.</div>
      <div class="finding"><b>Once asked, the funnel is healthy-ish.</b>{counts[2]/counts[1]:.0%} respond, {counts[3]/counts[2]:.0%} of responders send the intro, {counts[4]/counts[3]:.0%} of intros book a meeting, {counts[5]/counts[4]:.0%} of meetings create an opportunity.</div>
      <div class="finding"><b>Opportunity $ is carried over, not validated.</b>All {counts[5]} opportunity values equal the original requested deal value; {len(opp_status_mismatch)} of them still show status Open/Stalled/Routed in <code>intro_requests.csv</code> ({", ".join(opp_status_mismatch)}).</div>
      <p class="foot">Standalone chart + code: <code>scoping/sankey_funnel.py</code>, <code>scoping/sankey_funnel.html</code>.</p>
    </div>
  </div>
</section>

<section id="scoping">
  <h2>Scoping — what happens in <code>#intro-requests</code></h2>
  <p class="lede">From <code>dataset/slack_threads.jsonl</code>: {len(threads)} threads, {sum(len(t["messages"]) for t in threads)} messages, {len(replies)} replies. Full write-up in <code>scoping/slack_thread_findings.md</code>.</p>
  <div class="kpis">
    {kpi(f"{canned_total/len(replies):.0%}", "of replies are canned", f"{len(masked)} distinct texts after name masking")}
    {kpi(len(offers), "genuine offers to help", f"across {len({r for r, _ in offers})} threads")}
    {kpi(f"{len(offers_unlogged)} / {len(offers)}", "offers never logged as asked", usd(offers_unlogged_value) + " of deal value")}
    {kpi(f"{adds_followed} / {len(adds)}", '"adding X who might know" followed up', "named person later asked")}
    {kpi(len(no_reply), "threads with zero replies", f"{len(no_reply_asked)} asked anyway")}
    {kpi(f"{statistics.median(first_reply_h):.0f} h", "median time to first reply", f"mean {statistics.mean(first_reply_h):.0f} h · max {max(first_reply_h):.0f} h")}
  </div>
  <div class="grid2">
    <div>
      <h3>Most common replies (name-masked)</h3>
      {reply_div}
    </div>
    <div>
      <h3>Findings</h3>
      <div class="finding warn"><b>The channel is noise.</b>{canned_total} of {len(replies)} replies repeat one of {len(canned)} stock phrases; the top 7 alone are {sum(n for _, n in canned[:7])} replies. Only {len(offers)} replies actually offer a path.</div>
      <div class="finding warn"><b>Offers fall through the cracks.</b>{len(offers_unlogged)} of the {len(offers)} offers ({", ".join(sorted({r for r, _ in offers_unlogged}))}) have no <code>connector_asked</code> row — {usd(offers_unlogged_value)} of pipeline where someone said "leave it with me" and nothing was recorded.</div>
      <div class="finding warn"><b>Delegation never lands.</b>"adding X who might know" appears {len(adds)} times; the named person was logged as asked in {adds_followed} of them. Everyone tagged is an AE / CRM owner, not a roster connector.</div>
      <div class="finding"><b>Silence is not a signal.</b>{len(no_reply)} threads got no reply, yet {len(no_reply_asked)} of them were routed to a connector anyway — the ask happened outside Slack.</div>
      <div class="finding"><b>Slow first response.</b>Median {statistics.median(first_reply_h):.1f} h to the first reply on the {len(first_reply_h)} threads that got one.</div>
    </div>
  </div>
  <h3>Offers to help with no logged ask</h3>
  {table(["request_id", "Offered by", "deal_value_usd", "Request status", "Reply"],
         [(rid, m["user"], f"{float(requests[rid]['deal_value_usd']):,.0f}", requests[rid]["status"], m["text"]) for rid, m in offers_unlogged])}
</section>

<section id="verify">
  <h2>Verification — CSV inventory profile</h2>
  <p class="lede">From <code>verify/profile.md</code> (generated by <code>verify/profile_csvs.py</code>): {len(inventory)} CSV files, {sum(r for _, r, _, _ in inventory):,} data rows, {len(flags)} column-level flags.</p>
  <div class="kpis">
    {kpi(len(inventory), "CSV files profiled", f"{sum(r for _, r, _, _ in inventory):,} rows")}
    {kpi(len(flags), "column flags raised", f"{len(flag_categories)} categories")}
    {kpi(len(crm_dupes), "near-duplicate CRM accounts", f"{crm_dup_owner_conflicts} with conflicting owners")}
    {kpi(f"{req_missing_company} / {len(requests)}", "requests with no target company", f"{req_missing_person} lack a target person")}
    {kpi(f"{req_missing_flag}", "requests with blank path_found_flag", f"{sum(1 for r in requests.values() if r['path_found_flag'].strip()=='Unknown')} more say Unknown")}
    {kpi(outcome_dup_ids, "duplicate request_ids in outcomes", "one ask per request — a 2nd offer can never be logged")}
  </div>
  <div class="grid2">
    <div>
      <h3>File inventory</h3>
      {table(["File", "Rows", "Columns", "Flags"], inventory)}
    </div>
    <div>
      <h3>Findings</h3>
      <div class="finding warn"><b>Entity resolution is the hard part.</b>{len(crm_dupes)} groups of CRM accounts differ only by case / suffix (e.g. <code>Ellerby Semiconductor, Inc.</code> vs <code>Ellerby Semiconductor</code>), {crm_dup_owner_conflicts} of them owned by different AEs. {req_missing_company} requests have no structured company and must be recovered from free text.</div>
      <div class="finding warn"><b>Connection exports need cleaning.</b>Names with a stray leading <code>·</code> in every <code>connections_*.csv</code>; hundreds of <code>connected_on</code> dates pre-2020 and several in the future (up to 2028).</div>
      <div class="finding"><b>Inconsistent casing is systematic.</b><code>requester_role</code>, <code>status</code>, <code>path_found_flag</code>, <code>role</code> and <code>account_name</code> all mix Title / Sentence / UPPER — safe to normalise, but joins on raw strings will miss.</div>
      <div class="finding"><b>Outcomes are one row per request.</b><code>intro_outcomes.csv</code> has {len(outcomes)} rows and {len(outcomes) - outcome_dup_ids} distinct request_ids, so only one connector can ever be recorded per request.</div>
      <h3>Flag categories</h3>
      {table(["Category", "Columns affected"], flag_categories.most_common())}
    </div>
  </div>
  <h3>All flags, by file</h3>
  {table(["File", "Column", "Issue"], flags)}
</section>

<section id="integrity" style="padding:0 0 10px">
  {integrity_div}
  <p class="foot" style="padding:0 30px">Standalone page + data: <code>audit/integrity.html</code>, <code>audit/results.json</code> (generated by <code>audit/integrity_audit.py</code>).</p>
</section>

<p class="foot">Regenerate with <code>python3 dashboard/build_dashboard.py</code>. All figures are computed from <code>dataset/</code> at build time.</p>
</main>
</body></html>
"""

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "halyardscoping.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(page)
print(f"wrote {out_path}")
print(f"funnel {counts}  offers {len(offers)} unlogged {len(offers_unlogged)} adds {len(adds)}/{adds_followed} "
      f"no_reply {len(no_reply)}/{len(no_reply_asked)} median_h {statistics.median(first_reply_h):.1f} "
      f"flags {len(flags)} dupes {len(crm_dupes)}/{crm_dup_owner_conflicts}")
