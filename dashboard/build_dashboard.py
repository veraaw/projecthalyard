"""Build the dashboard tabs in docs/:

  halyardscoping.html  Raw Sept Data Dashboard — Slack thread findings, CSV profile,
                       joins, timing and the integrity audit, straight from dataset/
  livedata.html        Live Data Dashboard — funnel, accounts and connectors from golden/
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
from datetime import date, datetime, timedelta, timezone

import plotly.graph_objects as go
import plotly.io as pio

from analysis.integrity.integrity_audit import fragment as integrity_fragment
from dashboard import data_cuts, theme
from dashboard.funnel_overview import dropoff_rows, ratios
from dashboard.live_priorities import (BATCH_PAGE as BATCH_HTML, BUILD_STAMP, PAGE as PRIORITIES_HTML,
                                       SECTIONS as PRIORITIES_SECTIONS, batch_fragment, connector_fragments,
                                       cycles as connector_cycles, fragment as priorities_fragment)
from dashboard.sankey_funnel import GOLDEN as GOLDEN_REQUESTS, build_figure, funnel_stages
from dashboard.trace_section import fragment as trace_fragment
from golden import build_golden as bg
from paths import DATASET, DOCS, PROFILE, ROUTING

DATA = str(DATASET)


def rows(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def usd(d):
    return f"${d/1e6:.1f}M" if d >= 1e6 else f"${d/1e3:.0f}K"


def esc(s):
    return html.escape(str(s))


# --------------------------------------------------------------------------- funnel
TODAY = date.today()
ROLLING_SINCE = (TODAY - timedelta(days=365)).isoformat()
stages = funnel_stages()
stages_12m = funnel_stages(since=ROLLING_SINCE)
with open(GOLDEN_REQUESTS, newline="", encoding="utf-8-sig") as _f:
    _dates = sorted(r["request_date"].strip()[:10] for r in csv.DictReader(_f) if r["request_date"].strip())
stages_first, stages_last = _dates[0][:7], _dates[-1][:7]


def plot(fig, div_id):
    html = pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id=div_id,
                       config={"displayModeBar": False, "responsive": True})
    return f'<div class="tscroll plot">{html}</div>'


def sankey(stg, div_id):
    fig = build_figure(stg)
    fig.update_layout(width=None, height=560, autosize=True, title=None,
                      margin=dict(l=10, r=10, t=20, b=20), paper_bgcolor="rgba(0,0,0,0)")
    return plot(fig, div_id)


sankey_div = sankey(stages, "sankey")
sankey_div_12m = sankey(stages_12m, "sankey-12m")

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
opp_status_mismatch = [o["request_id"] for o in outcomes
                       if o["opportunity_created"] == "Y" and requests[o["request_id"]]["status"] in ("Open", "Stalled", "Routed")]

# --------------------------------------------------------------------------- integrity audit
integrity_div = integrity_fragment()  # also refreshes analysis/integrity/findings.md

# --------------------------------------------------------------------------- render
def kpi(value, label, sub=""):
    return f'<div class="kpi"><div class="v">{value}</div><div class="l">{esc(label)}</div>' + (f'<div class="s">{esc(sub)}</div>' if sub else "") + "</div>"


def table(headers, body_rows, cls=""):
    h = "".join(f"<th>{esc(x)}</th>" for x in headers)
    b = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in body_rows)
    return f'<table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>'


counts = [c for _, c in stages]
counts_12m = [c for _, c in stages_12m]


def pct(a, b, digits=0):
    return f"{a / b:.{digits}%}" if b else "—"


def funnel_table(stg):
    n = [c for _, c in stg]
    return table(["Stage", "Count", "of requests", "step conversion"],
                 [(name, c, pct(c, n[0]), pct(c, n[i - 1]) if i else "—") for i, (name, c) in enumerate(stg)])


def funnel_kpis(n):
    return f"""<div class="kpis">
    {kpi(n[0], "requests")}
    {kpi(n[1], "asked", f"{pct(n[1], n[0])} of requests")}
    {kpi(n[3], "intros sent", f"{pct(n[3], n[1])} of asks")}
    {kpi(n[4], "meetings", f"{pct(n[4], n[3])} of intros")}
    {kpi(n[5], "opportunities", f"{pct(n[5], n[0], 1)} of requests end-to-end")}
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
overview_table = ('<table class="fo"><thead><tr><th>Category</th><th>Funnel Dropoff</th>'
                  '<th class="num"># Requests</th><th class="num">% Total</th></tr></thead>'
                  f'<tbody>{ov_body}</tbody></table>')

# --------------------------------------------------------------------------- additional data cuts
cuts = data_cuts.load()
joins = data_cuts.join_summary_cut(cuts)
demand = data_cuts.account_demand_cut(cuts)
top_accounts = data_cuts.top_accounts_cut(cuts)
connectors = data_cuts.connector_cut(cuts)
targets = data_cuts.target_person_cut(cuts)
timing = data_cuts.routing_time_cut(cuts)
slack = data_cuts.slack_cut(cuts)
noise = data_cuts.flag_noise_cut(cuts)
coverage = data_cuts.outcome_delta_cut(cuts)

joins_rows = [(link, f"{left:.1f}%", f"{right:.1f}%", note or "—")
              for link, left, right, note in sorted(joins["joins"], key=lambda j: min(j[1], j[2]))]
joins_table = table(["Link (left -> right)", "Left matched", "Right matched", "What it means"], joins_rows)

demand_12m = data_cuts.account_demand_cut(cuts, since=ROLLING_SINCE)
demand_top = demand["companies"][:20]


def demand_chart(dm, div_id):
    """Top 20 companies by asks, routed vs never routed, for one window of `dm`."""
    top = dm["companies"][:20]
    fig = go.Figure()
    fig.add_bar(y=[b["name"] for b in top][::-1], x=[b["routed"] for b in top][::-1],
                name="routed to a connector", orientation="h", marker_color=theme.ACCENT)
    fig.add_bar(y=[b["name"] for b in top][::-1], x=[b["requests"] - b["routed"] for b in top][::-1],
                name="never routed", orientation="h", marker_color=theme.NEUTRAL)
    fig.update_layout(barmode="stack", height=560, autosize=True, margin=dict(l=10, r=20, t=10, b=30),
                      **theme.PLOTLY_LAYOUT)
    fig.update_layout(legend=dict(orientation="h", y=1.04, x=0), xaxis=dict(title="asks"), yaxis=dict(automargin=True))
    return plot(fig, div_id)


demand_div = demand_chart(demand, "demand")
demand_div_12m = demand_chart(demand_12m, "demand-12m")
demand_rows = [(b["name"], b["industry"] or ("—" if b["in_crm"] else "no CRM record"), b["requests"], b["routed"], b["requests"] - b["routed"],
                len(b["requesters"]), b["paths"], usd(b["value"])) for b in demand_top]
demand_rows += [(b["name"], "unresolvable", b["requests"], b["routed"], b["requests"] - b["routed"],
                 len(b["requesters"]), "—", "—") for b in demand["unresolvable"]]
demand_table = table(["Company", "Industry", "Asks", "Routed", "Never routed", "Requesters", "Paths in network", "Value"],
                     demand_rows)
unresolvable_asks = sum(b["requests"] for b in demand["unresolvable"])

top_rows = [(b["name"], usd(b["value"]), "CRM ARR" if b["value_source"] == "CRM" else "deal value",
             b["requests"], b["routed"], f'{b["responded"]}/{b["intros"]}/{b["meetings"]}/{b["opps"]}',
             b["owner"] or "no CRM account",
             ", ".join(b["internal_connectors"]) or "—",
             ", ".join(b["outside_connectors"]) or "—")
            for b in top_accounts["companies"]]
top_table = table(["Company", "Value", "Value from", "Asks", "Routed", "Resp/Intro/Mtg/Opp",
                   "CRM owner", "Internal connectors asked", "Advisor / investor asked"], top_rows)

connector_rows = [(c["name"], c["type"], c["capacity"], c["asked"], c["responded"], c["intros"],
                   c["meetings"], c["opps"], usd(c["value"]), usd(c["opp_value"]),
                   f'{c["in_focus"]}/{c["asked"]}', c["focus_areas"], c["notes"])
                  for c in connectors["connectors"]]
connector_table = table(["Connector", "Type", "Capacity/mo", "Asked", "Responded", "Intros", "Meetings",
                         "Opps", "Requested $", "Opp $", "In focus area", "Stated focus", "Roster note"],
                        connector_rows)

target_table = table(["Looked up in", "Distinct target people found"],
                     [(label, n) for label, n in targets["hits"]])

weeks = timing["weekly"]
roll = []
for i in range(len(weeks)):
    window = weeks[max(0, i - 3):i + 1]
    req_n = sum(w[1] for w in window)
    roll.append(sum(w[3] for w in window) / req_n if req_n else None)
trend_fig = go.Figure()
trend_fig.add_bar(x=[w[0] for w in weeks], y=[w[1] for w in weeks], name="requests filed",
                  marker_color=theme.NEUTRAL)
trend_fig.add_bar(x=[w[0] for w in weeks], y=[w[3] for w in weeks], name="intros sent", marker_color=theme.ACCENT)
trend_fig.add_scatter(x=[w[0] for w in weeks], y=roll, name="completion rate (4-week rolling)",
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
cycles = connector_cycles(TODAY)
cyc_rows = cycles["rows"]
cyc_fig = go.Figure()
cyc_fig.add_bar(x=[r["cycle"] for r in cyc_rows], y=[r["used"] for r in cyc_rows], name="roster slots used",
                marker_color=theme.NEUTRAL)
cyc_fig.add_bar(x=[r["cycle"] for r in cyc_rows], y=[r["intros"] for r in cyc_rows], name="intros made",
                marker_color=theme.ACCENT)
cyc_fig.add_scatter(x=[r["cycle"] for r in cyc_rows], y=[r["intros_cumulative"] for r in cyc_rows],
                    name="cumulative intros", mode="lines+markers", line=dict(color=theme.WARN, width=2))
cyc_fig.add_scatter(x=[r["cycle"] for r in cyc_rows], y=[r["capacity_pct"] for r in cyc_rows],
                    name="capacity used", yaxis="y2", mode="lines", line=dict(color=theme.BATON, width=2, dash="dot"))
cyc_fig.update_layout(barmode="overlay", height=380, autosize=True, margin=dict(l=10, r=10, t=10, b=30),
                      **theme.PLOTLY_LAYOUT)
cyc_fig.update_layout(legend=dict(orientation="h", y=1.08, x=0),
                      xaxis=dict(title="cycle", type="category"), yaxis=dict(title="asks / intros"),
                      yaxis2=dict(overlaying="y", side="right", tickformat=".0%", rangemode="tozero",
                                  title="capacity used", showgrid=False))
cyc_div = plot(cyc_fig, "cycles-chart")


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


cyc_connector_rows = [(p["connector"], p["rows"][-1]["capacity"], f'{p["rows"][-1]["used"]} ({p["rows"][-1]["capacity_pct"]:.0%})',
                       p["rows"][-1]["intros"], p["rows"][-1]["intros_cumulative"],
                       f'{sum(r["asks"] for r in p["rows"]) / len(p["rows"]):.1f}',
                       f'{sum(r["capacity_pct"] for r in p["rows"][:-1]) / max(1, len(p["rows"]) - 1):.0%}',
                       f'{sum(r["intros"] for r in p["rows"]) / len(p["rows"]):.1f}')
                      for p in cycles["per_connector"]]
cyc_connector_table = table(["Connector", "Capacity/mo", "Slots used this cycle", "Intros this cycle", "Cumulative intros",
                             "Asks / cycle", "Capacity used / cycle", "Intros / cycle"], cyc_connector_rows)
cyc_prev = [r for r in cyc_rows if not r["current"]]
cyc_avg_pct = sum(r["capacity_pct"] for r in cyc_prev) / len(cyc_prev) if cyc_prev else 0

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
section{{background:var(--surface);border:1px solid var(--line);padding:28px 32px;margin:0 0 20px;scroll-margin-top:calc(var(--topbar,140px) + 16px)}}
h2{{margin:0 0 6px;font-size:22px}}
h3{{margin:28px 0 10px;font-size:12px;font-weight:500;color:var(--mute);text-transform:uppercase;letter-spacing:.08em}}
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
.kpi .l{{margin-top:6px;font-weight:500;font-size:13px}}
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
table.cycles td.date{{font-family:var(--mono);font-size:12.5px;white-space:nowrap}}
table.cycles tr.now td{{background:{theme.rgba(theme.BATON, 0.08)};font-weight:500}}
table.cycles tr.now td .foot{{font-weight:400}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:32px}}
.grid2>*{{min-width:0}}
@media(max-width:900px){{.grid2{{grid-template-columns:1fr}}}}
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
#lp h2 .foot{{display:block;font-weight:400;margin-top:2px}}
#lp details.fold{{margin:0}}
#lp .fold summary{{display:flex;align-items:flex-start;gap:16px;margin:0}}
#lp .fold summary::before{{content:none}}
#lp .fold summary h2{{flex:1}}
#lp .fold summary::after{{content:"▾";color:var(--mute);font-size:24px;line-height:1.1;padding-top:2px;transform:rotate(-90deg);transition:transform .15s}}
#lp .fold[open] summary::after{{transform:none}}
#lp .fold summary:hover::after{{color:var(--ink)}}
#lp .fold[open] summary{{margin-bottom:6px}}
#lp .lede{{font-size:15.5px}}
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
#lp .strip .l{{margin-top:8px;font-size:13px;font-weight:500;text-transform:uppercase;letter-spacing:.06em;color:var(--mute)}}
@media(max-width:900px){{#lp .strip{{grid-template-columns:repeat(3,1fr)}}}}
#lp table.top td.order{{color:var(--mute)}}
#lp table.top td.ev{{font-size:18px;font-weight:500;color:var(--blue)}}
#lp table.top tr.done td{{color:var(--mute);text-decoration:line-through}}
#lp table.top tr.done td.ev{{color:var(--mute)}}
#lp table.top tr.quiet td{{color:var(--mute)}}
#lp table.top .tick{{width:16px;height:16px;accent-color:var(--blue)}}
#lp .parts .c{{border-bottom:1px dotted var(--mute);cursor:help}}
#lp th .fm{{font-weight:400;font-size:11px;text-transform:none;letter-spacing:0}}
#lp .formula{{margin-top:14px;padding:12px 16px;background:var(--bg);border-left:2px solid var(--blue)}}
#lp .formula p{{margin:0 0 6px}}
#lp .subtabs{{display:flex;flex-wrap:wrap;gap:4px;margin:12px 0 18px;border-bottom:1px solid var(--line)}}
#lp .subtabs button{{font-family:var(--sans);font-size:14px;color:var(--mute);background:none;border:1px solid transparent;padding:8px 14px;margin-bottom:-1px;cursor:pointer}}
#lp .subtabs button .n{{margin-left:8px;font-size:12px;color:var(--mute);font-variant-numeric:tabular-nums}}
#lp .subtabs button.on{{color:var(--ink);background:var(--surface);border-color:var(--line) var(--line) var(--surface)}}
#lp .dl{{display:flex;gap:16px;align-items:flex-start;margin:14px 0;font-size:14px;font-family:var(--sans)}}
#lp .dl span{{color:var(--mute);padding-top:6px}}
#lp button:not(.subtabs button){{font-family:var(--sans);font-size:14px;font-weight:500;background:var(--blue);color:#fff;border:1px solid var(--blue);padding:8px 16px;cursor:pointer;white-space:nowrap}}
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
#lp .stamp a{{color:inherit}}
#lp table.top .tick:disabled{{opacity:.55}}
#lp table.preview tr.flag td{{background:rgba(159,45,0,.035)}}
#lp .presets{{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 8px;font-family:var(--sans);font-size:12.5px;color:var(--mute);align-items:center}}
#lp .presets button{{font-size:12.5px;padding:5px 10px}}
#lp .ask{{display:flex;gap:10px;align-items:stretch}}
#lp textarea{{flex:1;font-family:var(--serif);font-size:15px;line-height:1.45;padding:10px 12px;border:1px solid var(--line);background:var(--surface);color:var(--ink);resize:vertical;min-height:64px}}
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
  main{{padding:16px 10px 64px}}
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
NO_PEOPLE_ROW = {LIVE_HTML, RAW_HTML}


connector_pages = connector_fragments(TODAY)
MASTHEAD = (f'<a class="mast" href="{LIVE_HTML}">{theme.logo()}'
            '<span class="t"><b>Halyard Baton</b> / intro routing console</span></a>')


def tabs(active):
    """The sticky bar on every page: the masthead across the top, the page tabs, and
    under Live Priorities a sub-row in the baton colour with one tab per connector.
    The connector row belongs to Live Priorities, so the two data dashboards go without
    it; on a connector's page the Live Priorities tab is marked as the parent."""
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


# Back-to-top button; the topbar's height as --topbar so anchors land below it; every table
# in a horizontally scrolling wrapper (the wide ones overflow a phone screen); and on a narrow
# screen the tab rows scroll sideways, so bring the active tab into view.
TOTOP = """<button class="totop" type="button" title="Back to top" aria-label="Back to top">&uarr;</button>
<script>
(function () {
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

  var wrap = function () {
    document.querySelectorAll('table').forEach(function (t) {
      if (t.parentElement.classList.contains('tscroll')) return;
      var row = t.querySelector('tr'), cols = 0;
      if (row) for (var i = 0; i < row.cells.length; i++) cols += row.cells[i].colSpan;
      t.style.setProperty('--tmin', Math.min(cols * 130, 1100) + 'px');
      var d = document.createElement('div');
      d.className = 'tscroll';
      t.parentNode.insertBefore(d, t);
      d.appendChild(t);
    });
  };
  wrap();
  new MutationObserver(wrap).observe(document.body, { childList: true, subtree: true });

  bar.querySelectorAll('.tabs').forEach(function (row) {
    var on = row.querySelector('a.on, a.parent');
    if (on && row.scrollWidth > row.clientWidth) row.scrollLeft = on.offsetLeft - (row.clientWidth - on.offsetWidth) / 2;
  });
})();
</script>"""


built = f"built {datetime.now():%Y-%m-%d}"


def head(title):
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>Halyard — {title}</title>\n'
            f'<script src="https://cdn.plot.ly/plotly-3.0.1.min.js"></script>\n{theme.FONT_LINK}\n{STYLE}</head>')


raw_page = f"""{head("raw Sept data dashboard")}
<body>
{tabs(RAW_HTML)}
<header>
  <h1>Raw Sept data — scoping &amp; verification</h1>
  <p>200 warm-intro requests · Aug 2025 – Jul 2026 · source: the September exports in <code>dataset/</code>, as filed · {built}</p>
  <nav style="margin-top:12px"><a href="#flow">File flow</a><a href="#overview">Funnel overview</a><a href="#joins">Joins</a><a href="#targets">Target people</a><a href="#timing">Timing</a><a href="#scoping">Slack threads</a><a href="#quality">Flags &amp; coverage</a><a href="#verify">CSV profile</a><a href="#integrity">Integrity audit</a></nav>
</header>
<main>

<p class="lede part-lede">Computed directly from the exports in <code>dataset/</code>: intro requests and outcomes, CRM accounts, connection lists, roster and Slack threads, as filed. The <a href="{LIVE_HTML}">Live Data Dashboard</a> tab shows the same requests after entity resolution.</p>

<section id="flow">
  <h2>How the files connect</h2>
  <p class="lede">An intro request moves from Slack to a logged outcome; the four reference tables feed the routing step by name/company text only — <code>request_id</code> is the sole real key.</p>
  <img src="routing_flow.png" alt="Intro-request routing flow across the CSV files" style="display:block;max-width:720px;width:100%;margin:0 auto">
  <p class="foot">Source: <code>analysis/routing/routing_flow.mmd</code>; narrative in <code>analysis/routing/routing_flow.md</code>.</p>
</section>

<section id="overview">
  <h2>Funnel overview</h2>
  <p class="lede">Every request drops out at the first stage it fails, so the eight buckets partition all {ov_n} requests. Unrouted requests split on whether the target company appears in <code>dataset/connections_*.csv</code>; a target counts as identifiable when a company can be recovered from <code>target_company_raw</code>, the company names in <code>raw_ask</code>, or an email domain in <code>raw_ask</code>.</p>
  {overview_table}
  <p class="foot">Buckets and ratios: <code>dashboard/funnel_overview.py</code> (also prints the table standalone).</p>
</section>

<section id="joins">
  <h2>Scoped joins</h2>
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
      <div class="finding"><b><code>intro_outcomes.request_id</code> -> <code>intro_requests.request_id</code> — 100%.</b>Every outcome row resolves to a real request and no request_id is duplicated, so the funnel is safe to read forward from a request.</div>
      <div class="finding"><b><code>requested_by</code> -> <code>crm_accounts.owner</code> — 100% / 100%.</b>The same eight names, spelled identically, on both sides — requester-level and owner-level analysis can be mixed freely.</div>
      <div class="finding"><b><code>connector_roster.connections_file</code> -> files on disk — 100%.</b>Supply is fully enumerable: six rosters, six exports, {len(cuts["connections"]):,} contacts.</div>
    </div>
    <div>
      <h3>Joins that break the analysis</h3>
      <div class="finding warn"><b><code>target_person_raw</code> -> <code>connections_*.name</code> — 0% / 0%.</b>Not one of the {targets["distinct"]} named individuals appears anywhere in the network (see below). Person-level routing is impossible; only the company can be matched.</div>
      <div class="finding warn"><b><code>connector_asked</code> -> <code>connector_roster.name</code> — 54.5%.</b>{sum(n for _, n in connectors["off_roster"])} asks went to {len(connectors["off_roster"])} people who are not connectors ({", ".join(n for n, _ in connectors["off_roster"])}), so capacity and focus-area rules never applied to them.</div>
      <div class="finding warn"><b><code>target_company_raw</code> -> <code>crm_accounts.account_name</code> — 71.2% only after normalization.</b>Exact match is 65.4%; the CRM side needs legal-suffix stripping to reach 84%. Every company cut below is therefore built on the resolved <code>golden/</code> company id, not the raw string.</div>
      <div class="finding warn"><b><code>connections_*.company</code> -> <code>target_company_raw</code> — 58% / 55.8%.</b>Supply and demand barely overlap: 21 companies in the network are never requested and 23 requested companies have no contact at all.</div>
    </div>
  </div>
  <h3>All measured links</h3>
  {joins_table}
</section>

<section id="targets">
  <h2>Target people — does the named individual exist anywhere?</h2>
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
      <div class="finding warn"><b><code>target_person_raw</code> is unjoinable by construction.</b>All {targets["distinct"]} names are distinct, none appears in {len(cuts["connections"]):,} contacts, {len(cuts["investors"])} investor rows, the roster, the CRM owners or as a Slack author. Every surname token, however, is a surname that does occur in the network — the names are recombinations, so any fuzzy matcher will produce plausible false positives.</div>
      <div class="finding"><b>The usable signal is the title, not the person.</b>For {targets["title_reachable"]} of the {targets["named"]} person-named requests, a contact at the same company already holds exactly the requested title — routing should match company plus title and ignore the name.</div>
      <div class="finding"><b>Data point to track:</b><code>target_person_resolvable</code> = 0 / {targets["distinct"]}, <code>target_title_reachable</code> = {targets["title_reachable"]} / {targets["named"]}. Recomputed on every build in <code>dashboard/data_cuts.py</code>.</div>
    </div>
  </div>
</section>

<section id="timing">
  <h2>Routing time and completion</h2>
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
      <div class="finding"><b>Routing is fast; everything after it is not.</b>When a request is routed at all it is routed in {timing['mean_to_ask']:.1f} days on average (max {max(timing['to_ask'])}), but the intro lands {timing['mean_to_intro']:.1f} days after the request — the delay is the connector, not the triage.</div>
      <div class="finding warn"><b>Completion is flat, not improving.</b>Weekly volume swings between {min(w[1] for w in timing["weekly"])} and {max(w[1] for w in timing["weekly"])} requests, and the 4-week rolling completion rate stays inside {min(r for r in roll if r is not None):.0%}–{max(r for r in roll if r is not None):.0%} across all {len(timing["weekly"])} weeks. Month over month it never exceeds {max(i/n for _, n, _, i, _ in timing["monthly"]):.0%}.</div>
      <div class="finding warn"><b>Week-over-week trending is noisy by construction.</b>The median week holds {statistics.median([w[1] for w in timing["weekly"]]):.0f} requests, so a single intro moves the weekly rate by tens of points; the rolling line above is the honest read.</div>
    </div>
  </div>
</section>

<section id="scoping">
  <h2>Scoping — what happens in <code>#intro-requests</code></h2>
  <p class="lede">From <code>dataset/slack_threads.jsonl</code>: {len(threads)} threads, {sum(len(t["messages"]) for t in threads)} messages, {len(replies)} replies. Full write-up in <code>analysis/slack/slack_thread_findings.md</code>.</p>
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
  <h3>Duplicate-checking replies</h3>
  <div class="grid2">
    <div>
      {dup_table}
      <p class="foot">Matched on <code>same as</code>, <code>already lost/asked</code>, <code>last month</code>, <code>duplicate</code> in <code>dashboard/data_cuts.py</code>.</p>
    </div>
    <div>
      <div class="finding warn"><b>{slack["dups"]} of {slack["replies"]} replies ({slack["dups"]/slack["replies"]:.0%}) are someone asking whether this ask is a duplicate.</b>They appear in {slack["dup_threads"]} of the {slack["threads"]} threads, and only {slack["dup_threads_with_intro"]} of those threads ever produced an intro. Nobody ever answers the question in-thread.</div>
      <div class="finding"><b>The question is well-founded.</b>{demand["repeat_share"]:.0%} of asks are for a company that was already requested, so "is this the same as the one from last month?" is usually yes — and the answer already exists in <code>golden/golden_companies.csv</code> (<code>total_requests</code>, <code>latest_request_id</code>).</div>
    </div>
  </div>
  <h3>Offers to help with no logged ask</h3>
  {table(["request_id", "Offered by", "deal_value_usd", "Request status", "Reply"],
         [(rid, m["user"], f"{float(requests[rid]['deal_value_usd']):,.0f}", requests[rid]["status"], m["text"]) for rid, m in offers_unlogged])}
</section>

<section id="quality">
  <h2>Flags, statuses and outcome coverage</h2>
  <p class="lede">Whether <code>path_found_flag</code> and <code>status</code> carry information, and whether <code>intro_outcomes.csv</code> is a deliberate subset of <code>intro_requests.csv</code> or a coverage hole.</p>
  <div class="kpis">
    {kpi(f"{(noise['flags']['(blank)'] + noise['flags']['Unknown'])/len(requests):.0%}", "of path_found_flag is blank or Unknown", f"{noise['flags']['(blank)']} blank · {noise['flags']['Unknown']} Unknown")}
    {kpi(sum(n for _, n in noise["contradictions"]), "flag/status contradictions", "across the six checks below")}
    {kpi(f"{coverage['matched']} / {coverage['requests']}", "requests with an outcome row", f"{coverage['orphan_outcomes']} orphan outcome rows")}
    {kpi(coverage["should_exist"], "missing rows that must exist", f"status is Routed or Intro sent · {usd(coverage['should_exist_value'])}")}
  </div>
  <div class="grid2">
    <div>
      <h3>path_found_flag x status</h3>
      {matrix_table}
      <h3>What the flag actually predicts</h3>
      {reality_table}
      <p class="foot">"Company has a path" is measured against <code>golden/supply_reach.csv</code>, i.e. the network, not the flag.</p>
    </div>
    <div>
      <h3>Findings</h3>
      <div class="finding warn"><b><code>path_found_flag</code> is noise for {(noise["flags"]["(blank)"] + noise["flags"]["Unknown"])/len(requests):.0%} of requests.</b>{noise["flags"]["(blank)"]} are blank and {noise["flags"]["Unknown"]} say <code>Unknown</code>; of the blank ones {noise["flag_reality"]["(blank)"]["paths"]/noise["flag_reality"]["(blank)"]["requests"]:.0%} actually do have a path in the network, so blank does not mean "no path".</div>
      <div class="finding warn"><b>Where it is filled in, it contradicts the outcome.</b>{dict(noise["contradictions"])["flag <code>Path found</code> yet nobody was ever asked"]} requests flagged <code>Path found</code> were never routed, and {dict(noise["contradictions"])["flag <code>No path found</code> yet an intro was sent"]} flagged <code>No path found</code> ended in an intro. The two fields are maintained independently of the funnel.</div>
      <div class="finding warn"><b><code>status</code> and the outcome rows disagree both ways.</b>{dict(noise["contradictions"])["status <code>Intro sent</code> with no <code>intro_sent=Y</code> outcome row"]} requests claim status <code>Intro sent</code> with no such outcome row, while {dict(noise["contradictions"])["<code>intro_sent=Y</code> while status is still Open/Stalled/Routed"]} requests with a sent intro still show Open/Stalled/Routed. Neither field can be used as the funnel stage — <code>intro_outcomes.csv</code> has to be the source of truth.</div>
      {contradiction_table}
    </div>
  </div>
  <h3>intro_outcomes vs intro_requests — subset or coverage hole?</h3>
  <div class="grid2">
    <div>
      {coverage_table}
    </div>
    <div>
      <div class="finding warn"><b>It is a coverage hole, not a subset.</b>All {coverage["outcomes"]} outcome rows resolve to a request and none is duplicated, so the file is clean in that direction. But {coverage["should_exist"]} of the {coverage["missing"]} requests with no outcome row are filed as <code>Routed</code> or <code>Intro sent</code> ({usd(coverage["should_exist_value"])}) — a routed request must have an ask, so those rows are missing rather than not-yet-existing.</div>
      <div class="finding warn"><b>Slack shows the same gap.</b>{coverage["offered_in_slack"]} of the requests with no outcome row have someone in-thread saying they would take it — the ask happened, the row was never written.</div>
      <div class="finding"><b>The rest is plausibly genuine.</b>The remaining {coverage["missing"] - coverage["should_exist"]} are Open, Stalled or Closed - no path, i.e. requests that legitimately never reached a connector. Treat {coverage["matched"]}/{coverage["requests"]} as the ceiling on funnel coverage and {coverage["should_exist"]} as the known write-back defect.</div>
    </div>
  </div>
</section>

<section id="verify">
  <h2>Verification — CSV inventory profile</h2>
  <p class="lede">From <code>analysis/profile/profile.md</code> (generated by <code>analysis/profile/profile_csvs.py</code>): {len(inventory)} CSV files, {sum(r for _, r, _, _ in inventory):,} data rows, {len(flags)} column-level flags.</p>
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
</body></html>
"""

live_page = f"""{head("live data dashboard")}
<body>
{tabs(LIVE_HTML)}
<header>
  <h1>Live data — funnel, accounts and connectors</h1>
  <p>The same {len(requests)} requests after entity resolution · source: <code>golden/</code>, rebuilt from <code>dataset/</code> by <code>python3 build.py</code> · {built}</p>
  <nav style="margin-top:12px"><a href="#funnel">Funnel</a><a href="#accounts">Accounts</a><a href="#connectors">Connectors</a><a href="#cycles">Intros by cycle</a></nav>
</header>
<main>

<p class="lede part-lede">Computed from <code>golden/</code> — <code>golden_requests.csv</code>, <code>golden_companies.csv</code>, <code>supply_reach.csv</code> — after entity resolution, so companies are counted by identity rather than by how the name was typed.</p>

<section id="funnel">
  <h2>Where the requests go</h2>
  <p class="lede">From <code>golden/golden_requests.csv</code>. Node labels show how many requests survive each step. Pipeline $ is deliberately omitted: the same <code>deal_value_usd</code> would be re-counted at every stage a request passes through.</p>
  <div class="seg" id="funnel-toggle" data-scope="funnel" role="tablist"><button class="on" data-view="all" role="tab">Cumulative</button><button data-view="12m" role="tab">Last 12 months</button></div>
  <span class="foot" id="funnel-window" data-all="every request on file, {stages_first} to {stages_last}" data-12m="requests dated {ROLLING_SINCE} or later ({counts_12m[0]} of {counts[0]}), rolling from the build date">every request on file, {stages_first} to {stages_last}</span>
  <div class="fview" data-view="12m" hidden>
  {funnel_kpis(counts_12m)}
  {sankey_div_12m}
  <div class="grid2">
    <div>
      <h3>Stage table — last 12 months</h3>
      {funnel_table(stages_12m)}
    </div>
    <div>
      <h3>Reading it</h3>
      <div class="finding warn"><b>The biggest leak is still before anyone is asked.</b>{counts_12m[0]-counts_12m[1]} of {counts_12m[0]} requests ({pct(counts_12m[0]-counts_12m[1], counts_12m[0])}) never reach a connector.</div>
      <div class="finding"><b>Once asked.</b>{pct(counts_12m[2], counts_12m[1])} respond, {pct(counts_12m[3], counts_12m[2])} of responders send the intro, {pct(counts_12m[4], counts_12m[3])} of intros book a meeting, {pct(counts_12m[5], counts_12m[4])} of meetings create an opportunity.</div>
      <p class="foot">Same stages and source as the cumulative view, restricted to <code>request_date &gt;= {ROLLING_SINCE}</code>; the window moves every time the page is rebuilt.</p>
    </div>
  </div>
  </div>
  <div class="fview" data-view="all">
  {funnel_kpis(counts)}
  {sankey_div}
  <div class="grid2">
    <div>
      <h3>Stage table</h3>
      {funnel_table(stages)}
    </div>
    <div>
      <h3>Reading it</h3>
      <div class="finding warn"><b>The biggest leak is before anyone is asked.</b>{counts[0]-counts[1]} of {counts[0]} requests ({(counts[0]-counts[1])/counts[0]:.0%}) never reach a connector — larger than every downstream drop combined.</div>
      <div class="finding"><b>Once asked, the funnel is healthy-ish.</b>{counts[2]/counts[1]:.0%} respond, {counts[3]/counts[2]:.0%} of responders send the intro, {counts[4]/counts[3]:.0%} of intros book a meeting, {counts[5]/counts[4]:.0%} of meetings create an opportunity.</div>
      <div class="finding"><b>Status and outcomes disagree.</b>{len(opp_status_mismatch)} of the {counts[5]} opportunity requests still show status Open/Stalled/Routed in <code>intro_requests.csv</code> ({", ".join(opp_status_mismatch)}).</div>
      <p class="foot">Standalone chart + code: <code>dashboard/sankey_funnel.py</code>, <code>docs/sankey_funnel.html</code>.</p>
    </div>
  </div>
  </div>
</section>

<section id="accounts">
  <h2>Account-level demand</h2>
  <p class="lede">Asks per company after entity resolution ({len(demand["companies"])} distinct companies behind {len(requests) - unresolvable_asks} of {len(requests)} requests, from <code>golden/golden_requests.csv</code>), split by whether a connector was ever asked. The {unresolvable_asks} asks that resolve to no company are grouped by why, not by the name written.</p>
  <div class="kpis">
    {kpi(len(demand["companies"]), "distinct companies requested", f"{demand['repeat_share']:.0%} of asks are for a repeat company")}
    {kpi(demand["singletons"], "companies asked exactly once", f"{len(demand['companies']) - demand['singletons']} asked more than once")}
    {kpi(demand["companies"][0]["requests"], f"asks for {demand['companies'][0]['name']}", "the most-requested company")}
    {kpi(sum(1 for b in demand["companies"] if b["routed"] == 0), "companies never routed once", "nobody was asked for any of their requests")}
  </div>
  <div class="grid2">
    <div id="demand-views">
      <h3>Top 20 companies by asks</h3>
      <div class="seg" id="demand-toggle" data-scope="demand-views" role="tablist"><button class="on" data-view="all" role="tab">Cumulative</button><button data-view="12m" role="tab">Last 12 months</button></div>
      <span class="foot" id="demand-views-window" data-all="every request on file, {stages_first} to {stages_last}" data-12m="requests dated {ROLLING_SINCE} or later ({demand_12m['asks']} of {demand['asks']} asks, {len(demand_12m['companies'])} companies), rolling from the build date">every request on file, {stages_first} to {stages_last}</span>
      <div class="fview" data-view="12m" hidden>{demand_div_12m}</div>
      <div class="fview" data-view="all">{demand_div}</div>
    </div>
    <div>
      <h3>Reading it</h3>
      <div class="finding warn"><b>Demand is concentrated and repetitive.</b>{demand['repeat_share']:.0%} of all asks are for a company that was already requested at least once — the same {len(demand['companies']) - demand['singletons']} companies come back again and again, which is what the duplicate-checking in Slack is reacting to.</div>
      <div class="finding warn"><b>Some companies are asked repeatedly and never routed.</b>{", ".join(b["name"] for b in demand["companies"][:20] if b["routed"] == 0)} each have multiple asks and zero connector rows.</div>
      <div class="finding"><b>Unresolvable asks cluster too.</b>{unresolvable_asks} requests resolve to no company at all: {"; ".join(f'{b["requests"]} {b["name"].strip("()")}' for b in demand["unresolvable"])}. They sit at the bottom of the detail table and are excluded from the company counts above.</div>
    </div>
  </div>
  <h3>Per-company detail</h3>
  <p class="foot">Paths in network = distinct ways to reach the company in <code>golden/supply_reach.csv</code>.</p>
  {demand_table}
  <h3>Top 20 accounts by value</h3>
  <p class="lede">Value is the CRM <code>arr_potential_usd</code> where the company has a CRM account, otherwise the largest <code>deal_value_usd</code> filed on a request. Internal touchpoints are split into roster connectors employed internally versus advisors and investors.</p>
  {top_table}
</section>
<script>
(function () {{
  // Cumulative / Last 12 months: each .seg swaps the .fview blocks inside its data-scope element
  document.querySelectorAll('.seg[data-scope]').forEach(function (seg) {{
    var scope = document.getElementById(seg.dataset.scope), note = document.getElementById(seg.dataset.scope + '-window');
    seg.querySelectorAll('button').forEach(function (b) {{
      b.onclick = function () {{
        seg.querySelectorAll('button').forEach(function (x) {{ x.classList.toggle('on', x === b); }});
        scope.querySelectorAll('.fview').forEach(function (v) {{
          v.hidden = v.dataset.view !== b.dataset.view;
          if (!v.hidden && window.Plotly) v.querySelectorAll('.js-plotly-plot').forEach(function (p) {{ Plotly.Plots.resize(p); }});
        }});
        if (note) note.textContent = note.dataset[b.dataset.view];
      }};
    }});
  }});
}})();
</script>

<section id="connectors">
  <h2>Connectors — the six on the roster</h2>
  <p class="lede">Funnel per connector from <code>intro_outcomes.csv</code>, with the stated capacity and free-text note from <code>dataset/connector_roster.csv</code>. An ask is "in focus area" when the resolved company's CRM industry is one of the connector's stated focus areas.</p>
  <div class="kpis">
    {kpi(f"{connectors['in_focus']} / {connectors['asked']}", "asks inside the stated focus area", f"over {connectors['months']} months")}
    {kpi(f"{connectors['in_focus_intro_rate']:.0%}", "intro rate for in-focus asks", f"vs {connectors['off_focus_intro_rate']:.0%} outside the focus area")}
    {kpi(f"{connectors['connectors'][0]['asked']}", f"asks to {connectors['connectors'][0]['name']}", "the most-asked connector")}
    {kpi(sum(n for _, n in connectors["off_roster"]), "asks to people not on the roster", ", ".join(n for n, _ in connectors["off_roster"]))}
  </div>
  {connector_table}
  <div class="grid2">
    <div>
      <h3>Routing ignores the roster notes</h3>
      <div class="finding warn"><b>Only {connectors['in_focus']} of {connectors['asked']} asks land in a stated focus area — and those convert at {connectors['in_focus_intro_rate']:.0%} vs {connectors['off_focus_intro_rate']:.0%}.</b>Focus area is the single strongest predictor of an intro in this data, and it is almost never used when choosing who to ask.</div>
      <div class="finding warn"><b>The notes predicted the failures.</b>Owen Trask ("tapped no more than twice a month") was asked {[c["asked"] for c in connectors["connectors"] if c["name"] == "Owen Trask"][0]} times in {connectors["months"]} months and sent zero intros; Dana Whitfield ("travels constantly; slow to respond") got {[c["asked"] for c in connectors["connectors"] if c["name"] == "Dana Whitfield"][0]} asks and booked no meetings.</div>
    </div>
    <div>
      <h3>Where the notes were right</h3>
      <div class="finding"><b>Elena Duvall — "deep but narrow".</b>{[c["in_focus"] for c in connectors["connectors"] if c["name"] == "Elena Duvall"][0]} of her {[c["asked"] for c in connectors["connectors"] if c["name"] == "Elena Duvall"][0]} asks were heavy industry, and that is where her intros came from.</div>
      <div class="finding"><b>Marcus Aldridge — "asked far more than anyone else", capacity 4/month.</b>{[c["asked"] for c in connectors["connectors"] if c["name"] == "Marcus Aldridge"][0]} asks with the weakest response rate of the four heavily-used connectors ({[f"{c['responded']/c['asked']:.0%}" for c in connectors["connectors"] if c["name"] == "Marcus Aldridge"][0]}).</div>
      <div class="finding"><b>Tomás Beckett — "fast responder, broad but shallow".</b>{[f"{c['responded']/c['asked']:.0%}" for c in connectors["connectors"] if c["name"] == "Tomás Beckett"][0]} response rate but only {[f"{c['intros']/c['responded']:.0%}" for c in connectors["connectors"] if c["name"] == "Tomás Beckett"][0]} of those responses became an intro.</div>
    </div>
  </div>
</section>

<section id="cycles">
  <h2>Intros by cycle</h2>
  <p class="lede">Every connector summed, one row per cycle (a calendar month, the allocator's unit) from the first ask on file to the current cycle {cycles["cycle"]}. Asks by <code>asked_date</code> and intros by <code>intro_date</code> from <code>intro_outcomes.csv</code>; capacity used is roster asks against the roster's stated monthly capacity of {cycles["roster_capacity"]} in <code>connector_roster.csv</code>. The current cycle counts this build's allocation as slots used, since those asks are about to go out. Each connector's own record is on their tab under Live Priorities.</p>
  <div class="kpis">
    {kpi(cycles["current"]["intros"], "intros made this cycle", f"{cycles['cycle']} · {cyc_prev[-1]['intros'] if cyc_prev else 0} in {cyc_prev[-1]['cycle'] if cyc_prev else 'the cycle before'}")}
    {kpi(cycles["intros_total"], "cumulative intros", f"since {cycles['rows'][0]['cycle']}, from {cycles['asks_total']} asks")}
    {kpi(f"{cycles['current']['capacity_pct']:.0%}", "roster capacity used this cycle", f"{cycles['current']['used']} of {cycles['roster_capacity']} slots" + (f" · {cycles['current']['allocated_off_roster']} more allocated off-roster" if cycles['current']['allocated_off_roster'] else ""))}
    {kpi(f"{cyc_avg_pct:.0%}", "capacity used per cycle, to date", f"average over {len(cyc_prev)} closed cycles; best month {cycles['best']['cycle']} with {cycles['best']['intros']} intros")}
  </div>
  {cyc_div}
  <div class="grid2">
    <div>
      <h3>By cycle, all connectors</h3>
      {cycle_table(cyc_rows)}
    </div>
    <div>
      <h3>Reading it</h3>
      <div class="finding warn"><b>Closed cycles used {cyc_avg_pct:.0%} of roster capacity.</b>That is the average against {cycles['roster_capacity']} stated monthly slots; the busiest month used {max(r['capacity_pct'] for r in cyc_prev):.0%}. {"This cycle's allocation is the first to fill it." if cycles['current']['capacity_pct'] >= 1 else f"This cycle's allocation takes it to {cycles['current']['capacity_pct']:.0%}."}</div>
      <div class="finding"><b>Intros arrive at roughly {cycles['intros_total'] / max(1, len(cyc_prev)):.1f} a month.</b>{cycles['intros_total']} intros over {len(cyc_prev)} closed cycles from {cycles['asks_total']} asks — about one intro per {cycles['asks_total'] / max(1, cycles['intros_total']):.1f} asks. The cumulative line is the honest read; single months swing between {min(r['intros'] for r in cyc_prev)} and {max(r['intros'] for r in cyc_prev)}.</div>
      <p class="foot">Asks to people off the roster ({", ".join(cycles['off_roster'])}) are counted in asks and intros but not against capacity, as they have none stated.</p>
    </div>
  </div>
  <h3>Per connector, this cycle and the run rate</h3>
  {cyc_connector_table}
  <p class="foot">Run-rate columns average every cycle since {cycles['rows'][0]['cycle']}; capacity used per cycle averages closed cycles only. Click a connector's tab for their cycle-by-cycle table.</p>
</section>

<p class="foot">Regenerate with <code>python3 build.py dashboard</code>. Everything on this tab is computed from <code>golden/</code> at build time. The <a href="{TRACE_HTML}">Company Trace</a> tab has the full history of any one company.</p>
</main>
</body></html>
"""

trace_page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Halyard — company trace</title>
{theme.FONT_LINK}
{STYLE}</head>
<body>
{tabs(TRACE_HTML)}
<header>
  <h1>Company trace — the full history of one company</h1>
  <p>What <code>analysis/trace.py</code> prints, for any of the 48 companies with a request · sources: <code>dataset/</code>, <code>golden/</code> · {built}</p>
</header>
<main>
<section id="trace">
  <p class="lede">Search by name, alias, company id or CRM account id. Five sections: the header, where the files disagree (omitted when the files agree), who can reach them by strength, every event from <code>intro_requests.csv</code>, <code>slack_threads.jsonl</code>, <code>intro_outcomes.csv</code> and <code>crm_accounts.csv</code> oldest first, and who needs to do what next, cheapest action first. The same traces are written to <code>analysis/traces/</code> by <code>python3 build.py trace</code>.</p>
  {trace_fragment()}
</section>
<p class="foot">Regenerate with <code>python3 build.py dashboard</code>.</p>
</main>
</body></html>
"""

priorities_page = f"""{head("live priorities")}
<body>
{tabs(PRIORITIES_HTML)}
<header>
  <h1>Live priorities — what to do next, and who does it</h1>
  <p>Every number here is computed by <code>dashboard/live_priorities.py</code> from <code>golden/</code> and <code>dataset/</code> at build time and written into the page; the browser only renders it. Every company name opens its <a href="{TRACE_HTML}">Company Trace</a> · {built}</p>
  <nav style="margin-top:12px">{"".join(f'<a href="#{sid}">{esc(label)}</a>' for sid, label in PRIORITIES_SECTIONS)}</nav>
</header>
<main>
{priorities_fragment()}
<p class="foot">Regenerate with <code>python3 build.py dashboard</code>. Ranking constants live at the top of <code>dashboard/live_priorities.py</code>.</p>
</main>
</body></html>
"""


batch_page = f"""{head("batched-ask for connectors")}
<body>
{tabs(BATCH_HTML)}
<header>
  <h1>Batched-Ask for Connectors — one message per connector, this cycle's batch</h1>
  <p>Each connector's allocated requests from <code>golden/golden_allocation.csv</code>, drafted as a single plain-text ask by <code>dashboard/batch_ask.py</code> at build time with the wording in <code>config/batch_ask_templates.json</code>. Copy, send, then tick <i>ask sent</i> on <a href="{PRIORITIES_HTML}#connectors">Live Priorities</a> or the connector's page — copying writes nothing. Every company name opens its <a href="{TRACE_HTML}">Company Trace</a> · {built}</p>
</header>
<main>
{batch_fragment(TODAY)}
<p class="foot">Regenerate with <code>python3 build.py dashboard</code>. Print the messages with <code>python3 -m dashboard.batch_ask</code>.</p>
</main>
</body></html>
"""


def connector_page(c, frag):
    who = f"{esc(c['role'])} · {esc(c['type'])}" if c["on_roster"] else "not on the roster"
    return f"""{head(esc(c["connector"]))}
<body>
{tabs(c["page"])}
<header>
  <h1>{esc(c["connector"])} — top {len(c["top"])}, then the longer list</h1>
  <p>{who} · {len(c["top"]) + len(c["rest"])} live requests routed to them this cycle, ranked by the same expected value as <a href="{PRIORITIES_HTML}#top">Live Priorities</a>; computed by <code>dashboard/live_priorities.py</code> at build time, rendered by the browser. Every company name opens its <a href="{TRACE_HTML}">Company Trace</a> · {built}</p>
</header>
<main>
{frag}
<p class="foot">Regenerate with <code>python3 build.py dashboard</code>. Ticks are shared with the Live Priorities tab in this browser.</p>
</main>
</body></html>
"""


shutil.copyfile(ROUTING / "routing_flow.png", DOCS / "routing_flow.png")
for old in DOCS.glob("connector-*.html"):
    if old.name not in {c["page"] for c, _ in connector_pages}:
        old.unlink()
for name, markup in (
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
print(f"funnel {counts}  offers {len(offers)} unlogged {len(offers_unlogged)} adds {len(adds)}/{adds_followed} "
      f"no_reply {len(no_reply)}/{len(no_reply_asked)} median_h {statistics.median(first_reply_h):.1f} "
      f"flags {len(flags)} dupes {len(crm_dupes)}/{crm_dup_owner_conflicts}")
