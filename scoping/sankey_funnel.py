"""Sankey of the warm-intro funnel: requests -> asked -> responded -> intros -> meetings -> opportunities.

Counts and dollars are computed from dataset/intro_requests.csv and dataset/intro_outcomes.csv
(deal_value_usd joined on request_id; the final stage uses opportunity_value_usd).
Writes scoping/sankey_funnel.html and scoping/sankey_funnel.png.

    pip install plotly kaleido
    python3 scoping/sankey_funnel.py      # from the repo root
"""
import csv
import os

import plotly.graph_objects as go

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "dataset")
OUT = os.path.dirname(os.path.abspath(__file__))


def money(d):
    return f"&#36;{d/1e6:.1f}M" if d >= 1e6 else f"&#36;{d/1e3:.0f}K"


def funnel_stages():
    with open(os.path.join(DATA, "intro_requests.csv"), newline="", encoding="utf-8") as f:
        req = {r["request_id"]: r for r in csv.DictReader(f)}
    with open(os.path.join(DATA, "intro_outcomes.csv"), newline="", encoding="utf-8") as f:
        out = list(csv.DictReader(f))
    val = lambda o: float(req[o["request_id"]]["deal_value_usd"] or 0)
    stages = [
        ("Requests", list(req.values()), lambda r: float(r["deal_value_usd"] or 0)),
        ("Asked", out, val),
        ("Responded", [o for o in out if o["responded"] == "Y"], val),
        ("Intros", [o for o in out if o["intro_sent"] == "Y"], val),
        ("Meetings", [o for o in out if o["meeting_booked"] == "Y"], val),
        ("Opportunities", [o for o in out if o["opportunity_created"] == "Y"],
         lambda o: float(o["opportunity_value_usd"] or 0)),
    ]
    return [(name, len(s), sum(f(x) for x in s)) for name, s, f in stages]


def build_figure(stages):
    names = [s[0] for s in stages]
    counts = [s[1] for s in stages]
    dollars = [s[2] for s in stages]
    drop_names = ["Never asked", "No response", "No intro", "No meeting", "No opportunity"]

    labels = [f"<b>{n}</b><br>{c} · {money(d)}" for n, c, d in zip(names, counts, dollars)]
    labels += [f"{dn}<br>{counts[i]-counts[i+1]} · {money(dollars[i]-dollars[i+1])}"
               for i, dn in enumerate(drop_names)]
    node_colors = ["#1f5f8b"] * len(names) + ["#b8b8b8"] * len(drop_names)

    src, tgt, vals, link_colors = [], [], [], []
    for i in range(len(names) - 1):
        src += [i, i]
        tgt += [i + 1, len(names) + i]
        vals += [counts[i + 1], counts[i] - counts[i + 1]]
        link_colors += ["rgba(31,95,139,0.45)", "rgba(184,184,184,0.35)"]

    n = len(names)
    x = [i / (n - 1) * 0.9 + 0.02 for i in range(n)] + [i / (n - 1) * 0.9 + 0.11 for i in range(n - 1)]
    y = [0.3] * n + [0.85] * (n - 1)

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(label=labels, color=node_colors, pad=30, thickness=22, x=x, y=y,
                  line=dict(width=0)),
        link=dict(source=src, target=tgt, value=vals, color=link_colors),
    ))
    fig.update_layout(
        title=dict(text=f"Warm-intro funnel: {counts[0]} requests → {counts[-1]} opportunities"
                        f"<br><sup>Node label = count · deal value in pipeline at that stage. "
                        f"Overall: {money(dollars[0])} requested → {money(dollars[-1])} of opportunity created "
                        f"({dollars[-1]/dollars[0]:.1%}). Aug 2025 – Jul 2026.</sup>"),
        font=dict(size=14), width=1400, height=700, margin=dict(l=20, r=20, t=90, b=40),
    )
    return fig


if __name__ == "__main__":
    stages = funnel_stages()
    fig = build_figure(stages)
    fig.write_html(os.path.join(OUT, "sankey_funnel.html"), include_plotlyjs="cdn")
    fig.write_image(os.path.join(OUT, "sankey_funnel.png"), scale=2)
    for name, c, d in stages:
        print(f"{name:14} {c:4} {money(d).replace('&#36;', '$')}")
