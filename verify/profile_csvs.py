"""Column-level inventory profile of every CSV in data/.

Writes verify/profile.md. Uses the csv module so quoted fields containing
commas parse correctly.
"""

import csv
import os
import re
import sys
import unicodedata
from collections import Counter
from datetime import date

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dataset")
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profile.md")

DATE_RE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$")
SLASH_DATE_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\s*$")
INT_RE = re.compile(r"^[+-]?\d+$")
FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
FORMATTED_NUM_RE = re.compile(r"^[+-]?[$€£]?\s?\d{1,3}(,\d{3})+(\.\d+)?%?$|^[+-]?[$€£]\s?\d+(\.\d+)?$|^\d+(\.\d+)?%$")
DATE_MIN, DATE_MAX = date(2020, 1, 1), date(2027, 12, 31)


def md_escape(s):
    if s is None:
        return ""
    s = s.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "\\n").replace("\r", "\\r")
    return s


def clip(s, n=60):
    return s if len(s) <= n else s[: n - 1] + "\u2026"


def cell(s, n=60):
    return "`" + md_escape(clip(s, n)) + "`" if s != "" else "_(empty)_"


def parse_date(v):
    m = DATE_RE.match(v)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = SLASH_DATE_RE.match(v)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        try:
            return date(y, a, b)  # ambiguous m/d vs d/m; only used for range flagging
        except ValueError:
            return None
    return None


MINOR_WORDS = {
    "a", "an", "and", "as", "at", "but", "by", "de", "for", "from", "in", "nor", "of", "on",
    "or", "per", "the", "to", "van", "via", "vs", "with",
}


def case_style(v):
    letters = [c for c in v if c.isalpha()]
    if not letters:
        return None
    if all(c.isupper() for c in letters):
        return "UPPER"
    if all(c.islower() for c in letters):
        return "lower"
    words = [w for w in re.split(r"[\s_/]+", v) if any(c.isalpha() for c in w)]
    if words and all(
        w[0].isupper() or w.lower().strip(".,;:&-") in MINOR_WORDS for w in words if w[0].isalpha()
    ):
        return "Title"
    if v[:1].isupper():
        return "Sentence"
    return "mixed"


LEGAL_SUFFIXES = ("inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "co", "plc", "gmbh", "sa", "nv", "ag")


def normalize_entity(v):
    s = re.sub(r"[^a-z0-9 ]+", " ", v.lower())
    words = [w for w in s.split() if w]
    while words and words[-1] in LEGAL_SUFFIXES:
        words.pop()
    return "".join(words)


def profile_column(name, values):
    total = len(values)
    stripped = [v.strip() for v in values]
    nulls = sum(1 for v in stripped if v == "")
    nonempty = [v for v in stripped if v != ""]
    counter = Counter(nonempty)
    distinct = len(counter)

    dates = [parse_date(v) for v in nonempty]
    date_ok = [d for d in dates if d is not None]
    plain_nums = [v for v in nonempty if INT_RE.match(v) or FLOAT_RE.match(v)]

    kind, mn, mx = "string", "", ""
    if nonempty and len(date_ok) / len(nonempty) >= 0.8:
        kind = "date"
        mn, mx = str(min(date_ok)), str(max(date_ok))
    elif nonempty and len(plain_nums) / len(nonempty) >= 0.8:
        kind = "numeric"
        nums = [float(v) for v in plain_nums]
        fmt = (lambda x: str(int(x))) if all(INT_RE.match(v) for v in plain_nums) else (lambda x: repr(x))
        mn, mx = fmt(min(nums)), fmt(max(nums))

    uniq = sorted(set(nonempty), key=lambda s: (len(s), s))
    shortest = uniq[:3]
    longest = list(reversed(uniq[-3:]))

    flags = []
    ws = [v for v in values if v != v.strip() and v.strip() != ""]
    if ws:
        flags.append(f"leading/trailing whitespace in {len(ws)} value(s), e.g. {cell(repr(ws[0]))}")
    blank_only = sum(1 for v in values if v != "" and v.strip() == "")
    if blank_only:
        flags.append(f"{blank_only} whitespace-only value(s) counted as empty")

    styles = Counter(s for s in (case_style(v) for v in nonempty) if s)
    if len(styles) > 1 and kind == "string":
        top = ", ".join(f"{k}={v}" for k, v in styles.most_common())
        if styles.most_common()[-1][1] / max(1, sum(styles.values())) < 0.98:
            flags.append(f"mixed case conventions ({top})")

    edge_punct = [v for v in nonempty if v[0] in "·.,;:-_*'\"" or v[-1] in "·;:_*"]
    if edge_punct:
        flags.append(
            f"{len(edge_punct)} value(s) start/end with stray punctuation, e.g. {cell(edge_punct[0])}"
        )

    def describe(chars):
        return ", ".join(f"{c!r} ({unicodedata.name(c, 'U+%04X' % ord(c))})" for c in sorted(chars)[:6])

    na_letters = {c for v in nonempty for c in v if ord(c) > 127 and c.isalpha()}
    na_other = {c for v in nonempty for c in v if ord(c) > 127 and not c.isalpha()}
    if na_letters:
        n = sum(1 for v in nonempty if any(c in na_letters for c in v))
        flags.append(f"non-ASCII letters in {n} value(s) (likely legitimate): {describe(na_letters)}")
    if na_other:
        n = sum(1 for v in nonempty if any(c in na_other for c in v))
        flags.append(f"non-ASCII punctuation/symbols in {n} value(s): {describe(na_other)}")

    trunc = [v for v in nonempty if v.endswith(("...", "\u2026")) or v.endswith(("-", ","))]
    if trunc:
        flags.append(f"possible truncation in {len(trunc)} value(s), e.g. {cell(trunc[0])}")
    if nonempty:
        maxlen = max(len(v) for v in nonempty)
        distinct_at_max = len({v for v in nonempty if len(v) == maxlen})
        distinct_below = len({v for v in nonempty if len(v) == maxlen - 1})
        if maxlen >= 15 and distinct_at_max >= 5 and distinct_below == 0:
            flags.append(
                f"{distinct_at_max} distinct values all exactly {maxlen} chars with none at "
                f"{maxlen - 1} (length cap / hard truncation)"
            )

    if kind == "date":
        bad = [str(d) for d in date_ok if d < DATE_MIN or d > DATE_MAX]
        if bad:
            b = sorted(bad)
            flags.append(f"{len(bad)} date(s) outside 2020-2027 (min {b[0]}, max {b[-1]})")
        unparsed = [v for v, d in zip(nonempty, dates) if d is None]
        if unparsed:
            flags.append(f"{len(unparsed)} unparseable date value(s), e.g. {cell(unparsed[0])}")

    formatted = [v for v in nonempty if FORMATTED_NUM_RE.match(v)]
    if formatted:
        flags.append(f"{len(formatted)} number(s) stored as formatted text, e.g. {cell(formatted[0])}")
    if kind == "numeric":
        lead_zero = [v for v in plain_nums if re.match(r"^0\d", v)]
        if lead_zero:
            flags.append(f"{len(lead_zero)} value(s) with leading zeros, e.g. {cell(lead_zero[0])}")
        nonnum = [v for v in nonempty if v not in set(plain_nums)]
        if nonnum:
            flags.append(f"{len(nonnum)} non-numeric value(s) in numeric column, e.g. {cell(nonnum[0])}")
    elif kind == "string" and nonempty:
        numlike = len(plain_nums) + len(formatted)
        if 0.3 <= numlike / len(nonempty) < 0.8:
            flags.append(f"{numlike}/{len(nonempty)} values look numeric in a text column")

    if kind == "string" and distinct > 1:
        groups = {}
        for v in counter:
            groups.setdefault(normalize_entity(v), []).append(v)
        collisions = [g for g in groups.values() if len(g) > 1]
        if collisions:
            ex = "; ".join(" ~ ".join(cell(x, 30) for x in g) for g in collisions[:3])
            flags.append(
                f"{len(collisions)} group(s) of near-duplicate values differing only by case, "
                f"punctuation, or legal suffix: {ex}"
            )

    dupes = [v for v, c in counter.items() if c > 1]
    return {
        "column": name,
        "kind": kind,
        "rows": total,
        "nulls": nulls,
        "distinct": distinct,
        "top": counter.most_common(5),
        "min": mn,
        "max": mx,
        "shortest": shortest,
        "longest": longest,
        "flags": flags,
        "has_dupes": bool(dupes),
    }


def main():
    files = sorted(f for f in os.listdir(DATA_DIR) if f.lower().endswith(".csv"))
    out = []
    out.append("# CSV inventory profile — `dataset/`\n")
    out.append(
        "Generated by `verify/profile_csvs.py` (stdlib `csv`, so quoted fields containing commas "
        "parse correctly). Null/empty counts treat whitespace-only cells as empty; all other stats "
        "use stripped values. Longest/shortest are over distinct values.\n"
    )

    summaries = []
    all_flags = []
    per_file = []

    for fname in files:
        path = os.path.join(DATA_DIR, fname)
        with open(path, newline="", encoding="utf-8") as fh:
            sample = fh.read(4096)
            fh.seek(0)
            reader = csv.reader(fh)
            try:
                header = next(reader)
            except StopIteration:
                header = []
            rows = list(reader)
        bom = sample.startswith("\ufeff")
        with open(path, "rb") as bfh:
            raw = bfh.read()
        crlf = raw.count(b"\r\n")
        lf_only = raw.count(b"\n") - crlf
        line_endings = "CRLF" if crlf and not lf_only else ("LF" if lf_only and not crlf else "mixed CRLF/LF")
        cols = {h: [] for h in header}
        order = list(header)
        ragged_short = ragged_long = 0
        blank_rows = 0
        for r in rows:
            if not r or all(c.strip() == "" for c in r):
                blank_rows += 1
            if len(r) < len(header):
                ragged_short += 1
            elif len(r) > len(header):
                ragged_long += 1
            for i, h in enumerate(order):
                cols[h].append(r[i] if i < len(r) else "")
        profs = [profile_column(h, cols[h]) for h in order]
        per_file.append((fname, len(rows), order, profs))
        summaries.append((fname, len(rows), len(order), sum(len(p["flags"]) for p in profs)))

        file_notes = []
        if bom:
            file_notes.append("file starts with a UTF-8 BOM")
        file_notes.append(f"line endings: {line_endings}")
        if ragged_short:
            file_notes.append(f"{ragged_short} row(s) with fewer fields than the header")
        if ragged_long:
            file_notes.append(f"{ragged_long} row(s) with more fields than the header")
        if blank_rows:
            file_notes.append(f"{blank_rows} completely blank row(s)")
        dup_rows = sum(c - 1 for c in Counter(tuple(r) for r in rows).values() if c > 1)
        if dup_rows:
            file_notes.append(f"{dup_rows} fully duplicated data row(s)")
        dup_headers = [h for h, c in Counter(order).items() if c > 1]
        if dup_headers:
            file_notes.append(f"duplicate header names: {', '.join(dup_headers)}")
        hdr_ws = [h for h in order if h != h.strip()]
        if hdr_ws:
            file_notes.append(f"header names with surrounding whitespace: {hdr_ws}")
        per_file[-1] = per_file[-1] + (file_notes,)
        for p in profs:
            for f in p["flags"]:
                all_flags.append((fname, p["column"], f))

    others = sorted(
        f for f in os.listdir(DATA_DIR) if not f.lower().endswith(".csv") and os.path.isfile(os.path.join(DATA_DIR, f))
    )
    if others:
        out.append(
            "Non-CSV files present in the folder and not profiled here: "
            + ", ".join(f"`{f}`" for f in others)
            + ".\n"
        )

    out.append("## Files\n")
    out.append("| File | Data rows | Columns | Flags raised |")
    out.append("| --- | ---: | ---: | ---: |")
    for fname, nrows, ncols, nflags in summaries:
        out.append(f"| `{fname}` | {nrows} | {ncols} | {nflags} |")
    out.append("")

    for fname, nrows, order, profs, file_notes in per_file:
        out.append(f"## `{fname}`\n")
        out.append(f"{nrows} data rows, {len(order)} columns.\n")
        if file_notes:
            out.append("File-level notes:\n")
            for n in file_notes:
                out.append(f"- {n}")
            out.append("")

        out.append("### Column summary\n")
        out.append("| Column | Inferred type | Rows | Null/empty | Distinct | Min | Max |")
        out.append("| --- | --- | ---: | ---: | ---: | --- | --- |")
        for p in profs:
            mn = f"`{md_escape(p['min'])}`" if p["min"] != "" else "—"
            mx = f"`{md_escape(p['max'])}`" if p["max"] != "" else "—"
            out.append(
                f"| `{md_escape(p['column'])}` | {p['kind']} | {p['rows']} | {p['nulls']} | {p['distinct']} | {mn} | {mx} |"
            )
        out.append("")

        out.append("### Most common values\n")
        out.append("| Column | 1st | 2nd | 3rd | 4th | 5th |")
        out.append("| --- | --- | --- | --- | --- | --- |")
        for p in profs:
            cells = []
            for v, c in p["top"]:
                cells.append(f"{cell(v, 40)} ×{c}")
            cells += ["—"] * (5 - len(cells))
            out.append(f"| `{md_escape(p['column'])}` | " + " | ".join(cells) + " |")
        out.append("")

        out.append("### Longest and shortest values (distinct)\n")
        out.append("| Column | 3 longest | 3 shortest |")
        out.append("| --- | --- | --- |")
        for p in profs:
            lg = "<br>".join(f"{cell(v, 70)} ({len(v)})" for v in p["longest"]) or "—"
            sh = "<br>".join(f"{cell(v, 70)} ({len(v)})" for v in p["shortest"]) or "—"
            out.append(f"| `{md_escape(p['column'])}` | {lg} | {sh} |")
        out.append("")

        flagged = [p for p in profs if p["flags"]]
        out.append("### Flags\n")
        if not flagged:
            out.append("None.\n")
        else:
            out.append("| Column | Issue |")
            out.append("| --- | --- |")
            for p in flagged:
                for f in p["flags"]:
                    out.append(f"| `{md_escape(p['column'])}` | {f} |")
            out.append("")

    cats = Counter()
    for _, _, f in all_flags:
        for key, label in (
            ("non-ASCII", "non-ASCII characters"),
            ("outside 2020-2027", "dates outside 2020-2027"),
            ("mixed case", "mixed case conventions"),
            ("stray punctuation", "stray leading/trailing punctuation"),
            ("near-duplicate", "near-duplicate values (case/punctuation/legal suffix)"),
            ("whitespace", "leading/trailing whitespace"),
            ("truncation", "possible truncation"),
            ("numeric", "numeric formatting"),
        ):
            if key in f:
                cats[label] += 1
                break
        else:
            cats["other"] += 1

    out.append("## Issue categories\n")
    out.append("| Category | Columns affected |")
    out.append("| --- | ---: |")
    for label, n in cats.most_common():
        out.append(f"| {label} | {n} |")
    out.append("")

    out.append("## All flags, by file\n")
    out.append("| File | Column | Issue |")
    out.append("| --- | --- | --- |")
    for fname, col, f in all_flags:
        out.append(f"| `{fname}` | `{md_escape(col)}` | {f} |")
    out.append("")

    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print(f"wrote {OUT_PATH}: {len(files)} files, {len(all_flags)} flags")


if __name__ == "__main__":
    sys.exit(main())
