#!/usr/bin/env python3
"""S3 integrity audit over dataset/*.csv.

Emits integrity/findings.md (readable report, one section per check). The same run
also renders the embeddable HTML fragment consumed by dashboard/build_dashboard.py.
Read-only over dataset/; reports, never repairs. Deterministic: stable ordering
everywhere, no timestamps.
"""
import csv
import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "dataset"
OUT = ROOT / "integrity"
AS_OF = dt.date(2026, 9, 3)
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DATE_COLUMNS = {
    "intro_requests.csv": ["request_date"],
    "intro_outcomes.csv": ["asked_date", "response_date", "intro_date"],
    "crm_accounts.csv": ["last_touch_date"],
    "investor_network.csv": ["prior_employer_start", "prior_employer_end"],
}
CONNECTION_FILES = sorted(p.name for p in DATA.glob("connections_*.csv"))
for _f in CONNECTION_FILES:
    DATE_COLUMNS[_f] = ["connected_on"]

PRIMARY_KEY = {
    "intro_requests.csv": "request_id",
    "intro_outcomes.csv": "request_id",
    "crm_accounts.csv": "account_id",
    "connector_roster.csv": "name",
    "investor_network.csv": "person",
}
for _f in CONNECTION_FILES:
    PRIMARY_KEY[_f] = "name"


def load(name):
    with open(DATA / name, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def parse_date(s):
    s = s.strip()
    if not ISO.match(s):
        return None
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def row_key(file, row, idx):
    pk = PRIMARY_KEY.get(file)
    return row.get(pk, "") if pk else f"row {idx}"


class Audit:
    def __init__(self):
        self.checks = []  # ordered metadata
        self.findings = []
        self.rows = {}  # file -> list of rows (for click-through)

    def check(self, check_id, title, severity, denominator, denominator_label, section, columns):
        self.checks.append({
            "check_id": check_id, "title": title, "severity": severity,
            "denominator": denominator, "denominator_label": denominator_label,
            "section": section, "columns": columns,
        })

    def add(self, check_id, severity, file, key, fields, detail):
        self.findings.append({
            "check_id": check_id, "severity": severity, "file": file,
            "row_key": key, "fields": fields, "detail": detail,
        })


def run():
    a = Audit()
    tables = {f: load(f) for f in sorted(PRIMARY_KEY)}
    for f, rows in tables.items():
        a.rows[f] = rows
    req = tables["intro_requests.csv"]
    out = tables["intro_outcomes.csv"]
    roster = tables["connector_roster.csv"]
    crm = tables["crm_accounts.csv"]

    joins = []

    # --- Referential integrity ------------------------------------------
    def id_join(join_id, title, left_file, left_col, right_file, right_col,
                check_left, check_right, sev_left, sev_right, people):
        left = tables[left_file]
        right = tables[right_file]
        lvals = [r[left_col].strip() for r in left]
        rvals = [r[right_col].strip() for r in right]
        lset, rset = set(lvals), set(rvals)
        matched = sorted(lset & rset)
        orph_l = sorted(lset - rset)
        orph_r = sorted(rset - lset)
        a.check(check_left, f"{left_file}.{left_col} not found in {right_file}.{right_col}",
                sev_left, len(left), f"{left_file} rows", "referential", [left_col])
        a.check(check_right, f"{right_file}.{right_col} not found in {left_file}.{left_col}",
                sev_right, len(right), f"{right_file} rows", "referential", [right_col])
        for i, r in enumerate(left, 2):
            v = r[left_col].strip()
            if v not in rset:
                a.add(check_left, sev_left, left_file, row_key(left_file, r, i), {left_col: r[left_col]},
                      f"{left_col}={v!r} has no match in {right_file}.{right_col}")
        for i, r in enumerate(right, 2):
            v = r[right_col].strip()
            if v not in lset:
                a.add(check_right, sev_right, right_file, row_key(right_file, r, i), {right_col: r[right_col]},
                      f"{right_col}={v!r} has no match in {left_file}.{left_col}")
        joins.append({
            "join_id": join_id, "title": title, "people": people,
            "left": {"file": left_file, "column": left_col, "rows": len(left), "distinct": len(lset),
                     "orphans": orph_l, "orphan_rows": sum(1 for v in lvals if v not in rset),
                     "check_id": check_left},
            "right": {"file": right_file, "column": right_col, "rows": len(right), "distinct": len(rset),
                      "orphans": orph_r, "orphan_rows": sum(1 for v in rvals if v not in lset),
                      "check_id": check_right},
            "matched_distinct": len(matched),
            "matched_left_rows": sum(1 for v in lvals if v in rset),
            "matched_right_rows": sum(1 for v in rvals if v in lset),
        })

    id_join("j_request_id", "intro_outcomes.request_id ↔ intro_requests.request_id",
            "intro_outcomes.csv", "request_id", "intro_requests.csv", "request_id",
            "orphan_outcome_request_id", "request_without_outcome", "high", "info", False)
    id_join("j_connector", "intro_outcomes.connector_asked → connector_roster.name",
            "intro_outcomes.csv", "connector_asked", "connector_roster.csv", "name",
            "connector_asked_not_in_roster", "roster_connector_never_asked", "high", "info", True)
    id_join("j_owner", "crm_accounts.owner ↔ intro_requests.requested_by",
            "crm_accounts.csv", "owner", "intro_requests.csv", "requested_by",
            "crm_owner_not_a_requester", "requester_not_a_crm_owner", "medium", "medium", True)

    # duplicate primary keys
    for f in ("intro_requests.csv", "intro_outcomes.csv", "crm_accounts.csv", "connector_roster.csv"):
        pk = PRIMARY_KEY[f]
        cid = f"duplicate_{f.replace('.csv', '')}_{pk}"
        rows = tables[f]
        a.check(cid, f"duplicate {pk} in {f}", "high", len(rows), f"{f} rows", "keys", [pk])
        seen = {}
        for i, r in enumerate(rows, 2):
            seen.setdefault(r[pk].strip(), []).append(i)
        for k in sorted(seen):
            if len(seen[k]) > 1:
                a.add(cid, "high", f, k, {pk: k}, f"{pk}={k!r} appears on lines {seen[k]}")

    # --- Temporal ---------------------------------------------------------
    req_by_id = {r["request_id"].strip(): r for r in req}
    lag_specs = [
        ("lag_response", "response_date − asked_date", "asked_date", "response_date",
         "negative_response_lag"),
        ("lag_intro", "intro_date − response_date", "response_date", "intro_date",
         "negative_intro_lag"),
    ]
    lags = []
    for lag_id, title, c0, c1, cid in lag_specs:
        pairs = [(r, parse_date(r[c0]), parse_date(r[c1])) for r in out]
        both = [(r, d0, d1) for r, d0, d1 in pairs if d0 and d1]
        a.check(cid, f"{c1} earlier than {c0}", "high", len(both),
                f"intro_outcomes rows with both {c0} and {c1}", "temporal", [c0, c1])
        values = []
        for r, d0, d1 in both:
            days = (d1 - d0).days
            values.append({"key": r["request_id"], "days": days})
            if days < 0:
                a.add(cid, "high", "intro_outcomes.csv", r["request_id"],
                      {c0: r[c0], c1: r[c1]}, f"{c1} is {-days} day(s) before {c0}")
        lags.append({"lag_id": lag_id, "title": title, "check_id": cid, "values": values})

    # asked_date before request_date (join through request_id)
    a.check("asked_before_requested", "intro_outcomes.asked_date earlier than intro_requests.request_date",
            "high", sum(1 for r in out if r["request_id"].strip() in req_by_id and parse_date(r["asked_date"])),
            "intro_outcomes rows with a matching request and an asked_date", "temporal",
            ["asked_date", "request_date"])
    for r in out:
        rq = req_by_id.get(r["request_id"].strip())
        d0 = parse_date(r["asked_date"])
        if rq and d0:
            d1 = parse_date(rq["request_date"])
            if d1 and d0 < d1:
                a.add("asked_before_requested", "high", "intro_outcomes.csv", r["request_id"],
                      {"asked_date": r["asked_date"], "request_date": rq["request_date"]},
                      f"asked {(d1 - d0).days} day(s) before the request was made")

    # dates across every date column: future + unparseable
    date_series = []
    for f in sorted(DATE_COLUMNS):
        for col in DATE_COLUMNS[f]:
            rows = tables[f]
            nonempty = [(i, r) for i, r in enumerate(rows, 2) if r[col].strip()]
            fut = f"future_date_{f.replace('.csv', '')}_{col}"
            bad = f"unparseable_date_{f.replace('.csv', '')}_{col}"
            a.check(fut, f"{f}.{col} after {AS_OF.isoformat()}", "medium", len(nonempty),
                    f"non-empty {col} values in {f}", "dates", [col])
            a.check(bad, f"{f}.{col} not an ISO date", "medium", len(nonempty),
                    f"non-empty {col} values in {f}", "dates", [col])
            values = []
            for i, r in nonempty:
                d = parse_date(r[col])
                if d is None:
                    a.add(bad, "medium", f, row_key(f, r, i), {col: r[col]},
                          f"{col}={r[col]!r} is not YYYY-MM-DD")
                    continue
                values.append(d.isoformat())
                if d > AS_OF:
                    a.add(fut, "medium", f, row_key(f, r, i), {col: r[col]},
                          f"{col}={r[col]} is {(d - AS_OF).days} day(s) after {AS_OF.isoformat()}")
            date_series.append({"file": f, "column": col, "check_id": fut, "dates": values})

    # --- Contradictions -----------------------------------------------------
    matrices = []

    def matrix(mid, flag_col, date_col, cid):
        cells = {"YY": [], "YN": [], "NY": [], "NN": []}
        for r in out:
            flag = "Y" if r[flag_col].strip().upper() == "Y" else "N"
            has = "Y" if r[date_col].strip() else "N"
            cells[flag + has].append(r["request_id"])
        a.check(cid, f"{flag_col} disagrees with presence of {date_col}", "high", len(out),
                "intro_outcomes rows", "contradictions", [flag_col, date_col])
        for k in cells["YN"]:
            r = next(x for x in out if x["request_id"] == k)
            a.add(cid, "high", "intro_outcomes.csv", k, {flag_col: r[flag_col], date_col: r[date_col]},
                  f"{flag_col}=Y but {date_col} is empty")
        for k in cells["NY"]:
            r = next(x for x in out if x["request_id"] == k)
            a.add(cid, "high", "intro_outcomes.csv", k, {flag_col: r[flag_col], date_col: r[date_col]},
                  f"{flag_col}=N but {date_col}={r[date_col]}")
        matrices.append({"matrix_id": mid, "flag": flag_col, "date": date_col, "check_id": cid,
                         "cells": {k: {"count": len(v), "keys": v} for k, v in cells.items()}})

    matrix("m_responded", "responded", "response_date", "responded_vs_response_date")
    matrix("m_intro", "intro_sent", "intro_date", "intro_sent_vs_intro_date")

    funnel = [
        ("intro_sent_without_response", "intro_sent", "responded"),
        ("meeting_without_intro", "meeting_booked", "intro_sent"),
        ("opportunity_without_meeting", "opportunity_created", "meeting_booked"),
    ]
    for cid, later, earlier in funnel:
        a.check(cid, f"{later}=Y while {earlier}=N", "high", len(out), "intro_outcomes rows",
                "contradictions", [earlier, later])
        for r in out:
            if r[later].strip().upper() == "Y" and r[earlier].strip().upper() != "Y":
                a.add(cid, "high", "intro_outcomes.csv", r["request_id"],
                      {earlier: r[earlier], later: r[later]}, f"{later}=Y but {earlier}={r[earlier]!r}")

    a.check("opportunity_value_mismatch", "opportunity_created disagrees with opportunity_value_usd",
            "medium", len(out), "intro_outcomes rows", "contradictions",
            ["opportunity_created", "opportunity_value_usd"])
    for r in out:
        created = r["opportunity_created"].strip().upper() == "Y"
        has_val = bool(r["opportunity_value_usd"].strip())
        if created != has_val:
            a.add("opportunity_value_mismatch", "medium", "intro_outcomes.csv", r["request_id"],
                  {"opportunity_created": r["opportunity_created"],
                   "opportunity_value_usd": r["opportunity_value_usd"]},
                  "opportunity_created=Y with no value" if created else "value present but opportunity_created=N")

    # --- Assemble -----------------------------------------------------------
    a.findings.sort(key=lambda x: (x["check_id"], x["file"], x["row_key"], json.dumps(x["fields"], sort_keys=True)))
    counts = {}
    for f in a.findings:
        counts[f["check_id"]] = counts.get(f["check_id"], 0) + 1
    for c in a.checks:
        c["count"] = counts.get(c["check_id"], 0)

    # --- Report context (why a finding count looks the way it does) ---------
    out_ids = {r["request_id"].strip() for r in out}
    status_gap = {}
    for r in req:
        if r["request_id"].strip() not in out_ids:
            status_gap[r["status"].strip() or "(blank)"] = status_gap.get(r["status"].strip() or "(blank)", 0) + 1

    roster_names = {r["name"].strip() for r in roster}
    requesters = {r["requested_by"].strip() for r in req}
    owners = {c["owner"].strip() for c in crm}
    unrostered = {}
    for r in out:
        n = r["connector_asked"].strip()
        if n not in roster_names:
            unrostered[n] = unrostered.get(n, 0) + 1

    flag_cols = ["responded", "intro_sent", "meeting_booked", "opportunity_created"]
    combos = {}
    for r in out:
        key = tuple(r[c].strip().upper() or "-" for c in flag_cols)
        combos[key] = combos.get(key, 0) + 1

    context = {
        "request_without_outcome": {
            "caption": "An outcome row exists only once a connector was actually asked, so this gap is "
                       "expected; the request `status` says whether it is benign.",
            "table": (["status", "requests with no outcome row"],
                      [[s, status_gap[s]] for s in sorted(status_gap, key=lambda s: (-status_gap[s], s))]),
        },
        "connector_asked_not_in_roster": {
            "caption": "Where each unrostered name appears elsewhere in `dataset/` — a name that also "
                       "owns accounts or files requests is a roster omission, not a typo.",
            "table": (["connector_asked", "outcome rows", "also appears as"],
                      [[f"`{n}`", unrostered[n],
                        ", ".join(p for p, s in (("`intro_requests.requested_by`", requesters),
                                                 ("`crm_accounts.owner`", owners)) if n in s) or "nowhere else"]
                       for n in sorted(unrostered, key=lambda n: (-unrostered[n], n))]),
        },
        "contradictions": {
            "caption": "Every observed combination of the four funnel flags, so a clean contradiction "
                       "check can be read against the shape of the funnel it is checking.",
            "table": ([" / ".join(f"`{c}`" for c in flag_cols), "intro_outcomes rows"],
                      [[" / ".join(k), combos[k]] for k in sorted(combos, key=lambda k: (-combos[k], k))]),
        },
    }

    results = {
        "as_of": AS_OF.isoformat(),
        "source": "dataset/",
        "files": {f: {"rows": len(rows), "primary_key": PRIMARY_KEY[f], "columns": list(rows[0].keys()) if rows else []}
                  for f, rows in sorted(tables.items())},
        "checks": a.checks,
        "findings": a.findings,
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "findings.md").write_text(markdown(results, context), encoding="utf-8")

    embedded = {
        "results": results,
        "joins": joins,
        "lags": lags,
        "date_series": date_series,
        "matrices": matrices,
        "rows": {f: rows for f, rows in sorted(tables.items())},
    }
    blob = json.dumps(embedded, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/")
    template = (OUT / "template.html").read_text(encoding="utf-8")
    html = template.replace("/*__DATA__*/", blob)
    print(f"{len(a.findings)} findings across {len(a.checks)} checks -> {OUT / 'findings.md'}")
    return html


SEVERITY_ORDER = {"high": 0, "medium": 1, "info": 2}
SECTION_TITLES = [
    ("referential", "Referential integrity"),
    ("keys", "Primary keys"),
    ("temporal", "Temporal ordering"),
    ("dates", "Date validity"),
    ("contradictions", "Funnel contradictions"),
]


def md_table(header, rows):
    numeric = [all(isinstance(row[i], int) for row in rows) for i in range(len(header))]
    return (["| " + " | ".join(header) + " |",
             "| " + " | ".join("---:" if n else "---" for n in numeric) + " |"]
            + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows])


def md_context(context, key):
    block = context.get(key)
    if not block:
        return []
    return ["", block["caption"], ""] + md_table(*block["table"])


def markdown(results, context):
    checks = results["checks"]
    findings = results["findings"]
    by_check = {}
    for f in findings:
        by_check.setdefault(f["check_id"], []).append(f)
    sev_counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITY_ORDER}

    L = [
        f"# Integrity audit — `dataset/` (as of {results['as_of']})",
        "",
        "Generated by `integrity/integrity_audit.py`. Read-only over `dataset/`: every entry below is a "
        "reported observation, nothing is repaired. `info` findings are expected-shape gaps (e.g. a request "
        "with no outcome row yet), not defects.",
        "",
        f"**{len(findings)} findings across {len(checks)} checks** — "
        f"{sev_counts['high']} high, {sev_counts['medium']} medium, {sev_counts['info']} info. "
        f"{sum(1 for c in checks if c['count'] == 0)} checks are clean.",
        "",
        "## Files audited",
        "",
        "| File | Rows | Primary key | Columns |",
        "| --- | ---: | --- | ---: |",
    ]
    for name, meta in results["files"].items():
        L.append(f"| `{name}` | {meta['rows']} | `{meta['primary_key']}` | {len(meta['columns'])} |")

    L += ["", "## Checks with findings", "", "| Severity | Check | Findings | Rate |", "| --- | --- | ---: | ---: |"]
    hits = sorted((c for c in checks if c["count"]),
                  key=lambda c: (SEVERITY_ORDER[c["severity"]], -c["count"], c["check_id"]))
    for c in hits:
        rate = f"{c['count'] / c['denominator']:.1%}" if c["denominator"] else "—"
        L.append(f"| {c['severity']} | {c['title']} | {c['count']} | {rate} of {c['denominator_label']} |")

    clean = [c for c in checks if not c["count"]]
    if clean:
        L += ["", "## Clean checks", ""]
        L += [f"- {c['title']} (0 of {c['denominator']} {c['denominator_label']})" for c in clean]

    L += ["", "## Findings in detail"]
    for section, title in SECTION_TITLES:
        section_checks = [c for c in hits if c["section"] == section]
        section_context = md_context(context, section)
        if not section_checks and not section_context:
            continue
        L += ["", f"### {title}"]
        if not section_checks:
            L += ["", "Every check in this section is clean."]
        for c in section_checks:
            L += ["", f"#### `{c['check_id']}` — {c['title']}", "",
                  f"Severity {c['severity']}; {c['count']} of {c['denominator']} {c['denominator_label']}.",
                  "", "| File | Row | Values | Detail |", "| --- | --- | --- | --- |"]
            for f in by_check[c["check_id"]]:
                vals = "; ".join(f"`{k}`={v!r}" for k, v in sorted(f["fields"].items()))
                L.append(f"| `{f['file']}` | `{f['row_key']}` | {vals} | {f['detail']} |")
            L += md_context(context, c["check_id"])
        L += section_context

    return "\n".join(L) + "\n"


FRAGMENT_START = "<!--IA-FRAGMENT-START-->"
FRAGMENT_END = "<!--IA-FRAGMENT-END-->"


def fragment():
    """Run the audit and return the embeddable <div id="ia"> block (style + markup + script)."""
    html = run()
    return html[html.index(FRAGMENT_START) + len(FRAGMENT_START):html.index(FRAGMENT_END)].strip()


if __name__ == "__main__":
    run()
