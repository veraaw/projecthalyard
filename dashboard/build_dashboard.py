"""Build the site in docs/ (gitignored; the rebuild workflow deploys it to GitHub Pages):

  index.html           redirect to halyardscoping.html, with a link to every tab
  halyardscoping.html  Raw Sept Data Dashboard — the file flow, then the same funnel /
                       accounts / requesters / connectors / cycles charts as livedata.html
                       from dataset/ as filed, the funnel overview, timing and Slack
                       findings, and below a divider the data-integrity material: joins,
                       target people, flags, the CSV profile and the integrity audit
  livedata.html        Live Data Dashboard — funnel, accounts, requesters, connectors and
                       cycles from golden/ with completions.csv applied (asks sent from
                       Live Priorities count from the build that pulls them)
  companytrace.html    Company Trace (dashboard/trace_section.py)
  livepriorities.html  Live Priorities — what to do next (dashboard/live_priorities.py)
  connector-<slug>.html  one per connector, in the second tab row: their top 5, then the
                       longer list (dashboard/live_priorities.py connector_pages)

Every number is recomputed from dataset/ so the page stays in step with the data;
the narrative findings mirror analysis/slack/slack_thread_findings.md and
analysis/profile/profile.md.

    pip install plotly
    python3 build.py dashboard      # from the repo root
"""
import csv
import html
import json
import os
import re
import shutil
import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone

import plotly.graph_objects as go
import plotly.io as pio

from analysis.integrity.integrity_audit import fragment as integrity_fragment
from dashboard import data_cuts, theme
from dashboard.funnel_overview import dropoff_rows, ratios
from dashboard.live_priorities import (BANDS as PRIORITIES_BANDS, BATCH_PAGE as BATCH_HTML, BUILD_STAMP,
                                       PAGE as PRIORITIES_HTML, batch_fragment, connector_fragments,
                                       cycles as connector_cycles, fragment as priorities_fragment,
                                       in_flight as priorities_in_flight)
from dashboard.sankey_funnel import build_figure
from dashboard.trace_section import fragment as trace_fragment, sidebar as trace_sidebar
from golden import build_golden as bg
from golden.clock import as_of
from paths import CURRENT, DOCS, PROFILE, ROUTING

DATA = str(CURRENT)


def rows(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def usd(d):
    return f"${d/1e6:.1f}M" if d >= 1e6 else f"${d/1e3:.0f}K"


def esc(s):
    return html.escape(str(s))


# --------------------------------------------------------------------------- funnel
TODAY = as_of()
ROLLING_SINCE = (TODAY - timedelta(days=365)).isoformat()


def plot(fig, div_id):
    html = pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id=div_id,
                       config={"displayModeBar": False, "responsive": True})
    return f'<div class="tscroll plot">{html}</div>'


def sankey(stg, div_id):
    fig = build_figure(stg)
    fig.update_layout(width=None, height=560, autosize=True, title=None,
                      margin=dict(l=10, r=10, t=20, b=20), paper_bgcolor="rgba(0,0,0,0)")
    return plot(fig, div_id)


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

offers = [(rid, m) for rid, m in replies if bg.OFFER_RE.search(m["text"])]
offers_unlogged = [(rid, m) for rid, m in offers if m["user"].strip() not in asked_by.get(rid, set())]

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
    marker_color=[theme.ACCENT if p.startswith("adding") else theme.NEUTRAL for p, _ in canned[:8]][::-1],
    text=[n for _, n in canned[:8]][::-1], textposition="outside",
))
reply_fig.update_layout(height=330, margin=dict(l=10, r=40, t=10, b=30), autosize=True, **theme.PLOTLY_LAYOUT)
reply_fig.update_layout(xaxis=dict(title="replies", range=[0, max(n for _, n in canned[:8]) * 1.15]),
                        yaxis=dict(automargin=True), font_size=13)

# --------------------------------------------------------------------------- csv verification
def norm_entity(v):
    v = re.sub(r"[,.]?\s*(inc|llc|ltd|corp|co|group)\.?$", "", v.strip().lower())
    return re.sub(r"[^a-z0-9]", "", v)


def md_table(text, heading):
    """Return the rows of the first markdown table under `heading` in analysis/profile/profile.md."""
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


with open(PROFILE / "profile.md", encoding="utf-8") as f:
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

# --------------------------------------------------------------------------- integrity audit
integrity_div = integrity_fragment()  # also refreshes analysis/integrity/findings.md

# --------------------------------------------------------------------------- render
def kpi(value, label, sub=""):
    return f'<div class="kpi"><div class="v">{value}</div><div class="l">{esc(label)}</div>' + (f'<div class="s">{esc(sub)}</div>' if sub else "") + "</div>"


def table(headers, body_rows, cls=""):
    h = "".join(f"<th>{esc(x)}</th>" for x in headers)
    b = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in body_rows)
    return f'<table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>'


def pct(a, b, digits=0):
    return f"{a / b:.{digits}%}" if b else "—"


def funnel_table(stg):
    n = [c for _, c in stg]
    return table(["Stage", "Count", "Of requests", "Step conversion"],
                 [(name, c, pct(c, n[0]), pct(c, n[i - 1]) if i else "—") for i, (name, c) in enumerate(stg)])


def funnel_kpis(n, population):
    """`population` names what n[0] counts: "on file" or "dated <since> or later"."""
    return f"""<div class="kpis">
    {kpi(n[0], "requests", population)}
    {kpi(n[1], "asked", f"{pct(n[1], n[0])} of the {n[0]} requests {population}")}
    {kpi(n[3], "intros sent", f"{pct(n[3], n[1])} of asks")}
    {kpi(n[4], "meetings", f"{pct(n[4], n[3])} of intros")}
    {kpi(n[5], "opportunities", f"{pct(n[5], n[0], 1)} of the {n[0]} requests {population}, end-to-end")}
  </div>"""

overview = dropoff_rows()
ov_n = sum(n for _, _, n, _ in overview)
ov_body = "".join(
    f'<tr><td>{esc(category)}</td><td>{esc(dropoff)}</td><td class="num">{n}</td>'
    f'<td class="num">{n / ov_n:.1%}</td></tr>'
    for category, dropoff, n, _ in overview)
ov_body += f'<tr class="total"><td>Total</td><td></td><td class="num">{ov_n}</td><td class="num">100.0%</td></tr>'
ov_body += "".join(
    f'<tr class="ratio"><td colspan="3">{esc(label)}</td><td class="num">{value:.1%}</td></tr>'
    for label, value in ratios(overview))
overview_table = ('<table class="fo"><thead><tr><th>Category</th><th>Funnel dropoff</th>'
                  '<th class="num">Requests</th><th class="num">% of total</th></tr></thead>'
                  f'<tbody>{ov_body}</tbody></table>')

# --------------------------------------------------------------------------- additional data cuts
# the Raw Sept tab reads the September exports as filed; the Live Data tab reads golden/ with the
# ask log as the build applies it (intro_outcomes.csv + golden/completions.csv, see data_cuts.load)
cuts = data_cuts.load()
live_cuts = data_cuts.load("golden")
offers_unlogged_value = data_cuts.dollars(cuts, sorted({rid for rid, _ in offers_unlogged}))
joins = data_cuts.join_summary_cut(cuts)
demand = data_cuts.account_demand_cut(cuts)
connectors = data_cuts.connector_cut(cuts)
targets = data_cuts.target_person_cut(cuts)
timing = data_cuts.routing_time_cut(cuts)
slack = data_cuts.slack_cut(cuts)
noise = data_cuts.flag_noise_cut(cuts)
coverage = data_cuts.outcome_delta_cut(cuts)

joins_rows = [(link, f"{left:.1f}%", f"{right:.1f}%", note or "—")
              for link, left, right, note in sorted(joins["joins"], key=lambda j: min(j[1], j[2]))]
joins_table = table(["Link (left -> right)", "Left matched", "Right matched", "What it means"], joins_rows)


def demand_chart(dm, div_id):
    """Top 20 companies by asks, routed vs never routed, for one window of `dm`."""
    top = dm["companies"][:20]
    fig = go.Figure()
    fig.add_bar(y=[b["name"] for b in top][::-1], x=[b["routed"] for b in top][::-1],
                name="Routed to a connector", orientation="h", marker_color=theme.ACCENT)
    fig.add_bar(y=[b["name"] for b in top][::-1], x=[b["requests"] - b["routed"] for b in top][::-1],
                name="Never routed", orientation="h", marker_color=theme.NEUTRAL)
    fig.update_layout(barmode="stack", height=560, autosize=True, margin=dict(l=10, r=20, t=10, b=30),
                      **theme.PLOTLY_LAYOUT)
    fig.update_layout(legend=dict(orientation="h", y=1.04, x=0), xaxis=dict(title="asks"), yaxis=dict(automargin=True))
    return plot(fig, div_id)


target_table = table(["Looked up in", "Distinct target people found"],
                     [(label, n) for label, n in targets["hits"]])


# --------------------------------------------------------------------------- requesters
def requester_chart(req_rows, traces, div_id, ytitle, tickformat=None, barmode="group"):
    """One bar per requester, in the order of the table (most asks first)."""
    xs = [f'{b["name"]}<br><span style="font-size:11px;color:{theme.MUTE}">{b["kind"]}</span>' for b in req_rows]
    fig = go.Figure()
    for t in traces:
        fig.add_bar(x=xs, **t)
    # headroom so the labels printed above the bars clear the legend
    tops = [sum(ys) for ys in zip(*(t["y"] for t in traces))] if barmode == "stack" else [y for t in traces for y in t["y"]]
    fig.update_layout(barmode=barmode, height=360, autosize=True, margin=dict(l=10, r=10, t=30, b=10),
                      showlegend=len(traces) > 1, **theme.PLOTLY_LAYOUT)
    fig.update_layout(legend=dict(orientation="h", y=1.14, x=0),
                      xaxis=dict(tickfont=dict(size=12), tickangle=-40, fixedrange=True),
                      yaxis=dict(title=ytitle, tickformat=tickformat, range=[0, max(tops or [0]) * 1.18], fixedrange=True))
    return plot(fig, div_id)


weeks = timing["weekly"]
roll = []
for i in range(len(weeks)):
    window = weeks[max(0, i - 3):i + 1]
    req_n = sum(w[1] for w in window)
    roll.append(sum(w[3] for w in window) / req_n if req_n else None)
trend_fig = go.Figure()
trend_fig.add_bar(x=[w[0] for w in weeks], y=[w[1] for w in weeks], name="Requests filed",
                  marker_color=theme.NEUTRAL)
trend_fig.add_bar(x=[w[0] for w in weeks], y=[w[3] for w in weeks], name="Intros sent", marker_color=theme.ACCENT)
trend_fig.add_scatter(x=[w[0] for w in weeks], y=roll, name="Completion rate (4-week rolling)",
                      yaxis="y2", mode="lines", line=dict(color=theme.WARN, width=2))
trend_fig.update_layout(barmode="overlay", height=380, autosize=True, margin=dict(l=10, r=10, t=10, b=30),
                        **theme.PLOTLY_LAYOUT)
trend_fig.update_layout(legend=dict(orientation="h", y=1.08, x=0),
                        xaxis=dict(title="week of request"), yaxis=dict(title="requests"),
                        yaxis2=dict(overlaying="y", side="right", tickformat=".0%", range=[0, 1],
                                    title="completion rate", showgrid=False))
trend_div = plot(trend_fig, "trend")
monthly_rows = [(month, n, a, i, f"{i/n:.0%}", f"{lat:.1f} d" if lat is not None else "—")
                for month, n, a, i, lat in timing["monthly"]]
monthly_table = table(["Month", "Requests", "Routed", "Intros sent", "Completion rate", "Mean days to ask"],
                      monthly_rows)

# --------------------------------------------------------------------------- intros by cycle
def cycle_chart(cyc_rows, div_id):
    cyc_fig = go.Figure()
    cyc_fig.add_bar(x=[r["cycle"] for r in cyc_rows], y=[r["used"] for r in cyc_rows], name="Roster slots used",
                    marker_color=theme.NEUTRAL)
    cyc_fig.add_bar(x=[r["cycle"] for r in cyc_rows], y=[r["intros"] for r in cyc_rows], name="Intros made",
                    marker_color=theme.ACCENT)
    cyc_fig.add_scatter(x=[r["cycle"] for r in cyc_rows], y=[r["intros_cumulative"] for r in cyc_rows],
                        name="Cumulative intros", mode="lines+markers", line=dict(color=theme.WARN, width=2))
    cyc_fig.add_scatter(x=[r["cycle"] for r in cyc_rows], y=[r["capacity_pct"] for r in cyc_rows],
                        name="Capacity used", yaxis="y2", mode="lines", line=dict(color=theme.BATON, width=2, dash="dot"))
    cyc_fig.update_layout(barmode="overlay", height=380, autosize=True, margin=dict(l=10, r=10, t=10, b=30),
                          **theme.PLOTLY_LAYOUT)
    cyc_fig.update_layout(legend=dict(orientation="h", y=1.08, x=0),
                          xaxis=dict(title="cycle", type="category"), yaxis=dict(title="asks / intros"),
                          yaxis2=dict(overlaying="y", side="right", tickformat=".0%", rangemode="tozero",
                                      title="capacity used", showgrid=False))
    return plot(cyc_fig, div_id)


def cycle_cell(r):
    return f'{r["asks"]}' + (f' <span class="foot">+ {r["allocated"]} allocated</span>' if r["allocated"] else "")


def cycle_pct(r):
    return (f'{r["capacity_pct"]:.0%} <span class="foot">{r["used"]} / {r["capacity"]}</span>'
            if r["capacity_pct"] is not None else "—")


def cycle_table(rows):
    NOW, TAG = ' class="now"', ' <span class="foot">this cycle</span>'
    body = "".join(
        f'<tr{NOW if r["current"] else ""}><td class="date">{esc(r["cycle"])}{TAG if r["current"] else ""}</td>'
        f'<td class="num">{cycle_cell(r)}</td><td class="num">{cycle_pct(r)}</td>'
        f'<td class="num">{r["intros"]}</td><td class="num">{r["intros_cumulative"]}</td></tr>'
        for r in rows)
    return ('<table class="cycles"><thead><tr><th>Cycle</th><th class="num">Asks</th><th class="num">Of capacity</th>'
            f'<th class="num">Intros made</th><th class="num">Cumulative intros</th></tr></thead><tbody>{body}</tbody></table>')


def cycle_connector_table(cyc):
    rows_ = [(p["connector"], p["rows"][-1]["capacity"], f'{p["rows"][-1]["used"]} ({p["rows"][-1]["capacity_pct"] or 0:.0%})',
              p["rows"][-1]["intros"], p["rows"][-1]["intros_cumulative"],
              f'{sum(r["asks"] for r in p["rows"]) / max(1, len(p["rows"])):.1f}',
              f'{sum(r["capacity_pct"] or 0 for r in p["rows"][:-1]) / max(1, len(p["rows"]) - 1):.0%}',
              f'{sum(r["intros"] for r in p["rows"]) / max(1, len(p["rows"])):.1f}')
             for p in cyc["per_connector"] if p["rows"]]
    return table(["Connector", "Capacity/mo", "Slots used this cycle", "Intros this cycle", "Cumulative intros",
                  "Asks / cycle", "Capacity used / cycle", "Intros / cycle"], rows_)


# --------------------------------------------------------------------------- the shared strategic sections
def finding(title, text, warn=False):
    return f'<div class="finding{" warn" if warn else ""}"><b>{title}</b>{text}</div>'


def names_list(xs):
    xs = list(xs)
    return ", ".join(xs[:-1]) + " and " + xs[-1] if len(xs) > 1 else "".join(xs)


SEG_SCRIPT = """<script>
(function () {
  // Cumulative / Last 12 months: each .seg swaps the .fview blocks inside its data-scope element,
  // leaving alone the ones that belong to a toggle nested inside it
  var segs = document.querySelectorAll('.seg[data-scope]');
  var scopes = Array.prototype.map.call(segs, function (s) { return '#' + s.dataset.scope; }).join(',');
  segs.forEach(function (seg) {
    var scope = document.getElementById(seg.dataset.scope), note = document.getElementById(seg.dataset.scope + '-window');
    seg.querySelectorAll('button').forEach(function (b) {
      b.onclick = function () {
        seg.querySelectorAll('button').forEach(function (x) { x.classList.toggle('on', x === b); });
        scope.querySelectorAll('.fview').forEach(function (v) {
          if (v.parentElement.closest(scopes) !== scope) return;
          v.hidden = v.dataset.view !== b.dataset.view;
          if (!v.hidden && window.Plotly) v.querySelectorAll('.js-plotly-plot').forEach(function (p) { Plotly.Plots.resize(p); });
        });
        if (note) note.textContent = note.dataset[b.dataset.view];
      };
    });
  });
})();
</script>"""

STRATEGIC_NAV = [("#funnel", "Funnel", ""), ("#accounts", "Accounts", ""), ("#requesters", "Requesters", ""),
                 ("#connectors", "Connectors", ""), ("#latency", "Latency", ""), ("#cycles", "Intros by Cycle", "")]
LIVE_NAV = STRATEGIC_NAV[:1] + [("#unrouted", "Remaining Unrouted", ""), ("#inflight", "Requests in Flight", "")] + STRATEGIC_NAV[1:]


def in_flight_section(f):
    """Every open request in one state, the counts Live Priorities shows in its own sections."""
    section_label = {sid: label for _, _, sections in PRIORITIES_BANDS for sid, label in sections}
    by_key = {r["key"]: r for r in f["rows"]}
    waiting = sum(r["count"] for r in f["rows"] if r["group"] == "Asked, waiting on the connector")
    on_file = f["open"] + sum(o["count"] for o in f["outside"])
    body = ""
    for g in f["groups"]:
        body += f'<tr class="group"><th colspan="6">{esc(g["group"])} <span class="foot">{g["count"]} of the {f["open"]} in flight</span></th></tr>'
        for r in f["rows"]:
            if r["group"] != g["group"]:
                continue
            where = (f'<a href="{PRIORITIES_HTML}#{r["section"]}">{esc(section_label[r["section"]])}</a>' if r["section"] else "—")
            body += (f'<tr><td>{esc(r["label"])}' + (f'<br><span class="foot">{esc(r["note"])}</span>' if r["note"] else "")
                     + f'</td><td class="num"><b>{r["count"]}</b></td><td class="num">{pct(r["count"], f["open"])}</td>'
                     f'<td class="num">{esc(r["value_fmt"])}</td><td>{esc(r["next"])}</td><td>{where}</td></tr>')
    body += f'<tr class="total"><th>All requests in flight</th><th class="num">{f["open"]}</th><th class="num">100%</th><th colspan="3"></th></tr>'
    outside = " and ".join(f'{o["count"]} filed <code>{esc(o["status"])}</code>' for o in f["outside"])
    return f"""
<section id="inflight">
  <h2>Requests in Flight</h2>
  <p class="lede">Every request filed Open, Routed or Stalled in <code>golden/golden_requests.csv</code>, plus every request the allocator has this cycle whatever its filed status (a <code>Closed - no path</code> or <code>Intro sent</code> that nobody ever asked), each in exactly one state as of the build. The counts are the ones the <a href="{PRIORITIES_HTML}">Live Priorities</a> tab shows section by section: the queue and its exceptions from <code>golden/golden_allocation.csv</code>, the nudges and chases from the ask log, the parked requests from the live intros. Not in flight, asked and finished: {outside}.</p>
  <div class="kpis">
    {kpi(f["open"], "requests in flight", f"of {on_file} requests on file, in {len(f['rows'])} states")}
    {kpi(by_key["queued"]["count"], "queued this cycle", f"{by_key['no_slot']['count']} more routed with no slot")}
    {kpi(waiting, "waiting on a connector", f"{by_key['nudge']['count']} nudges and {by_key['chase']['count']} chases owed")}
    {kpi(by_key["parked"]["count"] + by_key["introduced"]["count"], "on a live intro", f"{by_key['parked']['count']} parked behind one, {by_key['introduced']['count']} introduced")}
    {kpi(by_key["meeting"]["count"], "meeting booked", by_key["meeting"]["note"] or "no opportunity logged yet")}
  </div>
  <table class="inflight"><thead><tr><th>State</th><th>Requests</th><th>Of in flight</th><th>Value</th><th>What happens next</th><th>On Live Priorities</th></tr></thead><tbody>{body}</tbody></table>
  <p class="foot">Value counts each company once (CRM ARR potential, else the deal value filed), as Live Priorities does. A nudge is owed on an ask the connector agreed to and has not delivered; a chase on one they never answered; either waits {f["quiet_days"]} days after a follow-up. An intro is live for {f["intro_live_days"]} days, or while its meeting has not stalled. Code: <code>dashboard/live_priorities.py</code> (<code>in_flight</code>).</p>
</section>
"""


def days(x):
    return "—" if x is None else (f"{x:.0f} d" if float(x).is_integer() else f"{x:.1f} d")


def backlog_box(b, population):
    top = ", ".join(f'{c["name"]} ({c["requests"]})' for c in b["companies"][:5])
    return finding(f'{b["never"]} of the {b["in_window"]} requests {population} never reach a connector.',
                   f'{b["with_path"]} of them are for {len(b["companies"])} companies that already have a path in <code>supply_reach.csv</code>, a backlog worth {usd(b["with_path_value"])} '
                   f'(one $ per company) that could be asked today; the other {b["without_path"]} ({usd(b["without_path_value"])}) have no path on file. '
                   + (f'Most-requested with a path: {top}.' if top else ''), warn=True)


def blockage_donut(ab, div_id, population):
    """Three slices over the blocked never-asked requests, bucketed on the request's state (the allocator's
    exception_reason, or the status gate); each slice's tooltip lists the exact states it sums.
    `population` names the requests the count is of: "on file" or "dated <since> or later"."""
    slices = [ab["slices"][k] for k in ("supply", "process", "closed")]
    sums = ["<br>".join(f'{b["bucket"]} {b["count"]}' for b in s["buckets"]) or "nothing this cycle" for s in slices]
    fig = go.Figure(go.Pie(
        labels=[s["label"] for s in slices], values=[s["count"] for s in slices], hole=.62, sort=False, direction="clockwise",
        marker=dict(colors=[theme.WARN, theme.ACCENT, theme.NEUTRAL_DARK], line=dict(color=theme.SURFACE, width=2)),
        text=[str(s["count"]) for s in slices], textinfo="text", textposition="inside", textfont=dict(size=14, color="#fff"),
        customdata=sums,
        hovertemplate="<b>%{label}</b>: %{value} of " + str(ab["blocked"]) + " blocked (%{percent})<br>sums exception_reason:<br>%{customdata}<extra></extra>"))
    fig.update_layout(height=320, autosize=True, margin=dict(l=10, r=10, t=10, b=10), showlegend=True, **theme.PLOTLY_LAYOUT)
    fig.update_layout(legend=dict(orientation="v", x=1, y=.5, xanchor="left"))
    fig.add_annotation(text=f'<b>{ab["blocked"]}</b><br><span style="font-size:11px">blocked<br>of {ab["in_window"]} requests {population}</span>',
                       x=.5, y=.5, showarrow=False, font=dict(size=22, color=theme.INK))
    return plot(fig, div_id)


def bucket_text(b):
    """A bucket with its count and, where the same bucket holds requests both with and without a
    path on file, that split."""
    without = b["no_path"] + b["unresolved"]
    if not (b["with_path"] and without):
        return f'{b["bucket"]} {b["count"]}'
    parts = [f'{b["no_path"]} no path'] * bool(b["no_path"]) + [f'{b["unresolved"]} no resolvable company'] * bool(b["unresolved"])
    return f'{b["bucket"]} {b["count"]} ({b["with_path"]} with a path available, {without} without: {", ".join(parts)})'


def blockage_caption(ab, population):
    """What the donut states rather than draws: the split, every state in each slice, any state no slice
    claims, and the no-path footnote. `population` as for blockage_donut."""
    def slice_text(kind):
        s = ab["slices"][kind]
        return f'{s["label"].capitalize()} {s["count"]}: ' + ("; ".join(bucket_text(b) for b in s["buckets"]) or "none") + "."
    gated = sum(b["no_path"] for b in ab["no_path_gated"])
    gated_text = ", ".join(f'{b["no_path"]} in {b["bucket"]}' for b in ab["no_path_gated"])
    unmapped = (finding("Outside the wedges.", "States no slice claims: " + "; ".join(bucket_text(b) for b in ab["unmapped"]) + ".", warn=True)
                if ab["unmapped"] else "")
    return f"""<p class="lede">{ab["never"]} of the {ab["in_window"]} requests {population} never reach a connector; {ab["blocked"]} of those are blocked. The other {ab["allocated"]} are allocated this cycle and not yet asked; they carry a <code>routed_to</code> and are not blocked.</p>
  {finding(f'Only {ab["supply_share"]:.0%} of the blockage is a missing relationship.', f'{slice_text("supply")} {slice_text("process")} {slice_text("closed")}', warn=True)}
  {unmapped}
  <p class="foot">{ab["no_path"]} never-asked requests (of the {ab["in_window"]} {population}) name a company with no path in <code>supply_reach.csv</code>: the {ab["slices"]["supply"]["count"]} above plus {gated} held before their paths were evaluated{f" ({gated_text})" if gated_text else ""}. That figure overlaps the slices, so it is a footnote, not a wedge.</p>"""


STATE_SOURCE = ('Each request has one state (<code>dashboard/request_state.py</code>, the classifier Live Priorities groups by too): '
                'in the ask log it is <i>asked</i>; otherwise its row in the current cycle of <code>golden/golden_allocation.csv</code> '
                'names a connector (<i>allocated, not yet asked</i>) or an <code>exception_reason</code> (its text before the first colon); '
                'with no row, <i>status gate:</i> a status the allocator does not know (every status on file reaches it; '
                'a request filed Intro sent with no intro logged is the <i>intro claimed, none logged</i> repair queue). '
                '<code>blocked_reason</code> is not an input: '
                'it ranks what would unblock a request, not why the system stopped.')


def blockage_view(bl, div_id, population):
    """The Remaining Unrouted donut with its reading, for one window of the funnel."""
    return f"""<div class="grid2">
    <div>{blockage_donut(bl, div_id, population)}</div>
    <div>
      {blockage_caption(bl, population)}
      <p class="foot">Code: <code>dashboard/data_cuts.py</code> (<code>blockage_cut</code>). {STATE_SOURCE}</p>
    </div>
  </div>"""


def blockage_panel(data, window_all):
    """Remaining Unrouted: its own section on Live Data, right below the funnel, with its own
    Cumulative / Last 12 months toggle so it can be read against either funnel view."""
    bl, bl_12m = data_cuts.blockage_cut(data), data_cuts.blockage_cut(data, since=ROLLING_SINCE)
    return f"""
<section id="unrouted">
  <h2>Remaining Unrouted</h2>
  <div class="seg" id="unrouted-toggle" data-scope="unrouted" role="tablist"><button class="on" data-view="all" role="tab">Cumulative</button><button data-view="12m" role="tab">Last 12 months</button></div>
  <span class="foot" id="unrouted-window" data-all="{window_all}: {bl['never']} of {bl['total']} requests on file never asked" data-12m="Requests dated {ROLLING_SINCE} or later: {bl_12m['never']} of the {bl_12m['in_window']} in the window never asked ({bl['never']} of {bl['total']} on file)">{window_all}: {bl['never']} of {bl['total']} requests on file never asked</span>
  <div class="fview" data-view="12m" hidden>{blockage_view(bl_12m, "blockage-12m", f"dated {ROLLING_SINCE} or later")}</div>
  <div class="fview" data-view="all">{blockage_view(bl, "blockage", "on file")}</div>
</section>
"""


def return_chart(cs, div_id):
    """Connectors ranked by opportunity value per ask, best first."""
    fig = go.Figure()
    fig.add_bar(y=[c["name"] for c in cs][::-1], x=[c["opp_per_ask"] for c in cs][::-1], orientation="h",
                marker_color=theme.ACCENT, text=[f'{usd(c["opp_per_ask"])} · {usd(c["opp_value"])} from {c["asked"]} asks' for c in cs][::-1],
                textposition="outside", cliponaxis=False)
    fig.update_layout(height=60 + 40 * len(cs), autosize=True, margin=dict(l=10, r=150, t=10, b=30), showlegend=False, **theme.PLOTLY_LAYOUT)
    fig.update_layout(xaxis=dict(title="opportunity $ per ask", tickprefix="$", tickformat="~s", fixedrange=True), yaxis=dict(automargin=True, fixedrange=True))
    return plot(fig, div_id)


def latency_chart(monthly, div_id):
    """Median days for each step, by the month the request was filed."""
    fig = go.Figure()
    for key, label, color in (("to_ask", "Request to ask", theme.NEUTRAL_DARK), ("to_resp", "Ask to first response", theme.ACCENT),
                              ("to_intro", "Ask to intro", theme.WARN)):
        fig.add_scatter(x=[m["month"] for m in monthly], y=[m[key] for m in monthly], name=label, mode="lines+markers",
                        line=dict(color=color, width=2), connectgaps=True)
    fig.update_layout(height=340, autosize=True, margin=dict(l=10, r=10, t=10, b=30), **theme.PLOTLY_LAYOUT)
    fig.update_layout(legend=dict(orientation="h", y=1.1, x=0), xaxis=dict(title="month requested", fixedrange=True),
                      yaxis=dict(title="median days", rangemode="tozero", fixedrange=True))
    return plot(fig, div_id)


def headline_kpis(data):
    """The strip at the top of the Live Data tab: what the asks returned, how fast, and what is reachable but unasked."""
    y, lat, b = data_cuts.yield_cut(data), data_cuts.latency_cut(data), data_cuts.backlog_cut(data)
    return f"""<div class="kpis headline">
    {kpi(usd(y["opp"]), "opportunity value created", f"from {y['asks']} asks, {y['intros']} intros, {y['opps']} opportunities at {y['opp_companies']} companies, each counted once")}
    {kpi(usd(y["opp_per_ask"]), "return per ask", f"{usd(y['opp_per_intro'])} per intro")}
    {kpi(days(lat["median_to_intro"]), "median ask to intro", f"{days(lat['median_to_ask'])} request to ask")}
    {kpi(days(lat["median_to_resp"]), "median ask to first response", f"over {lat['asks']} asks")}
    {kpi(usd(b["with_path_value"]), "reachable but never asked", f"{b['with_path']} of {b['total']} requests on file, at {len(b['companies'])} companies with a path in supply_reach.csv, each counted once")}
  </div>"""


def strategic_sections(data, cyc, live, in_flight=None):
    """The five sections the two data dashboards share (funnel, accounts, requesters, connectors,
    intros by cycle), rendered from one data_cuts.load() result and one cycles dict. `live` picks
    the wording and the source lines: the Live Data tab reads golden/ with the ask log as the
    build applies it and says whatever the current data says; the Raw Sept tab reads the
    September exports as filed and keeps the September findings, by name, where those names
    are still on the roster."""
    n_req = len(data["requests"])
    ask_log = ('the ask log (<code>intro_outcomes.csv</code> with <code>golden/completions.csv</code> applied)' if live
               else '<code>intro_outcomes.csv</code>')
    status_file = "<code>status_as_filed</code>" if live else "<code>intro_requests.csv</code>"
    dates = sorted(r["request_date"].strip()[:10] for r in data["requests"] if r["request_date"].strip())
    first, last = (dates[0][:7], dates[-1][:7]) if dates else ("", "")
    window_all = f"Every request on file, {first} to {last}"

    # funnel
    stages = data_cuts.funnel_cut(data)
    stages_12m = data_cuts.funnel_cut(data, since=ROLLING_SINCE)
    counts, counts_12m = [c for _, c in stages], [c for _, c in stages_12m]
    mismatch = data_cuts.opportunity_status_mismatch(data)
    completion_asks = [o for o in data["outcomes"] if o.get("source") == "completions.csv"]
    reasks = [o for o in data["outcomes"] if o.get("reasked_date", "").strip()]
    funnel_source = (f'From <code>golden/golden_requests.csv</code> joined to {ask_log}: {len(completion_asks)} of the '
                     f'{counts[1]} asks so far exist only as a Submit on Live Priorities, and {len(reasks)} intros that fizzled '
                     f'have been re-asked.' if live else 'From <code>intro_requests.csv</code> and <code>intro_outcomes.csv</code>.')
    funnel = f"""
<section id="funnel">
  <h2>Where the Requests Go</h2>
  <p class="lede">{funnel_source} Node labels show how many requests survive each step. Pipeline $ is deliberately omitted: the same <code>deal_value_usd</code> would be re-counted at every stage a request passes through.</p>
  <div class="seg" id="funnel-toggle" data-scope="funnel" role="tablist"><button class="on" data-view="all" role="tab">Cumulative</button><button data-view="12m" role="tab">Last 12 months</button></div>
  <span class="foot" id="funnel-window" data-all="{window_all}" data-12m="Requests dated {ROLLING_SINCE} or later ({counts_12m[0]} of {counts[0]}), rolling from the build date">{window_all}</span>
  <div class="fview" data-view="12m" hidden>
  {funnel_kpis(counts_12m, f"dated {ROLLING_SINCE} or later")}
  {sankey(stages_12m, "sankey-12m")}
  {backlog_box(data_cuts.backlog_cut(data, since=ROLLING_SINCE), f"dated {ROLLING_SINCE} or later")}
  </div>
  <div class="fview" data-view="all">
  {funnel_kpis(counts, "on file")}
  {sankey(stages, "sankey")}
  {backlog_box(data_cuts.backlog_cut(data), "on file")}
  </div>
  <div class="fview" data-view="12m" hidden>
  <div class="grid2">
    <div>
      <h3>Stage table, last 12 months</h3>
      {funnel_table(stages_12m)}
    </div>
    <div>
      <h3>Reading it</h3>
      {finding("The biggest leak is still before anyone is asked.", f"{counts_12m[0]-counts_12m[1]} of the {counts_12m[0]} requests dated {ROLLING_SINCE} or later ({pct(counts_12m[0]-counts_12m[1], counts_12m[0])}) never reach a connector.", warn=True)}
      {finding("Once asked.", f"{pct(counts_12m[2], counts_12m[1])} respond, {pct(counts_12m[3], counts_12m[2])} of responders send the intro, {pct(counts_12m[4], counts_12m[3])} of intros book a meeting, {pct(counts_12m[5], counts_12m[4])} of meetings create an opportunity.")}
      <p class="foot">Same stages and source as the cumulative view, restricted to <code>request_date &gt;= {ROLLING_SINCE}</code>; the window moves every time the page is rebuilt.</p>
    </div>
  </div>
  </div>
  <div class="fview" data-view="all">
  <div class="grid2">
    <div>
      <h3>Stage table</h3>
      {funnel_table(stages)}
    </div>
    <div>
      <h3>Reading it</h3>
      {finding("The biggest leak is before anyone is asked.", f"{counts[0]-counts[1]} of the {counts[0]} requests on file ({pct(counts[0]-counts[1], counts[0])}) never reach a connector, a larger drop than every downstream stage combined.", warn=True)}
      {finding("Once asked, the funnel is healthy-ish.", f"{pct(counts[2], counts[1])} respond, {pct(counts[3], counts[2])} of responders send the intro, {pct(counts[4], counts[3])} of intros book a meeting, {pct(counts[5], counts[4])} of meetings create an opportunity.")}
      {finding("Status and outcomes disagree.", f"{len(mismatch)} of the {counts[5]} opportunity requests still show status Open/Stalled/Routed in {status_file}" + (f" ({', '.join(mismatch)})." if mismatch else "."))}
      <p class="foot">Code: <code>dashboard/data_cuts.py</code> (<code>funnel_cut</code>), drawn by <code>dashboard/sankey_funnel.py</code>.</p>
    </div>
  </div>
  </div>
</section>
""" + (blockage_panel(data, window_all) if live else "") + (in_flight_section(in_flight) if in_flight else "")

    # accounts
    demand = data_cuts.account_demand_cut(data)
    demand_12m = data_cuts.account_demand_cut(data, since=ROLLING_SINCE)
    top_accounts = data_cuts.top_accounts_cut(data)
    demand_top = demand["companies"][:20]
    demand_rows = [(b["name"], b["industry"] or ("—" if b["in_crm"] else "no CRM record"), b["requests"], b["routed"], b["requests"] - b["routed"],
                    len(b["requesters"]), b["paths"], usd(b["value"])) for b in demand_top]
    demand_rows += [(b["name"], "unresolvable", b["requests"], b["routed"], b["requests"] - b["routed"],
                     len(b["requesters"]), "—", "—") for b in demand["unresolvable"]]
    demand_table = table(["Company", "Industry", "Asks", "Routed", "Never routed", "Requesters", "Paths in network", "Value"], demand_rows)
    unresolvable_asks = sum(b["requests"] for b in demand["unresolvable"])
    top_rows = [(b["name"], usd(b["value"]), "CRM ARR" if b["value_source"] == "CRM" else "deal value",
                 b["requests"], b["routed"], f'{b["responded"]}/{b["intros"]}/{b["meetings"]}/{b["opps"]}',
                 b["owner"] or "no CRM account", ", ".join(b["internal_connectors"]) or "—", ", ".join(b["outside_connectors"]) or "—")
                for b in top_accounts["companies"]]
    top_table = table(["Company", "Value", "Value from", "Asks", "Routed", "Resp/Intro/Mtg/Opp",
                       "CRM owner", "Internal connectors asked", "Advisor / investor asked"], top_rows)
    most = demand["companies"][0] if demand["companies"] else {"requests": 0, "name": "—"}
    never_routed = [b["name"] for b in demand_top if b["routed"] == 0]
    accounts = f"""
<section id="accounts">
  <h2>Account-Level Demand</h2>
  <p class="lede">Asks per company after entity resolution ({len(demand["companies"])} distinct companies behind {n_req - unresolvable_asks} of the {n_req} requests on file, by <code>company_id</code> from <code>golden/golden_requests.csv</code>), split by whether a connector was ever asked. The {unresolvable_asks} asks that resolve to no company are grouped by why rather than by the name written.{" Industry, owner and ARR are the CRM's, as <code>golden/golden_companies.csv</code> carries them after the last rebuild." if live else ""}</p>
  <div class="kpis">
    {kpi(len(demand["companies"]), "distinct companies requested", f"{demand['repeat_share']:.0%} of asks are for a repeat company")}
    {kpi(demand["singletons"], "companies asked exactly once", f"{len(demand['companies']) - demand['singletons']} asked more than once")}
    {kpi(most["requests"], f"asks for {most['name']}", f"the most-requested company, of {n_req} requests on file")}
    {kpi(sum(1 for b in demand["companies"] if b["routed"] == 0), "companies never routed once", "nobody was asked for any of their requests")}
  </div>
  <div class="grid2">
    <div id="demand-views">
      <h3>Top 20 companies by asks</h3>
      <div class="seg" id="demand-toggle" data-scope="demand-views" role="tablist"><button class="on" data-view="all" role="tab">Cumulative</button><button data-view="12m" role="tab">Last 12 months</button></div>
      <span class="foot" id="demand-views-window" data-all="{window_all}" data-12m="Requests dated {ROLLING_SINCE} or later ({demand_12m['asks']} of {demand['asks']} asks, {len(demand_12m['companies'])} companies), rolling from the build date">{window_all}</span>
      <div class="fview" data-view="12m" hidden>{demand_chart(demand_12m, "demand-12m")}</div>
      <div class="fview" data-view="all">{demand_chart(demand, "demand")}</div>
    </div>
    <div>
      <h3>Reading it</h3>
      {finding("Demand is concentrated and repetitive.", f"{demand['repeat_share']:.0%} of all asks are for a company that was already requested at least once. The same {len(demand['companies']) - demand['singletons']} companies come back again and again, which is what the duplicate-checking in Slack is reacting to.", warn=True)}
      {finding("Some companies are asked repeatedly and never routed.", f"{', '.join(never_routed)} each have multiple asks and zero connector rows.", warn=True) if never_routed else finding("Every company in the top 20 has been routed at least once.", "No repeat company is still waiting for its first ask.")}
      {finding("Unresolvable asks cluster too.", f"{unresolvable_asks} of the {n_req} requests on file resolve to no company at all: " + "; ".join(f'{b["requests"]} {b["name"].strip("()")}' for b in demand["unresolvable"]) + ". They sit at the bottom of the detail table and are excluded from the company counts above.")}
    </div>
  </div>
  <h3>Per-company detail</h3>
  <p class="foot">Paths in network = distinct ways to reach the company in <code>golden/supply_reach.csv</code>.</p>
  {demand_table}
  <h3>Top 20 accounts by value</h3>
  <p class="lede">Value is the company's one $, the rule every $ on these pages follows: the CRM <code>arr_potential_usd</code> where the company has a CRM account, otherwise the <code>deal_value_usd</code> on its latest request that carries one. Internal touchpoints are split into roster connectors employed internally versus advisors and investors.</p>
  {top_table}
</section>
{SEG_SCRIPT}
"""

    # requesters
    requesters = data_cuts.requester_cut(data)
    req_rows = requesters["requesters"]
    n_sdr, n_ae = sum(1 for b in req_rows if b["kind"] == "SDR"), sum(1 for b in req_rows if b["kind"] == "AE")
    req_asks_div = requester_chart(req_rows,
        [dict(y=[b["requests"] for b in req_rows], marker_color=theme.ACCENT, text=[b["requests"] for b in req_rows],
              textposition="outside", customdata=[b["routed"] for b in req_rows],
              hovertemplate="%{y} requests<br>%{customdata} routed to a connector<extra></extra>")],
        "req-asks", "requests")
    req_value_div = requester_chart(req_rows,
        [dict(y=[b["value"] for b in req_rows], marker_color=theme.ACCENT, text=[usd(b["value"]) for b in req_rows],
              textposition="outside", customdata=[[b["accounts"], b["crm_accounts"]] for b in req_rows],
              hovertemplate="$%{y:,.0f} across %{customdata[0]} companies<br>%{customdata[1]} of them at CRM ARR potential<extra></extra>")],
        "req-value", "value, one $ per company", tickformat="$~s")
    req_accounts_div = requester_chart(req_rows,
        [dict(y=[b["crm_accounts"] for b in req_rows], name="With a CRM account", marker_color=theme.ACCENT,
              hovertemplate="%{y} accounts in the CRM<extra></extra>"),
         dict(y=[b["accounts"] - b["crm_accounts"] for b in req_rows], name="No CRM record", marker_color=theme.NEUTRAL,
              text=[b["accounts"] for b in req_rows], textposition="outside", cliponaxis=False,
              hovertemplate="%{y} companies with no CRM record<extra></extra>")],
        "req-accounts", "distinct companies", barmode="stack")
    req_rate_div = requester_chart(req_rows,
        [dict(y=[b["intro_rate"] for b in req_rows], marker_color=theme.ACCENT, text=[f'{b["intro_rate"]:.0%}' for b in req_rows],
              textposition="outside", customdata=[[b["intros"], b["requests"]] for b in req_rows],
              hovertemplate="%{customdata[0]} intros / %{customdata[1]} requests<extra></extra>")],
        "req-rate", "intros / requests", tickformat=".0%")
    req_urgency_div = requester_chart(req_rows,
        [dict(y=[b["critical_share"] for b in req_rows], name="Critical", marker_color=theme.WARN,
              text=[f'{b["critical_share"]:.0%}' for b in req_rows], textposition="outside",
              customdata=[[b["critical"], b["requests"]] for b in req_rows],
              hovertemplate="Critical on %{customdata[0]} of %{customdata[1]} requests<extra></extra>"),
         dict(y=[b["critical_high_share"] for b in req_rows], name="Critical + High", marker_color=theme.NEUTRAL_DARK,
              text=[f'{b["critical_high_share"]:.0%}' for b in req_rows], textposition="outside",
              customdata=[[b["critical_high"], b["requests"]] for b in req_rows],
              hovertemplate="Critical or High on %{customdata[0]} of %{customdata[1]} requests<extra></extra>")],
        "req-urgency", "share of own requests", tickformat=".0%")
    requester_table = table(["Requester", "Role", "Asks", "Routed", "Intros", "Intro rate", "Accounts", "In CRM",
                             "Value", "Critical", "Critical + High"],
                            [(b["name"], b["role"], b["requests"], b["routed"], b["intros"], f'{b["intro_rate"]:.0%}',
                              b["accounts"], b["crm_accounts"], usd(b["value"]),
                              f'{b["critical"]} ({b["critical_share"]:.0%})', f'{b["critical_high"]} ({b["critical_high_share"]:.0%})')
                             for b in req_rows])
    req_top = req_rows[0]
    req_best_rate = max(req_rows, key=lambda b: b["intro_rate"])
    req_worst_rate = min(req_rows, key=lambda b: b["intro_rate"])
    req_most_critical = max(req_rows, key=lambda b: b["critical_share"])
    req_least_critical = min(req_rows, key=lambda b: b["critical_share"])
    req_most_value = max(req_rows, key=lambda b: b["value"])
    req_unresolved = sum(b["unresolved"] for b in req_rows)
    req_title = "The SDR and the Seven AEs" if not live and (n_sdr, n_ae) == (1, 7) else f"{n_sdr} SDR{'s' if n_sdr != 1 else ''} and {n_ae} AE{'s' if n_ae != 1 else ''}"
    requesters_html = f"""
<section id="requesters">
  <h2>Requesters: {req_title}</h2>
  <p class="lede">Every request on file grouped by <code>requested_by</code>, in order of asks. Accounts are the distinct companies behind a requester's asks after entity resolution, so asking twice for the same company counts one account and its one $ once (CRM <code>arr_potential_usd</code> where it has an account, else the <code>deal_value_usd</code> on its latest request). Intro rate is intros sent over every request filed, routed or not. Urgency is what the requester declared in <code>urgency</code>.</p>
  <div class="kpis">
    {kpi(len(req_rows), "requesters", f"{n_sdr} SDR · {n_ae} AEs")}
    {kpi(f"{req_top['requests']}", f"asks from {req_top['name']}", f"{pct(req_top['requests'], requesters['requests'])} of the {requesters['requests']} requests on file, the most of anyone")}
    {kpi(f"{requesters['intro_rate']:.0%}", "intro rate across every requester", f"{requesters['intros']} intros / {requesters['requests']} requests on file · {req_best_rate['intro_rate']:.0%} ({req_best_rate['name']}) to {req_worst_rate['intro_rate']:.0%} ({req_worst_rate['name']})")}
    {kpi(f"{requesters['critical_share']:.0%}", "of requests declared Critical", f"{requesters['critical_high_share']:.0%} Critical or High")}
  </div>
  <div class="grid2">
    <div>
      <h3>Cumulative asks per requester</h3>
      {req_asks_div}
    </div>
    <div>
      <h3>Value per requester</h3>
      {req_value_div}
      <p class="foot">One $ per distinct company each requester asked for: CRM <code>arr_potential_usd</code> where it has an account, otherwise its latest <code>deal_value_usd</code>; a company with neither contributes nothing.</p>
    </div>
  </div>
  <div class="grid2">
    <div>
      <h3>Accounts per requester</h3>
      {req_accounts_div}
    </div>
    <div>
      <h3>Intro rate per requester</h3>
      {req_rate_div}
    </div>
  </div>
  <div class="grid2">
    <div>
      <h3>How often they declare Critical, and Critical or High</h3>
      {req_urgency_div}
    </div>
    <div>
      <h3>Reading it</h3>
      {finding("Who files the asks.", f"{req_top['name']} ({req_top['kind']}) files the most at {req_top['requests']}, {req_rows[-1]['name']} the fewest at {req_rows[-1]['requests']}; {req_rows[0]['requests'] - req_rows[-1]['requests']} requests separate the top from the bottom of {len(req_rows)} people, over the {n_req} requests on file.")}
      {finding("Where the value sits.", f"{req_most_value['name']} carries the most at {usd(req_most_value['value'])} across {req_most_value['accounts']} companies ({req_most_value['crm_accounts']} in the CRM). The bars overlap: {requesters['shared_accounts']} of the {requesters['accounts']} companies requested were asked for by more than one person, so the same company's $ appears under each of them; de-duplicated, {usd(requesters['value'])} sits behind the {requesters['accounts']} companies ({requesters['crm_accounts']} with a CRM account). {req_unresolved} of the {n_req} requests on file resolve to no company and count toward asks only.")}
      {finding(f"Intro rate ranges from {req_worst_rate['intro_rate']:.0%} to {req_best_rate['intro_rate']:.0%}.", f"{req_best_rate['name']} lands {req_best_rate['intros']} intros from their {req_best_rate['requests']} requests of the {n_req} on file; {req_worst_rate['name']} lands {req_worst_rate['intros']} from their {req_worst_rate['requests']}. The whole floor averages {requesters['intro_rate']:.0%}.", warn=True)}
      {finding("Critical means different things to different people.", f"{req_most_critical['name']} marks {req_most_critical['critical_share']:.0%} of their asks Critical, {req_least_critical['name']} {req_least_critical['critical_share']:.0%}. Add High and {requesters['critical_high_share']:.0%} of all requests are in the top two tiers, so urgency barely separates one ask from the next.", warn=True)}
    </div>
  </div>
  <h3>Per requester</h3>
  {requester_table}
</section>
"""

    # connectors
    cx = data_cuts.connector_cut(data)
    cs = cx["connectors"]
    by_name = {c["name"]: c for c in cs}
    connector_table = table(["Connector", "Type", "Capacity/mo", "Asked", "Responded", "Intros", "Meetings",
                             "Opps", "Requested $", "Opp $", "In focus area", "Stated focus", "Roster note"],
                            [(c["name"], c["type"], c["capacity"], c["asked"], c["responded"], c["intros"],
                              c["meetings"], c["opps"], usd(c["value"]), usd(c["opp_value"]),
                              f'{c["in_focus"]}/{c["asked"]}', c["focus_areas"], c["notes"]) for c in cs])
    return_table = table(["#", "Connector", "Asks", "Intros", "Opps", "Opp $", "Per ask $", "Per intro $"],
                         [(i + 1, c["name"], c["asked"], c["intros"], c["opps"], usd(c["opp_value"]), usd(c["opp_per_ask"]), usd(c["opp_per_intro"]))
                          for i, c in enumerate(cx["by_return"])])
    busiest = cs[0] if cs else {"asked": 0, "name": "—"}
    sept_names = ("Owen Trask", "Dana Whitfield", "Elena Duvall", "Marcus Aldridge", "Tomás Beckett")
    if not live and all(n in by_name for n in sept_names):
        owen, dana, elena, marcus, tomas = (by_name[n] for n in sept_names)
        left = finding("The notes predicted the failures.", f'Owen Trask ("tapped no more than twice a month") was asked {owen["asked"]} times in {cx["months"]} months and sent zero intros; Dana Whitfield ("travels constantly; slow to respond") got {dana["asked"]} asks and booked no meetings.', warn=True)
        right_title = "Where the notes were right"
        right = (finding('Elena Duvall, "deep but narrow".', f'{elena["in_focus"]} of her {elena["asked"]} asks were heavy industry, and that is where her intros came from.')
                 + finding('Marcus Aldridge, "asked far more than anyone else", capacity 4/month.', f'{marcus["asked"]} asks with the weakest response rate of the four heavily-used connectors ({pct(marcus["responded"], marcus["asked"])}).')
                 + finding('Tomás Beckett, "fast responder, broad but shallow".', f'{pct(tomas["responded"], tomas["asked"])} response rate but only {pct(tomas["intros"], tomas["responded"])} of those responses became an intro.'))
    else:
        asked_cs = [c for c in cs if c["asked"]]
        silent = [c for c in asked_cs if not c["intros"]]
        best_resp = max(asked_cs, key=lambda c: c["responded"] / c["asked"]) if asked_cs else None
        best_intro = max(asked_cs, key=lambda c: c["intros"] / c["asked"]) if asked_cs else None
        idle = [c for c in cs if not c["asked"]]
        left = (finding("Asked and never delivered.", f'{names_list(c["name"] for c in silent)} took {sum(c["asked"] for c in silent)} asks between them and sent no intro.', warn=True) if silent
                else finding("Every connector asked has delivered at least once.", "No roster connector is carrying asks with nothing to show for them."))
        if idle:
            left += finding("Capacity nobody uses.", f'{names_list(c["name"] for c in idle)} ({sum(c["capacity"] for c in idle)} stated slots a month) have not been asked at all.')
        right_title = "Who converts"
        right = ((finding(f'{best_resp["name"]} answers most reliably.', f'{pct(best_resp["responded"], best_resp["asked"])} of {best_resp["asked"]} asks got a response.') if best_resp else "")
                 + (finding(f'{best_intro["name"]} turns asks into intros most often.', f'{best_intro["intros"]} intros from {best_intro["asked"]} asks ({pct(best_intro["intros"], best_intro["asked"])}); the roster as a whole lands {pct(sum(c["intros"] for c in cs), cx["asked"])}.') if best_intro else "")
                 + finding(f'{busiest["name"]} carries the most.', f'{busiest["asked"]} asks against a stated capacity of {busiest["capacity"]} a month over {cx["months"]} months; the rest of the roster shares {cx["asked"] - busiest["asked"]}.'))
    connectors_html = f"""
<section id="connectors">
  <h2>Connectors: The {len(cs)} on the Roster</h2>
  <p class="lede">Funnel per connector from {ask_log}, with the stated capacity and free-text note from <code>dataset/connector_roster.csv</code>. An ask is "in focus area" when the resolved company's CRM industry is one of the connector's stated focus areas.</p>
  <div class="kpis">
    {kpi(f"{cx['in_focus']} / {cx['asked']}", "asks inside the stated focus area", f"over {cx['months']} months")}
    {kpi(f"{cx['in_focus_intro_rate']:.0%}", "intro rate for in-focus asks", f"vs {cx['off_focus_intro_rate']:.0%} outside the focus area")}
    {kpi(f"{busiest['asked']}", f"asks to {busiest['name']}", "the most-asked connector")}
    {kpi(sum(n for _, n in cx["off_roster"]), "asks to people not on the roster", ", ".join(n for n, _ in cx["off_roster"]) or "everyone asked is on the roster")}
  </div>
  {connector_table}
  <h3>Ranked by return per ask</h3>
  <p class="lede">The value of the companies a connector's asks turned into opportunities (one $ per company, CRM ARR potential else latest deal value), divided by the asks; the roster as a whole returns {usd(cx["opp_value"] / cx["asked"] if cx["asked"] else 0)} per ask.</p>
  <div class="grid2">
    <div>{return_chart(cx["by_return"], "connector-return")}</div>
    <div>{return_table}</div>
  </div>
  <div class="grid2">
    <div>
      <h3>Routing ignores the roster notes</h3>
      {finding(f"Only {cx['in_focus']} of {cx['asked']} asks land in a stated focus area, and those convert at {cx['in_focus_intro_rate']:.0%} vs {cx['off_focus_intro_rate']:.0%}.", "Focus area is the single strongest predictor of an intro in this data, and it is almost never used when choosing who to ask.", warn=True)}
      {left}
    </div>
    <div>
      <h3>{right_title}</h3>
      {right}
    </div>
  </div>
</section>
"""

    # cycles
    cyc_rows = cyc["rows"]
    closed = [r for r in cyc_rows if not r["current"]]
    now = cyc["current"]
    avg_pct = sum(r["capacity_pct"] or 0 for r in closed) / len(closed) if closed else 0
    busiest_pct = max((r["capacity_pct"] or 0 for r in closed), default=0)
    before = ([r for r in cyc_rows if r["cycle"] < now["cycle"]] or [None])[-1]
    if live:
        cyc_lede = (f'Every connector summed, one row per cycle (a calendar month, the allocator\'s unit) from the first ask on file to the current cycle {cyc["cycle"]}. '
                    f'Asks by <code>asked_date</code> and intros by <code>intro_date</code> from {ask_log}; capacity used is roster asks against the roster\'s stated monthly capacity of {cyc["roster_capacity"]} in <code>connector_roster.csv</code>. '
                    f'The current cycle counts this build\'s allocation as slots used, since those asks are about to go out. Each connector\'s own record is on their tab under Live Priorities.')
        now_label, now_sub = "intros made this cycle", f"{cyc['cycle']} · {before['intros'] if before else 0} in {before['cycle'] if before else 'the cycle before'}"
        cap_label = "roster capacity used this cycle"
        closed_word = "closed cycles"
        fill = ("This cycle's allocation is the first to fill it." if (now["capacity_pct"] or 0) >= 1
                else f"This cycle's allocation takes it to {now['capacity_pct'] or 0:.0%}.")
    else:
        cyc_lede = (f'Every connector summed, one row per calendar month from the first ask on file to the last month the exports touch, {cyc["cycle"]}. '
                    f'Asks by <code>asked_date</code> and intros by <code>intro_date</code> from <code>intro_outcomes.csv</code> as filed; capacity used is roster asks against the roster\'s stated monthly capacity of {cyc["roster_capacity"]} in <code>connector_roster.csv</code>. '
                    f'Nothing is allocated here: the <a href="{LIVE_HTML}">Live Data Dashboard</a> adds the current cycle\'s allocation and the asks sent since.')
        now_label, now_sub = f"intros made in {cyc['cycle']}", f"the last month on file · {before['intros'] if before else 0} in {before['cycle'] if before else 'the month before'}"
        cap_label = f"roster capacity used in {cyc['cycle']}"
        closed_word = "months"
        fill = ""
    cycles_html = f"""
<section id="cycles">
  <h2>Intros by Cycle</h2>
  <p class="lede">{cyc_lede}</p>
  <div class="kpis">
    {kpi(now["intros"], now_label, now_sub)}
    {kpi(cyc["intros_total"], "cumulative intros", f"since {cyc_rows[0]['cycle'] if cyc_rows else '—'}, from {cyc['asks_total']} asks")}
    {kpi(f"{now['capacity_pct'] or 0:.0%}", cap_label, f"{now['used']} of {cyc['roster_capacity']} slots" + (f" · {now['allocated_off_roster']} more allocated off-roster" if now.get('allocated_off_roster') else ""))}
    {kpi(f"{avg_pct:.0%}", "capacity used per cycle, to date", f"average over {len(closed)} {closed_word}; best month {cyc['best']['cycle']} with {cyc['best']['intros']} intros")}
  </div>
  {cycle_chart(cyc_rows, "cycles-chart")}
  <div class="grid2">
    <div>
      <h3>By cycle, all connectors</h3>
      {cycle_table(cyc_rows)}
    </div>
    <div>
      <h3>Reading it</h3>
      {finding(f"{closed_word.capitalize()} on file used {avg_pct:.0%} of roster capacity.", f"That is the average against {cyc['roster_capacity']} stated monthly slots; the busiest month used {busiest_pct:.0%}. {fill}".strip(), warn=True)}
      {finding(f"Intros arrive at roughly {cyc['intros_total'] / max(1, len(closed)):.1f} a month.", f"{cyc['intros_total']} intros over {len(closed)} {closed_word} from {cyc['asks_total']} asks, about one intro per {cyc['asks_total'] / max(1, cyc['intros_total']):.1f} asks. The cumulative line is the honest read; single months swing between {min((r['intros'] for r in closed), default=0)} and {max((r['intros'] for r in closed), default=0)}.")}
      <p class="foot">Asks to people off the roster ({", ".join(cyc['off_roster']) or "none so far"}) are counted in asks and intros but not against capacity, as they have none stated.</p>
    </div>
  </div>
  <h3>Per connector, {"this cycle" if live else cyc["cycle"]} and the run rate</h3>
  {cycle_connector_table(cyc)}
  <p class="foot">Run-rate columns average every cycle since {cyc_rows[0]['cycle'] if cyc_rows else '—'}; capacity used per cycle averages {closed_word} {"before this one" if live else "on file"}. Click a connector's tab for their cycle-by-cycle table.</p>
</section>
"""
    # latency
    lat = data_cuts.latency_cut(data)
    unrouted = data_cuts.blockage_cut(data)
    allocated, on_file = unrouted["allocated"], unrouted["total"]
    lat_rows = [(m["month"], m["requests"], m["asked"], days(m["to_ask"]), days(m["to_resp"]), days(m["to_intro"])) for m in lat["monthly"]]
    lat_table = table(["Month requested", "Requests", "Asked", "Request to ask", "Ask to response", "Ask to intro"], lat_rows)
    with_data = [m for m in lat["monthly"] if m["to_ask"] is not None]
    first_half, second_half = with_data[:len(with_data) // 2], with_data[len(with_data) // 2:]
    trend = ""
    if first_half and second_half:
        early = statistics.median(m["to_intro"] for m in first_half if m["to_intro"] is not None) if any(m["to_intro"] is not None for m in first_half) else None
        late = statistics.median(m["to_intro"] for m in second_half if m["to_intro"] is not None) if any(m["to_intro"] is not None for m in second_half) else None
        if early is not None and late is not None:
            trend = finding("Ask to intro month over month.", f"Median {days(early)} across the first {len(first_half)} months with asks ({first_half[0]['month']} to {first_half[-1]['month']}), {days(late)} across the last {len(second_half)} ({second_half[0]['month']} to {second_half[-1]['month']}); single months swing between {days(min(m['to_intro'] for m in with_data if m['to_intro'] is not None))} and {days(max(m['to_intro'] for m in with_data if m['to_intro'] is not None))}.")
    latency_html = f"""
<section id="latency">
  <h2>Latency</h2>
  <p class="lede">Days between the steps, from <code>request_date</code> and the dates in {ask_log}: request to ask, ask to the first response, ask to the intro going out. Medians, since a few slow intros pull the mean.</p>
  <div class="kpis">
    {kpi(days(lat["median_to_ask"]), "median request to ask", f"over {lat['asks']} asks")}
    {kpi(days(lat["median_to_resp"]), "median ask to first response")}
    {kpi(days(lat["median_to_intro"]), "median ask to intro")}
    {kpi(f"{lat['max_to_ask']} d", "longest a request waited before it was asked", f"{lat['waiting_past_max']} of {on_file} requests on file are unasked and already older than that")}
  </div>
  {latency_chart(lat["monthly"], "latency-chart")}
  <div class="grid2">
    <div>
      <h3>By month requested</h3>
      {lat_table}
    </div>
    <div>
      <h3>Reading it</h3>
      {finding("A request not asked inside a week is never asked.", f"Every one of the {lat['asks']} asks on file went out within {lat['max_to_ask']} days of the request ({lat['asked_within_week']} of {lat['asks']} inside seven); the {lat['waiting_past_max']} of the {on_file} requests on file still unasked are all older than that and, on this record, will stay unasked unless someone picks them up; {allocated} of them are allocated this cycle.", warn=True)}
      {trend}
      <p class="foot">Code: <code>dashboard/data_cuts.py</code> (<code>latency_cut</code>). A month's medians cover the requests filed that month, whenever the ask, response or intro happened.</p>
    </div>
  </div>
</section>
"""
    return funnel + accounts + requesters_html + connectors_html + latency_html + cycles_html


dup_table = table(["Reply text", "Occurrences"], [(text, n) for text, n in slack["dup_phrases"]])

flag_order = ["Path found", "No path found", "Unknown", "(blank)"]
status_order = ["Open", "Routed", "Intro sent", "Stalled", "Closed - no path"]
matrix_rows = [(flag, *[noise["cross"].get((flag, s), 0) for s in status_order], noise["flags"][flag])
               for flag in flag_order]
matrix_table = table(["path_found_flag", *status_order, "All"], matrix_rows)
reality_rows = [(flag, v["requests"], f'{v["paths"]/v["requests"]:.0%}', v["asked"],
                 f'{v["intros"]/v["requests"]:.0%}')
                for flag, v in ((f, noise["flag_reality"][f]) for f in flag_order)]
reality_table = table(["path_found_flag", "Requests", "Company has a path in the network", "Routed", "Intro rate"],
                      reality_rows)
contradiction_rows = "".join(f'<tr><td>{label}</td><td class="num">{n}</td></tr>'
                             for label, n in noise["contradictions"])
contradiction_table = ('<table><thead><tr><th>Contradiction</th><th class="num">Requests</th></tr></thead>'
                       f"<tbody>{contradiction_rows}</tbody></table>")

coverage_table = table(["Status in intro_requests.csv", "Requests with no outcome row"],
                       [(status, n) for status, n in coverage["by_status"]])

reply_div = plot(reply_fig, "replies")

STYLE = f"""<style>
:root{{--ink:{theme.INK};--mute:{theme.MUTE};--blue:{theme.ACCENT};--line:{theme.LINE};--bg:{theme.PAPER};--surface:{theme.SURFACE};--warn:{theme.WARN};--navy:{theme.NAVY};--baton:{theme.BATON};
  --serif:{theme.SERIF};--sans:{theme.SANS};--mono:{theme.MONO}}}
*{{box-sizing:border-box}}
body{{margin:0;font:16px/1.55 var(--serif);color:var(--ink);background:var(--bg);-webkit-font-smoothing:antialiased}}
h1,h2,h3,h4,nav,th,.kpi,.foot,summary{{font-family:var(--sans)}}
h1,h2,h3,h4{{font-weight:500;letter-spacing:-.01em}}
a{{color:var(--blue)}}
header{{background:var(--bg);border-bottom:1px solid var(--line);padding:32px 40px 28px}}
header h1{{margin:0 0 6px;font-size:34px;line-height:1.15;font-weight:400;letter-spacing:-.02em}}
header p{{margin:0;color:var(--mute)}}
nav a{{margin-right:18px;color:var(--ink);text-decoration:none;font-size:14px}}
nav a:hover{{color:var(--blue)}}
.part-lede{{margin-bottom:24px}}
main{{max-width:1240px;margin:0 auto;padding:28px 40px 72px}}
/* the left rail: a sticky list of the page's sections, highlighted as you scroll */
.layout{{display:grid;grid-template-columns:224px minmax(0,1fr);gap:0 36px;max-width:1560px;margin:0 auto;padding:0 40px;align-items:start}}
.layout>main{{max-width:none;margin:0;padding:28px 0 72px}}
.side{{position:sticky;top:var(--topbar,140px);max-height:calc(100vh - var(--topbar,140px));overflow-y:auto;padding:30px 0 40px;font-family:var(--sans);scrollbar-width:thin}}
.side .side-h{{margin:0 0 10px;font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--mute)}}
.side .side-h .foot{{font-weight:400;letter-spacing:0;text-transform:none;margin-left:6px;font-size:11.5px}}
.side input[type=search]{{width:100%;font:13px var(--sans);padding:7px 10px;margin:0 0 10px;border:1px solid var(--line);background:var(--surface);color:var(--ink);outline:none}}
.side input[type=search]:focus{{border-color:var(--blue)}}
.toc{{display:flex;flex-direction:column}}
.toc a{{display:block;margin:0;padding:5px 12px;border-left:2px solid var(--line);color:var(--mute);text-decoration:none;font-size:13.5px;line-height:1.35}}
.toc a:hover{{color:var(--ink)}}
.toc a.on{{color:var(--ink);border-left-color:var(--blue);font-weight:500}}
.toc a.band{{margin-top:14px;padding-left:0;border-left-color:transparent;font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--baton)}}
.toc a.band:first-child{{margin-top:0}}
.toc a .n{{float:right;margin-left:8px;color:var(--mute);font-size:11.5px;font-variant-numeric:tabular-nums}}
.toc .empty{{color:var(--mute);font-style:italic;font-size:13px;padding:5px 12px}}
/* long tables: 20 rows at a time, with a filter box; .tall tables scroll inside a fixed height instead */
.pager{{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;margin:10px 0 4px;font-family:var(--sans);font-size:12.5px;color:var(--mute)}}
.pager input{{font:inherit;padding:5px 9px;border:1px solid var(--line);background:var(--surface);color:var(--ink);min-width:170px}}
.pager input:focus{{outline:none;border-color:var(--blue)}}
.pager .pg-b{{display:inline-flex;gap:3px;align-items:center}}
.pager .pg-b span{{padding:0 4px}}
.pager button{{font:inherit;padding:4px 9px;border:1px solid var(--line);background:var(--surface);color:var(--ink);cursor:pointer;min-width:30px}}
.pager button.on{{background:var(--ink);color:var(--surface);border-color:var(--ink)}}
.pager button:disabled{{opacity:.4;cursor:default}}
.pager button.pg-all{{margin-left:auto}}
.pager button[hidden]{{display:none}}
.tscroll.tall{{max-height:min(70vh,640px);overflow-y:auto}}
.tscroll.tall thead th{{position:sticky;top:0;z-index:1;background:var(--surface);border-bottom-color:transparent;box-shadow:inset 0 -1px 0 var(--ink)}}
section{{background:var(--surface);border:1px solid var(--line);padding:28px 32px;margin:0 0 20px;scroll-margin-top:calc(var(--topbar,140px) + 16px)}}
/* the rule between the strategic sections and the data-integrity ones on the Raw Sept tab */
.divider{{margin:40px 0 20px;padding:14px 0 0;border-top:2px solid var(--baton);scroll-margin-top:calc(var(--topbar,140px) + 16px)}}
.divider .t{{display:block;font:600 11px/1.4 var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--baton)}}
.divider p{{margin:6px 0 0;color:var(--mute);font-size:15px;max-width:76ch}}
h2{{margin:0 0 6px;font-size:22px}}
h3{{margin:28px 0 10px;font-size:12px;font-weight:500;color:var(--mute);text-transform:uppercase;letter-spacing:.08em}}
h3 .foot{{font-weight:400;text-transform:none;letter-spacing:0;margin-left:6px}}
h3 code{{text-transform:none;letter-spacing:0;font-size:11.5px}}
details{{margin-top:26px}}
summary{{cursor:pointer;list-style:none;margin-bottom:10px}}
summary::-webkit-details-marker{{display:none}}
summary::before{{content:"+ ";color:var(--mute)}}
details[open] summary::before{{content:"− "}}
.lede{{color:var(--mute);margin:0 0 18px;font-size:17px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:1px;margin:12px 0 6px;background:var(--line);border:1px solid var(--line)}}
.kpi{{background:var(--surface);padding:16px 18px 14px}}
.kpi .v{{font-size:30px;font-weight:400;color:var(--ink);line-height:1.1;letter-spacing:-.02em;font-variant-numeric:tabular-nums}}
.kpi.warn .v{{color:var(--warn)}}
.kpi .v.words{{font-size:20px;padding-top:6px;color:var(--mute)}}
.kpi .l{{margin-top:6px;font-weight:500;font-size:13px}}
.kpi .l::first-letter,.kpi .s::first-letter,.strip .l::first-letter,.empty::first-letter{{text-transform:uppercase}}
.kpi .s{{color:var(--mute);font-size:12px;margin-top:2px}}
table{{border-collapse:collapse;width:100%;font-size:14px;font-family:var(--sans);font-variant-numeric:tabular-nums}}
.tscroll{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--mute);font-weight:500;font-size:12.5px;border-bottom-color:var(--ink)}}
td:nth-child(n+2):not(:last-child).num,th.num{{text-align:right}}
.fo th,.fo td{{padding:6px 10px}}
.fo td.num,.fo th.num{{text-align:right}}
.fo tr.total td{{font-weight:600;border-top:1px solid var(--ink)}}
.fo tr.ratio td{{color:var(--mute);border-bottom:none;padding-top:10px}}
.fo tr.ratio td.num{{color:var(--ink);font-weight:600}}
table.cycles td.num,table.cycles th.num{{text-align:right;white-space:nowrap}}
table.inflight td.num,table.inflight th.num{{text-align:right;white-space:nowrap}}
table.inflight tr.group th{{color:var(--ink);font-weight:600;font-size:13px;padding-top:18px;border-bottom-color:var(--line)}}
table.inflight tr.group th .foot{{font-weight:400;margin-left:6px}}
table.inflight tr.total th{{color:var(--ink);font-weight:600;font-size:14px;border-top:1px solid var(--ink);border-bottom:none}}
table.cycles td.date{{font-family:var(--mono);font-size:12.5px;white-space:nowrap}}
table.cycles tr.now td{{background:{theme.rgba(theme.BATON, 0.08)};font-weight:500}}
table.cycles tr.now td .foot{{font-weight:400}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:32px}}
.grid2>*{{min-width:0}}
@media(max-width:900px){{.grid2{{grid-template-columns:1fr}}}}
@media(max-width:1100px){{
  .layout{{display:block;padding:0}}
  .layout>main{{padding:24px 40px 72px}}
  .side{{position:static;max-height:none;overflow:visible;padding:12px 40px 0;border-bottom:1px solid var(--line);background:var(--bg)}}
  .side .side-h{{display:none}}
  .side input[type=search]{{max-width:360px}}
  .toc{{flex-direction:row;flex-wrap:nowrap;overflow-x:auto;gap:2px;scrollbar-width:none}}
  .toc::-webkit-scrollbar{{display:none}}
  .toc a{{flex:none;white-space:nowrap;border-left:0;border-bottom:2px solid transparent;padding:6px 10px}}
  .toc a.on{{border-bottom-color:var(--blue)}}
  .toc a.band{{margin:0 0 0 12px;padding:8px 6px 6px 0}}
  .toc a.band:first-child{{margin-left:0}}
  .toc a .n{{float:none}}
}}
.finding{{border-left:2px solid var(--blue);padding:6px 16px;margin:12px 0;background:var(--bg)}}
.finding.warn{{border-color:var(--warn)}}
.finding b{{display:block;font-family:var(--sans);font-weight:500;font-size:14px;margin-bottom:2px}}
.foot{{color:var(--mute);font-size:13px}}
code{{font-family:var(--mono);background:rgba(0,0,0,.04);padding:1px 5px;font-size:12.5px}}
img{{max-width:100%}}
.topbar{{position:sticky;top:0;z-index:10;background:var(--bg)}}
.mastrow{{display:flex;align-items:center;justify-content:space-between;gap:8px 28px;padding:10px 40px 8px;border-bottom:1px solid var(--line);background:var(--surface)}}
.mastrow .built{{font-family:var(--sans);font-size:12px;color:var(--mute);white-space:nowrap}}
.mast{{display:flex;align-items:center;gap:12px;text-decoration:none;color:var(--ink)}}
.mast .logo{{flex:none;display:block}}
.mast .t{{font-family:var(--sans);font-size:17px;line-height:1.2;letter-spacing:-.01em;color:var(--mute);white-space:nowrap}}
.mast .t b{{font-weight:600;color:var(--navy)}}
.tabs{{display:flex;flex-wrap:wrap;justify-content:flex-start;gap:4px;padding:6px 40px 0;border-bottom:1px solid var(--line)}}
.tabs a{{font-family:var(--sans);font-size:14px;color:var(--mute);text-decoration:none;padding:8px 16px;margin-bottom:-1px;border:1px solid transparent}}
.tabs a:hover{{color:var(--ink)}}
.tabs a.on{{color:var(--ink);background:var(--surface);border-color:var(--line) var(--line) var(--surface)}}
.tabs a.parent{{color:var(--ink);border-color:{theme.rgba(theme.BATON, 0.35)} {theme.rgba(theme.BATON, 0.35)} transparent;background:{theme.rgba(theme.BATON, 0.08)}}}
.tabs.people{{padding:4px 40px 0;background:{theme.rgba(theme.BATON, 0.08)};border-bottom:1px solid {theme.rgba(theme.BATON, 0.35)}}}
.tabs.people .lbl{{font-family:var(--sans);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--baton);padding:10px 12px 0 0}}
.tabs.people a{{color:#7a4520;font-size:13.5px;padding:7px 13px}}
.tabs.people a .n{{margin-left:6px;font-size:11.5px;color:var(--baton);font-variant-numeric:tabular-nums}}
.tabs.people a:hover{{color:var(--navy)}}
.tabs.people a.on{{color:var(--navy);background:var(--surface);border-color:{theme.rgba(theme.BATON, 0.35)} {theme.rgba(theme.BATON, 0.35)} var(--surface);box-shadow:inset 0 2px 0 var(--baton)}}
.totop{{position:fixed;right:28px;bottom:28px;z-index:20;width:44px;height:44px;border:1px solid var(--ink);background:var(--surface);color:var(--ink);font:20px/1 var(--sans);cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.12);opacity:0;visibility:hidden;transform:translateY(8px);transition:opacity .2s,transform .2s,visibility .2s}}
.totop.show{{opacity:1;visibility:visible;transform:none}}
.totop:hover{{background:var(--ink);color:var(--surface)}}
.seg{{display:inline-flex;border:1px solid var(--line);font-family:var(--sans);font-size:13px;margin:6px 0 4px}}
.seg button{{background:var(--surface);color:var(--mute);border:0;padding:6px 14px;cursor:pointer;font:inherit}}
.seg button+button{{border-left:1px solid var(--line)}}
.seg button.on{{background:var(--ink);color:var(--surface)}}
.fview[hidden]{{display:none}}
/* live priorities */
nav.bands{{display:flex;flex-wrap:wrap;gap:6px 28px;margin-top:14px}}
nav.bands .grp{{display:inline-flex;flex-wrap:wrap;align-items:baseline;gap:0 14px}}
nav.bands a{{margin:0}}
nav.bands a.band{{font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--mute)}}
#lp .band{{margin:0 0 36px;scroll-margin-top:calc(var(--topbar,140px) + 16px)}}
#lp .band-h{{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 14px;margin:0 0 12px;padding:0 0 8px;border-bottom:2px solid var(--ink);font-family:var(--sans)}}
#lp .band-h .t{{font-size:18px;font-weight:500;letter-spacing:-.01em}}
#lp section.masthead{{padding:14px 18px 10px}}
#lp .masthead .strip{{margin:0}}
#lp .masthead .strip .cell{{padding:10px 12px 8px}}
#lp .masthead .strip .v{{font-size:20px}}
#lp .masthead .strip .n{{font-size:12px}}
#lp .masthead .strip .l{{margin-top:4px;font-size:12px}}
#lp .masthead details.note{{margin:8px 0 0}}
#lp .masthead details.note summary{{margin:0;font-size:12.5px;color:var(--mute)}}
#lp .masthead details.note p{{margin:6px 0 0}}
#lp h2 .foot{{display:block;font-weight:400;margin-top:2px}}
#lp details.fold{{margin:0}}
#lp .fold>summary{{display:flex;align-items:flex-start;gap:16px;margin:0}}
#lp .fold>summary::before{{content:none}}
#lp .fold>summary h2{{flex:1}}
#lp .fold>summary::after{{content:"▾";color:var(--mute);font-size:24px;line-height:1.1;padding-top:2px;transform:rotate(-90deg);transition:transform .15s}}
#lp .fold[open]>summary::after{{transform:none}}
#lp .fold>summary:hover::after{{color:var(--ink)}}
#lp .fold[open]>summary{{margin-bottom:6px}}
#lp q{{quotes:"\\201C" "\\201D";font-family:var(--serif);font-style:italic}}
#lp b.warn,#lp .warn{{color:var(--warn)}}
#lp td.rid,#lp td.date{{font-family:var(--mono);font-size:12.5px;white-space:nowrap}}
#lp .empty{{color:var(--mute);font-style:italic;margin:0}}
#lp .drop{{border:1px dashed var(--mute);padding:26px;text-align:center;color:var(--mute);cursor:pointer;font-family:var(--sans);font-size:14px;background:var(--bg);position:relative}}
#lp .drop.over{{border-color:var(--blue);color:var(--blue)}}
#lp .drop input{{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%}}
#lp .strip{{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:var(--line);border:1px solid var(--line);margin:14px 0 8px}}
#lp .strip .cell{{background:var(--surface);padding:14px 16px 12px;font-family:var(--sans)}}
#lp .strip .v{{font-size:26px;letter-spacing:-.02em;font-variant-numeric:tabular-nums}}
#lp .strip .n{{color:var(--mute);font-size:12.5px;margin-top:2px}}
#lp .strip .l{{margin-top:8px;font-size:13px;font-weight:500;color:var(--ink)}}
@media(max-width:900px){{#lp .strip{{grid-template-columns:repeat(3,1fr)}}}}
#lp table.top td.order{{color:var(--mute)}}
#lp table.top td.ev{{font-size:18px;font-weight:500;color:var(--blue)}}
/* the ranked queue: roomier rows, the rank and the expected value carry the eye, the arithmetic sits quietly under each score */
#lp table.prio{{font-size:14.5px;line-height:1.4}}
#lp table.prio th{{padding:10px 12px 12px;font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;vertical-align:bottom;white-space:nowrap}}
#lp table.prio th .fm{{display:block;margin-top:3px;font-size:11px;letter-spacing:0;text-transform:none;white-space:normal;max-width:130px}}
#lp table.prio td{{padding:18px 12px}}
#lp table.prio th:first-child,#lp table.prio td:first-child{{padding-right:2px;width:24px}}
#lp table.prio td.order{{font-size:20px;font-weight:500;line-height:1.1;letter-spacing:-.02em;width:26px}}
#lp table.prio td.co{{min-width:230px}}
#lp table.prio td.co a{{font-size:16px;font-weight:500}}
#lp table.prio .rid{{font-family:var(--mono);font-size:12px}}
#lp table.prio td.who{{min-width:120px}}
#lp table.prio td.via{{min-width:150px}}
#lp table.prio td.ev{{font-size:22px;line-height:1.1;letter-spacing:-.02em;white-space:nowrap}}
#lp table.prio td.parts{{min-width:130px}}
#lp table.prio td.parts b{{display:block;font-size:16px;line-height:1.1}}
#lp table.prio td.parts .math{{display:block;margin-top:5px;font-size:12px;color:var(--mute);white-space:nowrap}}
#lp table.prio td.parts .foot{{display:block;margin-top:3px;font-size:12px}}
#lp table.prio .notify{{margin-top:8px;white-space:normal;max-width:300px}}
#lp table.prio tbody tr:hover td{{background:var(--bg)}}
#lp table.prio tr.done td{{text-decoration:none}}
#lp table.prio tr.done td.order,#lp table.prio tr.done td.co a{{text-decoration:line-through}}
#lp tr.done td{{color:var(--mute);text-decoration:line-through}}
#lp table.top tr.done td.ev{{color:var(--mute)}}
#lp table.top tr.quiet td{{color:var(--mute)}}
#lp table.top tr.owned td{{color:var(--mute)}}
#lp .tick{{width:16px;height:16px;accent-color:var(--blue)}}
#lp .sent{{display:none}}
#lp tr.done .sent{{display:inline-block;color:var(--blue);font-weight:500}}
#lp td.pick{{white-space:nowrap}}
#lp td.pick .tick{{vertical-align:middle;margin-right:6px}}
#lp td.pick select{{font-family:var(--sans);font-size:13px;color:var(--ink);background:var(--surface);border:1px solid var(--line);padding:4px 6px;max-width:190px}}
#lp td.pick select.need{{border-color:var(--warn)}}
#lp td.pick .pick-note{{display:block;margin-top:3px;white-space:normal;max-width:220px}}
#lp .parts .c,#lp table.preview .c{{border-bottom:1px dotted var(--mute);cursor:help}}
#lp th .fm{{font-weight:400;font-size:11px;text-transform:none;letter-spacing:0}}
#lp .formula{{margin-top:14px;padding:12px 16px;background:var(--bg);border-left:2px solid var(--blue)}}
#lp .formula p{{margin:0 0 6px}}
#lp .subtabs{{display:flex;flex-wrap:wrap;gap:4px;margin:12px 0 18px;border-bottom:1px solid var(--line)}}
#lp .subtabs button{{font-family:var(--sans);font-size:14px;color:var(--mute);background:none;border:1px solid transparent;padding:8px 14px;margin-bottom:-1px;cursor:pointer}}
#lp .subtabs button .n{{margin-left:8px;font-size:12px;color:var(--mute);font-variant-numeric:tabular-nums}}
#lp .subtabs button.on{{color:var(--ink);background:var(--surface);border-color:var(--line) var(--line) var(--surface)}}
#lp .subtabs button.agg{{margin-left:auto;color:var(--baton);font-weight:500}}
#lp .subtabs button.agg .n{{color:var(--baton)}}
#lp .subtabs button.agg.on{{color:var(--navy);border-color:{theme.rgba(theme.BATON, 0.35)} {theme.rgba(theme.BATON, 0.35)} var(--surface);box-shadow:inset 0 2px 0 var(--baton)}}
#lp .dl{{display:flex;gap:16px;align-items:flex-start;margin:14px 0;font-size:14px;font-family:var(--sans)}}
#lp .dl span{{color:var(--mute);padding-top:6px}}
#lp button:not(.subtabs button):not(.pager button){{font-family:var(--sans);font-size:14px;font-weight:500;background:var(--blue);color:#fff;border:1px solid var(--blue);padding:8px 16px;cursor:pointer;white-space:nowrap}}
#lp button.secondary{{background:var(--surface);color:var(--ink);border-color:var(--ink)}}
#lp .submitbar{{position:sticky;bottom:0;z-index:5;display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:0 -2px;padding:12px 18px;background:var(--surface);border-top:2px solid var(--blue);box-shadow:0 -6px 18px rgba(0,0,0,.08);font-family:var(--sans);font-size:14px}}
#lp .submitbar[hidden]{{display:none}}
#lp .submitbar .foot{{flex:1 1 240px;min-width:200px}}
#lp .submitbar a{{color:var(--blue)}}
#lp .submitbar.failed{{border-top-color:var(--warn)}}
#lp .submitbar button:disabled{{opacity:.5;cursor:default}}
#lp .stamp{{margin:0 0 10px;font-family:var(--sans);font-size:13px;color:var(--mute)}}
#lp .compose{{margin:14px 0 18px;border:1px solid var(--line);border-left:2px solid var(--baton);background:var(--surface)}}
#lp .compose .bar{{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;padding:10px 14px;border-bottom:1px solid var(--line);background:var(--bg);font-family:var(--sans);font-size:14px}}
#lp .compose .bar .foot{{flex:1 1 240px}}
#lp .compose pre.msg{{margin:0;padding:14px 16px;white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.55 var(--serif);color:var(--ink);background:var(--surface)}}
#lp .compose>.foot{{margin:0;padding:8px 14px;border-top:1px solid var(--line)}}
#lp .compose button.copied{{background:var(--ink);color:var(--surface);border-color:var(--ink)}}
#lp .notify{{white-space:nowrap}}
#lp .notify+.notify{{margin-top:8px}}
#lp .notify button{{font-size:12.5px;padding:4px 10px;margin-top:4px}}
#lp .notify button.copied{{background:var(--ink);color:var(--surface);border-color:var(--ink)}}
#lp table.top .notify{{margin-top:6px}}
#lp details.rest{{margin:14px 0 0}}
#lp details.rest>summary h3{{display:inline;margin:0}}
#lp .stamp a{{color:inherit}}
#lp .tick:disabled{{opacity:.55}}
#lp table.preview tr.flag td{{background:rgba(159,45,0,.035)}}
#lp table.preview tr.pick{{cursor:pointer}}
#lp table.preview tr.pick:hover td{{background:var(--bg)}}
#lp table.preview tr.detail>td{{padding:4px 18px 18px;background:var(--bg);border-left:2px solid var(--blue)}}
#lp table.preview tr.detail dl.route{{margin-top:10px}}
#lp .ask+.drop{{margin-top:12px;padding:22px 16px;font-size:14.5px}}
#lp .presets{{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 10px;font-family:var(--sans);font-size:13px;color:var(--mute);align-items:center}}
#lp .presets button{{font-size:13px;padding:6px 12px}}
#lp .upload-head{{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 10px;margin:16px 0 4px;font-family:var(--sans);font-size:14px}}
#lp .upload-head select{{font:inherit;padding:4px 8px;border:1px solid var(--line);background:var(--surface);color:var(--ink)}}
#lp table.changes td.from{{color:var(--mute);text-decoration:line-through}}
#lp table.changes td.to{{font-weight:500}}
#lp table.sample td{{max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
#lp tr.reverted td{{color:var(--mute);text-decoration:line-through}}
#lp tr.reverted td.foot,#lp tr.reverted td .foot{{text-decoration:none}}
#lp tr.revert td{{background:var(--bg);border-top:2px solid var(--warn)}}
#lp #lp-up-revert-box{{margin:14px 0}}
#lp .dl.failed{{border-left:2px solid var(--warn);padding-left:12px}}
#lp .ask{{display:flex;gap:12px;align-items:stretch}}
#lp #lp-route-go{{padding:8px 22px;font-size:15px}}
#lp textarea{{flex:1;font-family:var(--serif);font-size:16px;line-height:1.5;padding:14px 16px;border:1px solid var(--line);background:var(--surface);color:var(--ink);resize:vertical;min-height:120px}}
#lp textarea:focus{{outline:none;border-color:var(--blue)}}
#lp dl.route{{display:grid;grid-template-columns:max-content 1fr;gap:8px 20px;margin:18px 0 6px;font-size:15px}}
#lp dl.route dt{{font-family:var(--sans);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--mute);padding-top:4px}}
#lp dl.route dd{{margin:0}}
#lp dl.route dd.key{{font-weight:500}}
#lp dl.route dd.key .foot{{font-weight:400}}
#lp dl.route .cue{{font-family:var(--mono);font-size:12px;color:var(--mute)}}
#lp .route-note{{margin:14px 0 4px;padding:10px 16px;border-left:2px solid var(--warn);background:var(--bg);font-family:var(--sans);font-size:14px}}
#lp .route-note.ok{{border-color:var(--blue)}}
#lp .ev{{font-size:18px;font-weight:500;color:var(--blue)}}
#lp #route td.path{{white-space:nowrap}}
/* phones */
@media(max-width:720px){{
  html{{-webkit-text-size-adjust:100%}}
  body{{font-size:15px}}
  code{{overflow-wrap:anywhere}}
  header{{padding:20px 16px 18px}}
  header h1{{font-size:26px}}
  header p{{font-size:14px}}
  nav a{{display:inline-block;margin:0 14px 6px 0}}
  main,.layout>main{{padding:16px 10px 64px}}
  .side{{padding:10px 16px 0}}
  section{{padding:18px 14px;margin-bottom:14px}}
  h2{{font-size:20px}}
  h3{{margin-top:22px}}
  .lede{{font-size:15px}}
  .kpis{{grid-template-columns:repeat(auto-fit,minmax(140px,1fr))}}
  .kpi{{padding:12px 12px 10px}}
  .kpi .v{{font-size:24px}}
  table{{font-size:13px;min-width:var(--tmin,0)}}
  th,td{{padding:7px 8px}}
  .grid2{{gap:20px}}
  .finding{{padding:6px 12px}}
  .mastrow{{padding:8px 16px 7px}}
  .mastrow .built{{display:none}}
  .mast .t{{font-size:15px}}
  .tabs,.tabs.people{{flex-wrap:nowrap;overflow-x:auto;padding-left:16px;padding-right:16px;scrollbar-width:none}}
  .tabs::-webkit-scrollbar{{display:none}}
  .tabs a,.tabs.people a,.tabs.people .lbl{{flex:none;white-space:nowrap;margin-bottom:0}}
  .tabs a{{padding:8px 12px}}
  .plotly-graph-div{{min-width:600px}}
  .totop{{right:14px;bottom:14px;width:40px;height:40px}}
  #lp .strip{{grid-template-columns:repeat(2,1fr)}}
  #lp .strip .cell{{padding:12px 12px 10px}}
  #lp .strip .v{{font-size:22px}}
  #lp .fold summary{{gap:10px}}
  #lp .ask{{flex-direction:column}}
  #lp .ask button{{align-self:flex-start}}
  #lp .dl{{flex-direction:column;gap:6px}}
  #lp .dl span{{padding-top:0}}
  #lp .submitbar{{padding:10px 12px;gap:8px}}
  #lp dl.route{{grid-template-columns:1fr;gap:2px 0}}
  #lp dl.route dt{{padding-top:10px}}
  #lp dl.route dt:first-child{{padding-top:0}}
  #lp .drop{{padding:20px 14px}}
}}
</style>"""

RAW_HTML, LIVE_HTML, TRACE_HTML = "halyardscoping.html", "livedata.html", "companytrace.html"
TABS = [
    (PRIORITIES_HTML, "Live Priorities"),
    (BATCH_HTML, "Batched-Ask for Connectors"),
    (TRACE_HTML, "Company Trace"),
    (LIVE_HTML, "Live Data Dashboard"),
    (RAW_HTML, "Raw Sept Data Dashboard"),
]
NO_PEOPLE_ROW = {TRACE_HTML, LIVE_HTML, RAW_HTML}


connector_pages = connector_fragments(TODAY)
MASTHEAD = (f'<a class="mast" href="{LIVE_HTML}">{theme.logo()}'
            '<span class="t"><b>Halyard Baton</b> / intro routing console</span></a>')


def tabs(active):
    """The sticky bar on every page: the masthead across the top, the page tabs, and
    under Live Priorities a sub-row in the baton colour with one tab per connector.
    The connector row belongs to Live Priorities, so Company Trace and the two data
    dashboards go without it; on a connector's page the Live Priorities tab is marked
    as the parent."""
    on_connector = any(c["page"] == active for c, _ in connector_pages)
    people_row = active not in NO_PEOPLE_ROW

    def link(href, label, extra=""):
        cls = "on" if href == active else "parent" if href == PRIORITIES_HTML and on_connector else ""
        attr = f' class="{cls}"' if cls else ""
        return f'<a href="{href}"{attr}>{esc(label)}{extra}</a>'
    pages = "".join(link(href, label) for href, label in TABS)
    people = "".join(link(c["page"], c["connector"], f'<span class="n">{len(c["top"]) + len(c["rest"])}</span>')
                     for c, _ in connector_pages)
    return (f'<div class="topbar"><div class="mastrow">{MASTHEAD}<span class="built">{built}</span></div>'
            f'<div class="tabs">{pages}</div>'
            + (f'<div class="tabs people"><span class="lbl">Live Priorities · by connector</span>{people}</div>' if people_row else '')
            + f'</div>{TOTOP}')


def sidebar(items=None, title="On this page", body=None):
    """The left rail. `items` is [(href, label, cls)] with labels already escaped; with no
    items the browser fills the list from the page's <section id> headings once they render.
    `body` replaces the list outright (Company Trace puts its search box and company list here)."""
    if body is not None:
        inner = body
    elif items is None:
        inner = '<nav class="toc" data-auto></nav>'
    else:
        inner = '<nav class="toc">' + "".join(
            f'<a class="{cls}" href="{href}">{label}</a>' if cls else f'<a href="{href}">{label}</a>'
            for href, label, cls in items) + '</nav>'
    return f'<aside class="side"><div class="side-h">{title}</div>{inner}</aside>'


# Back-to-top button; the topbar's height as --topbar so anchors land below it; every table
# in a horizontally scrolling wrapper (the wide ones overflow a phone screen), and any table
# over 25 rows shown 20 at a time with a filter box; the left rail filled from the page's
# sections where the page did not write it, and its current entry highlighted as the page
# scrolls; and on a narrow screen the tab rows scroll sideways, so bring the active tab into view.
TOTOP = """<button class="totop" type="button" title="Back to top" aria-label="Back to top">&uarr;</button>
<script>
// this script sits in the top bar, ahead of <main>, so it waits for the rest of the page to parse
document.addEventListener('DOMContentLoaded', function () {
  var b = document.querySelector('.totop');
  var show = function () { b.classList.toggle('show', window.scrollY > 400); };
  window.addEventListener('scroll', show, { passive: true });
  show();
  b.onclick = function () { window.scrollTo({ top: 0, behavior: 'smooth' }); };

  var bar = document.querySelector('.topbar');
  var fit = function () { document.documentElement.style.setProperty('--topbar', bar.offsetHeight + 'px'); };
  fit();
  window.addEventListener('resize', fit);
  window.addEventListener('load', fit);

  var PAGE = 20, MIN_ROWS = 25;
  var pages = function (n, p) {
    if (n <= 7) { var all = []; for (var i = 0; i < n; i++) all.push(i); return all; }
    var keep = {}, out = [];
    [0, 1, n - 2, n - 1, p - 1, p, p + 1].forEach(function (i) { if (i >= 0 && i < n) keep[i] = true; });
    for (var j = 0; j < n; j++) {
      if (keep[j]) out.push(j);
      else if (out[out.length - 1] !== -1) out.push(-1);
    }
    return out;
  };
  var pager = function (t) {
    if (t.dataset.pager || t.classList.contains('nopage') || !t.tBodies.length) return;
    var rows = Array.prototype.slice.call(t.tBodies[0].rows);
    if (rows.length < MIN_ROWS) return;
    t.dataset.pager = '1';
    var box = t.parentElement, q = '', p = 0, all = false;
    var barEl = document.createElement('div');
    barEl.className = 'pager';
    barEl.innerHTML = '<input type="search" placeholder="Filter rows" aria-label="Filter rows"><span class="pg-l"></span><span class="pg-b"></span><button type="button" class="pg-all"></button>';
    box.parentNode.insertBefore(barEl, box.nextSibling);
    var label = barEl.querySelector('.pg-l'), nums = barEl.querySelector('.pg-b'), allBtn = barEl.querySelector('.pg-all');
    var draw = function () {
      var hits = rows.filter(function (r) { return !q || r.textContent.toLowerCase().indexOf(q) >= 0; });
      var n = Math.max(1, Math.ceil(hits.length / PAGE));
      if (p >= n) p = n - 1;
      rows.forEach(function (r) { r.hidden = true; });
      var shown = all ? hits : hits.slice(p * PAGE, (p + 1) * PAGE);
      shown.forEach(function (r) { r.hidden = false; });
      var of = q ? ' matching' : '';
      label.textContent = !hits.length ? 'No rows match' : all || hits.length <= PAGE ? hits.length + of + ' rows'
        : 'Rows ' + (p * PAGE + 1) + '\u2013' + (p * PAGE + shown.length) + ' of ' + hits.length + of;
      nums.innerHTML = '';
      if (!all && n > 1) {
        var mk = function (txt, to, dis, on) {
          var x = document.createElement('button');
          x.type = 'button'; x.textContent = txt; x.disabled = !!dis; if (on) x.className = 'on';
          x.onclick = function () { p = to; draw(); };
          nums.appendChild(x);
        };
        mk('\u2039', p - 1, p === 0);
        pages(n, p).forEach(function (i) {
          if (i < 0) { var s = document.createElement('span'); s.textContent = '\u2026'; nums.appendChild(s); }
          else mk(String(i + 1), i, false, i === p);
        });
        mk('\u203a', p + 1, p === n - 1);
      }
      allBtn.hidden = hits.length <= PAGE;
      allBtn.textContent = all ? 'Show ' + PAGE + ' at a time' : 'Show all ' + hits.length;
    };
    barEl.querySelector('input').addEventListener('input', function (e) { q = e.target.value.trim().toLowerCase(); p = 0; draw(); });
    allBtn.onclick = function () { all = !all; p = 0; draw(); };
    draw();
  };

  var wrap = function () {
    document.querySelectorAll('table').forEach(function (t) {
      if (!t.parentElement.classList.contains('tscroll')) {
        var row = t.querySelector('tr'), cols = 0;
        if (row) for (var i = 0; i < row.cells.length; i++) cols += row.cells[i].colSpan;
        t.style.setProperty('--tmin', Math.min(cols * 130, 1100) + 'px');
        var d = document.createElement('div');
        d.className = 'tscroll' + (t.classList.contains('tall') ? ' tall' : '');
        t.parentNode.insertBefore(d, t);
        d.appendChild(t);
      }
      pager(t);
    });
  };

  var toc = document.querySelector('.side nav.toc'), main = document.querySelector('main'), tocKey = '';
  var heading = function (s) {
    var h = s.querySelector('h2');
    if (!h) return '';
    var c = h.cloneNode(true);
    c.querySelectorAll('.foot').forEach(function (f) { f.remove(); });
    return c.textContent.trim();
  };
  var fillToc = function () {
    if (!toc || !toc.hasAttribute('data-auto') || !main) return;
    var items = [];
    main.querySelectorAll('section[id]').forEach(function (s) { var t = heading(s); if (t) items.push([s.id, t]); });
    var key = items.join('|');
    if (key === tocKey) return;
    tocKey = key;
    toc.innerHTML = '';
    items.forEach(function (it) {
      var a = document.createElement('a');
      a.href = '#' + it[0]; a.textContent = it[1];
      toc.appendChild(a);
    });
    spy();
  };
  var spy = function () {
    if (!toc) return;
    var links = Array.prototype.filter.call(toc.querySelectorAll('a[href^="#"]:not(.band)'), function (a) { return document.getElementById(a.getAttribute('href').slice(1)); });
    if (!links.length) return;
    var line = bar.offsetHeight + 40, on = links[0];
    links.forEach(function (a) {
      var el = document.getElementById(a.getAttribute('href').slice(1));
      if (el.getBoundingClientRect().top <= line) on = a;
    });
    if (window.innerHeight + window.scrollY >= document.body.scrollHeight - 2) on = links[links.length - 1];
    links.forEach(function (a) { a.classList.toggle('on', a === on); });
    var side = toc.closest('.side');
    if (side && side.scrollHeight > side.clientHeight) {
      var top = on.offsetTop - side.offsetTop;
      if (top < side.scrollTop + 20 || top > side.scrollTop + side.clientHeight - 40) side.scrollTop = top - side.clientHeight / 2;
    } else if (toc.scrollWidth > toc.clientWidth) toc.scrollLeft = on.offsetLeft - (toc.clientWidth - on.offsetWidth) / 2;
  };
  var pending = false;
  window.addEventListener('scroll', function () {
    if (pending) return;
    pending = true;
    requestAnimationFrame(function () { pending = false; spy(); });
  }, { passive: true });
  window.addEventListener('load', spy);

  wrap();
  fillToc();
  new MutationObserver(function () { wrap(); fillToc(); }).observe(document.body, { childList: true, subtree: true });

  bar.querySelectorAll('.tabs').forEach(function (row) {
    var on = row.querySelector('a.on, a.parent');
    if (on && row.scrollWidth > row.clientWidth) row.scrollLeft = on.offsetLeft - (row.clientWidth - on.offsetWidth) / 2;
  });
});
</script>"""


built = f"Built {TODAY.isoformat()}"


def head(title):
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>Halyard · {title}</title>\n'
            f'<script src="https://cdn.plot.ly/plotly-3.0.1.min.js"></script>\n{theme.FONT_LINK}\n{STYLE}</head>')


raw_page = f"""{head("Raw Sept Data Dashboard")}
<body>
{tabs(RAW_HTML)}
<header>
  <h1>Raw Sept Data Dashboard</h1>
  <p>Scoping and verification of {len(requests)} warm-intro requests · Aug 2025 to Jul 2026 · Source: the September exports in <code>dataset/</code>, as filed · {built}</p>
</header>
<div class="layout">
{sidebar([("#flow", "Strategic data", "band"), ("#flow", "File Flow", ""), *STRATEGIC_NAV, ("#overview", "Funnel Overview", ""),
          ("#timing", "Timing", ""), ("#scoping", "Slack Threads", ""),
          ("#integrity-divider", "Data integrity", "band"), ("#joins", "Joins", ""), ("#targets", "Target People", ""),
          ("#quality", "Flags &amp; Coverage", ""), ("#verify", "CSV Profile", ""), ("#integrity", "Integrity Audit", "")])}
<main>

<p class="lede part-lede">Computed directly from the exports in <code>dataset/</code>: intro requests and outcomes, CRM accounts, connection lists, roster and Slack threads, as filed. The <a href="{LIVE_HTML}">Live Data Dashboard</a> tab shows the same charts from <code>golden/</code>, with the asks sent since September applied.</p>

<section id="flow">
  <h2>How the Files Connect</h2>
  <p class="lede">An intro request moves from Slack to a logged outcome; the four reference tables feed the routing step by name/company text only, and <code>request_id</code> is the sole real key.</p>
  <img src="routing_flow.png" alt="Intro-request routing flow across the CSV files" style="display:block;max-width:720px;width:100%;margin:0 auto">
  <p class="foot">Source: <code>analysis/routing/routing_flow.mmd</code>; narrative in <code>analysis/routing/routing_flow.md</code>.</p>
</section>
{strategic_sections(cuts, data_cuts.cycle_cut(cuts), live=False)}
<section id="overview">
  <h2>Funnel Overview</h2>
  <p class="lede">Every request drops out at the first stage it fails, so the eight buckets partition all {ov_n} requests. Unrouted requests split on whether the target company appears in <code>dataset/connections_*.csv</code>; a target counts as identifiable when a company can be recovered from <code>target_company_raw</code>, the company names in <code>raw_ask</code>, or an email domain in <code>raw_ask</code>.</p>
  {overview_table}
  <p class="foot">Buckets and ratios: <code>dashboard/funnel_overview.py</code> (also prints the table standalone).</p>
</section>

<section id="timing">
  <h2>Routing Time and Completion</h2>
  <p class="lede">Completion is defined as <code>intro_sent = Y</code>. Latency is measured from <code>request_date</code> to <code>asked_date</code> (routing) and to <code>intro_date</code> (delivery).</p>
  <div class="kpis">
    {kpi(f"{timing['mean_to_ask']:.1f} d", "mean request -> connector asked", f"median {timing['median_to_ask']:.0f} d over {len(timing['to_ask'])} routed requests")}
    {kpi(f"{timing['mean_to_intro']:.1f} d", "mean request -> intro sent", f"median {timing['median_to_intro']:.0f} d over {len(timing['to_intro'])} intros")}
    {kpi(f"{timing['completion_rate']:.0%}", "completion rate", f"{len(timing['to_intro'])} intros / {len(requests)} requests")}
    {kpi(f"{timing['completion_rate_routed']:.0%}", "completion rate once routed", f"{len(timing['to_intro'])} intros / {len(outcomes)} asks")}
  </div>
  {trend_div}
  <div class="grid2">
    <div>
      <h3>By month</h3>
      {monthly_table}
    </div>
    <div>
      <h3>Reading it</h3>
      <div class="finding"><b>Routing is fast; everything after it is slow.</b>When a request is routed at all it is routed in {timing['mean_to_ask']:.1f} days on average (max {max(timing['to_ask'])}), but the intro lands {timing['mean_to_intro']:.1f} days after the request. The delay sits with the connector rather than the triage.</div>
      <div class="finding warn"><b>Completion is flat.</b>Weekly volume swings between {min(w[1] for w in timing["weekly"])} and {max(w[1] for w in timing["weekly"])} requests, and the 4-week rolling completion rate stays inside {min(r for r in roll if r is not None):.0%}–{max(r for r in roll if r is not None):.0%} across all {len(timing["weekly"])} weeks. Month over month it never exceeds {max(i/n for _, n, _, i, _ in timing["monthly"]):.0%}.</div>
      <div class="finding warn"><b>Week-over-week trending is noisy by construction.</b>The median week holds {statistics.median([w[1] for w in timing["weekly"]]):.0f} requests, so a single intro moves the weekly rate by tens of points; the rolling line above is the honest read.</div>
    </div>
  </div>
</section>

<section id="scoping">
  <h2>Scoping: What Happens in <code>#intro-requests</code></h2>
  <p class="lede">From <code>dataset/slack_threads.jsonl</code>: {len(threads)} threads, {sum(len(t["messages"]) for t in threads)} messages, {len(replies)} replies. Full write-up in <code>analysis/slack/slack_thread_findings.md</code>.</p>
  <div class="kpis">
    {kpi(f"{canned_total/len(replies):.0%}", "of replies are canned", f"{len(masked)} distinct texts after name masking")}
    {kpi(len(offers), "genuine offers to help", f"across {len({r for r, _ in offers})} threads")}
    {kpi(f"{len(offers_unlogged)} / {len(offers)}", "offers never logged as asked", usd(offers_unlogged_value) + " of company value, one $ per company")}
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
      <div class="finding warn"><b>Offers fall through the cracks.</b>{len(offers_unlogged)} of the {len(offers)} offers ({", ".join(sorted({r for r, _ in offers_unlogged}))}) have no <code>connector_asked</code> row. That is {usd(offers_unlogged_value)} of pipeline where someone said "leave it with me" and nothing was recorded.</div>
      <div class="finding warn"><b>Delegation never lands.</b>"adding X who might know" appears {len(adds)} times; the named person was logged as asked in {adds_followed} of them. Everyone tagged is an AE / CRM owner, and none of them is a roster connector.</div>
      <div class="finding"><b>Silence tells you little.</b>{len(no_reply)} threads got no reply, yet {len(no_reply_asked)} of them were routed to a connector anyway, so the ask happened outside Slack.</div>
      <div class="finding"><b>Slow first response.</b>Median {statistics.median(first_reply_h):.1f} h to the first reply on the {len(first_reply_h)} threads that got one.</div>
    </div>
  </div>
  <h3>Duplicate-checking replies</h3>
  <div class="grid2">
    <div>
      {dup_table}
      <p class="foot">Matched on <code>same as</code>, <code>already lost/asked</code>, <code>last month</code>, <code>duplicate</code> in <code>dashboard/data_cuts.py</code>.</p>
    </div>
    <div>
      <div class="finding warn"><b>{slack["dups"]} of {slack["replies"]} replies ({slack["dups"]/slack["replies"]:.0%}) are someone asking whether this ask is a duplicate.</b>They appear in {slack["dup_threads"]} of the {slack["threads"]} threads, and only {slack["dup_threads_with_intro"]} of those threads ever produced an intro. Nobody ever answers the question in-thread.</div>
      <div class="finding"><b>The question is well-founded.</b>{demand["repeat_share"]:.0%} of asks are for a company that was already requested, so "is this the same as the one from last month?" is usually yes, and the answer already exists in <code>golden/golden_companies.csv</code> (<code>total_requests</code>, <code>latest_request_id</code>).</div>
    </div>
  </div>
  <h3>Offers to help with no logged ask</h3>
  {table(["Request", "Offered by", "Deal value (USD)", "Request status", "Reply"],
         [(rid, m["user"], f"{float(requests[rid]['deal_value_usd']):,.0f}", requests[rid]["status"], m["text"]) for rid, m in offers_unlogged])}
</section>

<div class="divider" id="integrity-divider">
  <span class="t">Data integrity</span>
  <p>Everything above reads the business: where requests go, which accounts and requesters drive demand, what the connectors deliver and when. Everything from here down checks the files themselves: whether the keys join, whether the flags and statuses carry information, what each export looks like column by column. It sets how far to trust the numbers above; it does not change them.</p>
</div>

<section id="joins">
  <h2>Scoped Joins</h2>
  <p class="lede">Every entity link measured in both directions at the loosest normalization tier (lowercase, punctuation and legal suffixes stripped), from <code>analysis/joins/join_rates.md</code>. "Left matched" is the share of distinct left-hand values that find a counterpart.</p>
  <div class="kpis">
    {kpi(len(joins["perfect"]), "joins clean in both directions", f"of {len(joins['joins'])} links measured")}
    {kpi(f"{joins['concerning'][0][1]:.0f}%", "worst link: target_person_raw -> connections", "no requested person exists in the network")}
    {kpi("54.5%", "connector_asked on the roster", f"{len(connectors['off_roster'])} people asked who are not connectors")}
    {kpi("42.5%", "requests with an outcome row", f"{coverage['missing']} requests have none")}
  </div>
  <div class="grid2">
    <div>
      <h3>Joins you can build on</h3>
      <div class="finding"><b><code>intro_outcomes.request_id</code> -> <code>intro_requests.request_id</code>: 100%.</b>Every outcome row resolves to a real request and no request_id is duplicated, so the funnel is safe to read forward from a request.</div>
      <div class="finding"><b><code>requested_by</code> -> <code>crm_accounts.owner</code>: 100% / 100%.</b>The same eight names, spelled identically, on both sides, so requester-level and owner-level analysis can be mixed freely.</div>
      <div class="finding"><b><code>connector_roster.connections_file</code> -> files on disk: 100%.</b>Supply is fully enumerable: six rosters, six exports, {len(cuts["connections"]):,} contacts.</div>
    </div>
    <div>
      <h3>Joins that break the analysis</h3>
      <div class="finding warn"><b><code>target_person_raw</code> -> <code>connections_*.name</code>: 0% / 0%.</b>Not one of the {targets["distinct"]} named individuals appears anywhere in the network (see below). Person-level routing is impossible; only the company can be matched.</div>
      <div class="finding warn"><b><code>connector_asked</code> -> <code>connector_roster.name</code>: 54.5%.</b>{sum(n for _, n in connectors["off_roster"])} asks went to {len(connectors["off_roster"])} people who are not connectors ({", ".join(n for n, _ in connectors["off_roster"])}), so capacity and focus-area rules never applied to them.</div>
      <div class="finding warn"><b><code>target_company_raw</code> -> <code>crm_accounts.account_name</code>: 71.2%, and only after normalization.</b>Exact match is 65.4%; the CRM side needs legal-suffix stripping to reach 84%. Every company cut below is therefore built on the resolved <code>golden/</code> company id instead of the raw string.</div>
      <div class="finding warn"><b><code>connections_*.company</code> -> <code>target_company_raw</code>: 58% / 55.8%.</b>Supply and demand barely overlap: 21 companies in the network are never requested and 23 requested companies have no contact at all.</div>
    </div>
  </div>
  <h3>All measured links</h3>
  {joins_table}
</section>

<section id="targets">
  <h2>Target People: Does the Named Individual Exist Anywhere?</h2>
  <p class="lede">{targets["named"]} of {targets["requests"]} requests name a person in <code>target_person_raw</code> ({targets["blank"]} leave it blank). Each name was looked up in every other file in <code>dataset/</code>.</p>
  <div class="kpis">
    {kpi(f"0 / {targets['distinct']}", "named targets found anywhere", "across connections, investors, roster, CRM owners, Slack")}
    {kpi(f"{targets['in_own_thread']} / {targets['named']}", "named only in their own thread", "the name exists solely as free text")}
    {kpi(f"{targets['recombined']} / {targets['distinct']}", "names built from network surnames", "double-barrelled recombinations of contact surnames")}
    {kpi(f"{targets['title_reachable']} / {targets['named']}", "reachable by title instead", "a contact at the same company holds the requested title")}
  </div>
  <div class="grid2">
    <div>
      <h3>Lookup result</h3>
      {target_table}
      <p class="foot">Exact match after trimming; the same lookup at looser tiers in <code>analysis/joins/join_rates.md</code> is also 0%.</p>
    </div>
    <div>
      <h3>Findings</h3>
      <div class="finding warn"><b><code>target_person_raw</code> is unjoinable by construction.</b>All {targets["distinct"]} names are distinct, none appears in {len(cuts["connections"]):,} contacts, {len(cuts["investors"])} investor rows, the roster, the CRM owners or as a Slack author. Every surname token, however, is a surname that does occur in the network. The names are recombinations, so any fuzzy matcher will produce plausible false positives.</div>
      <div class="finding"><b>The usable signal is the title.</b>For {targets["title_reachable"]} of the {targets["named"]} person-named requests, a contact at the same company already holds exactly the requested title, so routing should match company plus title and ignore the name.</div>
      <div class="finding"><b>Data point to track:</b><code>target_person_resolvable</code> = 0 / {targets["distinct"]}, <code>target_title_reachable</code> = {targets["title_reachable"]} / {targets["named"]}. Recomputed on every build in <code>dashboard/data_cuts.py</code>.</div>
    </div>
  </div>
</section>

<section id="quality">
  <h2>Flags, Statuses and Outcome Coverage</h2>
  <p class="lede">Whether <code>path_found_flag</code> and <code>status</code> carry information, and whether <code>intro_outcomes.csv</code> is a deliberate subset of <code>intro_requests.csv</code> or a coverage hole.</p>
  <div class="kpis">
    {kpi(f"{(noise['flags']['(blank)'] + noise['flags']['Unknown'])/len(requests):.0%}", "of path_found_flag is blank or Unknown", f"{noise['flags']['(blank)']} blank · {noise['flags']['Unknown']} Unknown")}
    {kpi(sum(n for _, n in noise["contradictions"]), "flag/status contradictions", "across the six checks below")}
    {kpi(f"{coverage['matched']} / {coverage['requests']}", "requests with an outcome row", f"{coverage['orphan_outcomes']} orphan outcome rows")}
    {kpi(coverage["should_exist"], "missing rows that must exist", f"status is Routed or Intro sent · {usd(coverage['should_exist_value'])}")}
  </div>
  <div class="grid2">
    <div>
      <h3><code>path_found_flag</code> × <code>status</code></h3>
      {matrix_table}
      <h3>What the flag actually predicts</h3>
      {reality_table}
      <p class="foot">"Company has a path" is measured against <code>golden/supply_reach.csv</code>, i.e. the network rather than the flag.</p>
    </div>
    <div>
      <h3>Findings</h3>
      <div class="finding warn"><b><code>path_found_flag</code> is noise for {(noise["flags"]["(blank)"] + noise["flags"]["Unknown"])/len(requests):.0%} of requests.</b>{noise["flags"]["(blank)"]} are blank and {noise["flags"]["Unknown"]} say <code>Unknown</code>; of the blank ones {noise["flag_reality"]["(blank)"]["paths"]/noise["flag_reality"]["(blank)"]["requests"]:.0%} actually do have a path in the network, so blank does not mean "no path".</div>
      <div class="finding warn"><b>Where it is filled in, it contradicts the outcome.</b>{dict(noise["contradictions"])["flag <code>Path found</code> yet nobody was ever asked"]} requests flagged <code>Path found</code> were never routed, and {dict(noise["contradictions"])["flag <code>No path found</code> yet an intro was sent"]} flagged <code>No path found</code> ended in an intro. The two fields are maintained independently of the funnel.</div>
      <div class="finding warn"><b><code>status</code> and the outcome rows disagree both ways.</b>{dict(noise["contradictions"])["status <code>Intro sent</code> with no <code>intro_sent=Y</code> outcome row"]} requests claim status <code>Intro sent</code> with no such outcome row, while {dict(noise["contradictions"])["<code>intro_sent=Y</code> while status is still Open/Stalled/Routed"]} requests with a sent intro still show Open/Stalled/Routed. Neither field can be used as the funnel stage; <code>intro_outcomes.csv</code> has to be the source of truth.</div>
      {contradiction_table}
    </div>
  </div>
  <h3><code>intro_outcomes</code> vs <code>intro_requests</code>: subset or coverage hole?</h3>
  <div class="grid2">
    <div>
      {coverage_table}
    </div>
    <div>
      <div class="finding warn"><b>It is a coverage hole.</b>All {coverage["outcomes"]} outcome rows resolve to a request and none is duplicated, so the file is clean in that direction. But {coverage["should_exist"]} of the {coverage["missing"]} requests with no outcome row are filed as <code>Routed</code> or <code>Intro sent</code> ({usd(coverage["should_exist_value"])}). A routed request must have an ask, so those rows are missing rather than not-yet-existing.</div>
      <div class="finding warn"><b>Slack shows the same gap.</b>{coverage["offered_in_slack"]} of the requests with no outcome row have someone in-thread saying they would take it. The ask happened; the row was never written.</div>
      <div class="finding"><b>The rest is plausibly genuine.</b>The remaining {coverage["missing"] - coverage["should_exist"]} are Open, Stalled or Closed - no path, i.e. requests that legitimately never reached a connector. Treat {coverage["matched"]}/{coverage["requests"]} as the ceiling on funnel coverage and {coverage["should_exist"]} as the known write-back defect.</div>
    </div>
  </div>
</section>

<section id="verify">
  <h2>Verification: CSV Inventory Profile</h2>
  <p class="lede">From <code>analysis/profile/profile.md</code> (generated by <code>analysis/profile/profile_csvs.py</code>): {len(inventory)} CSV files, {sum(r for _, r, _, _ in inventory):,} data rows, {len(flags)} column-level flags.</p>
  <div class="kpis">
    {kpi(len(inventory), "CSV files profiled", f"{sum(r for _, r, _, _ in inventory):,} rows")}
    {kpi(len(flags), "column flags raised", f"{len(flag_categories)} categories")}
    {kpi(len(crm_dupes), "near-duplicate CRM accounts", f"{crm_dup_owner_conflicts} with conflicting owners")}
    {kpi(f"{req_missing_company} / {len(requests)}", "requests with no target company", f"{req_missing_person} lack a target person")}
    {kpi(f"{req_missing_flag}", "requests with blank path_found_flag", f"{sum(1 for r in requests.values() if r['path_found_flag'].strip()=='Unknown')} more say Unknown")}
    {kpi(outcome_dup_ids, "duplicate request_ids in outcomes", "one ask per request, so a 2nd offer can never be logged")}
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
      <div class="finding"><b>Inconsistent casing is systematic.</b><code>requester_role</code>, <code>status</code>, <code>path_found_flag</code>, <code>role</code> and <code>account_name</code> all mix Title / Sentence / UPPER. Safe to normalise, but joins on raw strings will miss.</div>
      <div class="finding"><b>Outcomes are one row per request.</b><code>intro_outcomes.csv</code> has {len(outcomes)} rows and {len(outcomes) - outcome_dup_ids} distinct request_ids, so only one connector can ever be recorded per request.</div>
      <h3>Flag categories</h3>
      {table(["Category", "Columns affected"], flag_categories.most_common())}
    </div>
  </div>
  <details>
    <summary><h3 style="display:inline;margin:0">All flags, by file ({len(flags)})</h3></summary>
    {table(["File", "Column", "Issue"], flags)}
  </details>
</section>

<section id="integrity" style="padding:0 0 10px">
  {integrity_div}
  <p class="foot" style="padding:0 30px">Readable report: <code>analysis/integrity/findings.md</code> (generated by <code>analysis/integrity/integrity_audit.py</code>).</p>
</section>

<p class="foot">Regenerate with <code>python3 build.py dashboard</code>. Everything on this tab is computed from <code>dataset/</code> at build time.</p>
</main>
</div>
</body></html>
"""

live_page = f"""{head("Live Data Dashboard")}
<body>
{tabs(LIVE_HTML)}
<header>
  <h1>Live Data Dashboard</h1>
  <p>Funnel, accounts, requesters and connectors: {len(live_cuts["requests"])} requests after entity resolution, with every ask sent since · Source: <code>golden/</code>, rebuilt from <code>dataset/</code> and Supabase by the rebuild workflow · {built}</p>
</header>
<div class="layout">
{sidebar(LIVE_NAV)}
<main>

{headline_kpis(live_cuts)}

<p class="lede part-lede">Computed from <code>golden/</code> (<code>golden_requests.csv</code>, <code>golden_companies.csv</code>, <code>supply_reach.csv</code>, <code>completions.csv</code>) after entity resolution, so companies are counted by identity rather than by how the name was typed. The ask log is <code>intro_outcomes.csv</code> with <code>golden/completions.csv</code> applied: a Submit on <a href="{PRIORITIES_HTML}">Live Priorities</a> lands in Supabase, the rebuild pulls it into <code>completions.csv</code>, and the ask counts here from that build on; requests added later, CRM changes and new <code>intro_outcomes.csv</code> rows flow in the same way, through <code>python3 golden/build_golden.py</code>. The <a href="{RAW_HTML}">Raw Sept Data Dashboard</a> has the same charts from the September exports alone.</p>

{strategic_sections(live_cuts, connector_cycles(TODAY), live=True, in_flight=priorities_in_flight(TODAY))}

<p class="foot">Regenerate with <code>python3 build.py dashboard</code>; <code>python3 golden/build_golden.py --completions supabase</code> first to pick up asks sent since the last build. Everything on this tab is computed from <code>golden/</code> at build time. The <a href="{TRACE_HTML}">Company Trace</a> tab has the full history of any one company.</p>
</main>
</div>
</body></html>
"""

trace_page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Halyard · Company Trace</title>
{theme.FONT_LINK}
{STYLE}</head>
<body>
{tabs(TRACE_HTML)}
<header>
  <h1>Company Trace</h1>
  <p>The full history of one company: what <code>analysis/trace.py</code> prints, for any of the 48 companies with a request · Sources: <code>dataset/</code>, <code>golden/</code> · {built}</p>
</header>
<div class="layout">
{sidebar(title='Companies <span class="foot" id="trace-count"></span>', body=trace_sidebar())}
<main>
<section id="trace">
  <p class="lede">Pick a company on the left, or search by name, alias, company id or CRM account id. Five sections follow: the header, where the files disagree (left out when they agree), who can reach them by strength, every event from <code>intro_requests.csv</code>, <code>slack_threads.jsonl</code>, <code>intro_outcomes.csv</code> and <code>crm_accounts.csv</code> newest first, and the additional investor and operator network around the company from <code>golden/network_orbit.csv</code> (left out when there is nobody; a view: an off-roster investor's own portfolio company is an <code>investor_network</code> path in section 3, asked only when the roster has no path or no capacity; nothing else here is scored or allocated). The same traces are written to <code>analysis/traces/</code> by <code>python3 build.py trace</code>.</p>
  {trace_fragment()}
</section>
<p class="foot">Regenerate with <code>python3 build.py dashboard</code>.</p>
</main>
</div>
</body></html>
"""

priorities_page = f"""{head("Live Priorities")}
<body>
{tabs(PRIORITIES_HTML)}
<header>
  <h1>Live Priorities</h1>
  <p>What to do next, and who does it. Every number here is computed by <code>dashboard/live_priorities.py</code> from <code>golden/</code> and <code>dataset/</code> at build time and written into the page; the browser only renders it. Every company name opens its <a href="{TRACE_HTML}">Company Trace</a> · {built}</p>
</header>
<div class="layout">
{sidebar([x for bid, title, sections in PRIORITIES_BANDS
          for x in [(f"#band-{bid}", esc(title.split(":")[0]), "band")] + [(f"#{sid}", esc(label), "") for sid, label in sections]])}
<main>
{priorities_fragment()}
<p class="foot">Regenerate with <code>python3 build.py dashboard</code>. Ranking constants live at the top of <code>dashboard/live_priorities.py</code>.</p>
</main>
</div>
</body></html>
"""


batch_page = f"""{head("Batched-Ask for Connectors")}
<body>
{tabs(BATCH_HTML)}
<header>
  <h1>Batched-Ask for Connectors</h1>
  <p>One message per connector, this cycle's batch. Each connector's allocated requests from <code>golden/golden_allocation.csv</code>, drafted as a single plain-text ask by <code>dashboard/batch_ask.py</code> at build time with the wording in <code>config/batch_ask_templates.json</code>. Copy, send, then tick <i>ask sent</i> on <a href="{PRIORITIES_HTML}#connectors">Live Priorities</a> or the connector's page. Copying writes nothing. Every company name opens its <a href="{TRACE_HTML}">Company Trace</a> · {built}</p>
</header>
<div class="layout">
{sidebar(title="Connectors")}
<main>
{batch_fragment(TODAY)}
<p class="foot">Regenerate with <code>python3 build.py dashboard</code>. Print the messages with <code>python3 -m dashboard.batch_ask</code>.</p>
</main>
</div>
</body></html>
"""


def connector_page(c, frag):
    who = f"{esc(c['role'])} · {esc(c['type'])}" if c["on_roster"] else "not on the roster"
    return f"""{head(esc(c["connector"]))}
<body>
{tabs(c["page"])}
<header>
  <h1>{esc(c["connector"])}</h1>
  <p>Top {len(c["top"])}, then the longer list · {who} · {len(c["top"]) + len(c["rest"])} live requests routed to them this cycle, ranked by the same expected value as <a href="{PRIORITIES_HTML}#top">Live Priorities</a>; computed by <code>dashboard/live_priorities.py</code> at build time, rendered by the browser. Every company name opens its <a href="{TRACE_HTML}">Company Trace</a> · {built}</p>
</header>
<div class="layout">
{sidebar()}
<main>
{frag}
<p class="foot">Regenerate with <code>python3 build.py dashboard</code>. Ticks are shared with the Live Priorities tab in this browser.</p>
</main>
</div>
</body></html>
"""


index_page = f"""<!doctype html>
<meta charset="utf-8">
<title>Halyard — scoping &amp; verification</title>
<meta http-equiv="refresh" content="0; url={RAW_HTML}">
<p>{' · '.join(f'<a href="{page}">{label}</a>' for page, label in TABS)}</p>
"""

DOCS.mkdir(exist_ok=True)
shutil.copyfile(ROUTING / "routing_flow.png", DOCS / "routing_flow.png")
for old in DOCS.glob("connector-*.html"):
    if old.name not in {c["page"] for c, _ in connector_pages}:
        old.unlink()
for name, markup in (
    ("index.html", index_page),
    (RAW_HTML, raw_page),
    (LIVE_HTML, live_page),
    (TRACE_HTML, trace_page),
    (PRIORITIES_HTML, priorities_page),
    (BATCH_HTML, batch_page),
    *((c["page"], connector_page(c, frag)) for c, frag in connector_pages),
):
    out_path = str(DOCS / name)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(markup)
    print(f"wrote {out_path}")
# when this site was generated, for the Live Priorities tab to show; kept out of
# the pages so an unchanged rebuild leaves them byte-identical
BUILD_STAMP.write_text(json.dumps({
    "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "as_of": TODAY.isoformat(),
    "completions": len(bg.load_completions()),
}) + "\n", encoding="utf-8")
print(f"wrote {BUILD_STAMP}")
print(f"funnel raw {[c for _, c in data_cuts.funnel_cut(cuts)]} golden {[c for _, c in data_cuts.funnel_cut(live_cuts)]}  "
      f"offers {len(offers)} unlogged {len(offers_unlogged)} adds {len(adds)}/{adds_followed} "
      f"no_reply {len(no_reply)}/{len(no_reply_asked)} median_h {statistics.median(first_reply_h):.1f} "
      f"flags {len(flags)} dupes {len(crm_dupes)}/{crm_dup_owner_conflicts}")
