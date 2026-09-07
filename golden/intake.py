"""Accepted uploads: more live data, layered over dataset/ without touching it.

    python3 golden/intake.py                                # rebuild golden/current/ from dataset/ + intake/
    python3 golden/intake.py --preview FILE [--target NAME] # what accepting FILE would change; writes nothing
    python3 golden/intake.py --add FILE [--target NAME] [--by WHO] [--note TEXT]
                                                            # accept FILE by hand (what the tab's Accept does)
    python3 golden/intake.py --revert [--by WHO]            # back to the September export: no upload applied
    python3 golden/intake.py --pull supabase                # pull the intake_uploads table into intake/

dataset/ is the raw September export, read-only, never written. Everything that
arrives later - a fresh CSV of any of its files, a Slack export of threads -
goes through the Live Priorities tab ("Intake: Add More Live Data"), which shows
what accepting the file would change (new rows, new columns, values it would
override) and, on Accept, posts the file to the Supabase `intake_uploads` table.
The rebuild pulls that table here:

  intake/uploads.csv          the ledger: one row per accepted upload, in the order accepted
  intake/files/<upload_id>.*  each upload as received, byte for byte
  intake/rejected.csv         uploads the build could not apply (bad target, unreadable file, a row with no key)

and materialize() writes golden/current/: every file of dataset/ with the
accepted uploads for it applied in ledger order, plus any new file an upload
created (a new connections_<surname>.csv). golden/current/ is what every reader
- the build, the analyses, the dashboards - reads; a file no upload touches is
a byte-for-byte copy of the export.

How an upload is applied, per file kind (SCHEMAS):

  CSV   rows are matched on the file's key (request_id, account_id, name, ...).
        A key not on file is a new row, appended in upload order. A key on file
        is an update: every non-empty cell in the upload that differs from the
        current value overrides it (the preview lists each one); an empty cell
        leaves the current value. Columns the file does not have yet are added,
        after the existing ones, blank on old rows. A row with no key is an
        error and the upload is rejected whole.
  JSONL Slack threads ({request_id, channel, messages:[{ts,user,text}]}, one per
        line, or a JSON array / {"threads": [...]} of the same). A request_id
        not on file is a new thread. One on file is extended: messages not
        already in it (same ts, user and text) are appended; any other
        non-empty field that differs overrides (listed). A thread whose
        request_id is not in intro_requests.csv becomes a request when the
        build runs, exactly as --threads does.

upload_id is <target stem>-<fnv1a-64 of the content>, computed the same way by
the browser (live_priorities.js uploadId) and here, so the same file accepted
twice lands once: the ledger, the table's primary key and --add all skip it.

Revert (the tab's "Revert to Sep Raw Data State", or --revert) is a ledger row
of its own (target `revert`, no file): nothing is deleted, but only the uploads
accepted after the last revert are applied, so golden/current/ is dataset/
again until the next Accept, and build_golden.py drops the requests those
uploads were the only source of from golden_requests.csv (reverted_request_ids;
the one exception to that file being append-only). Uploads after a revert get a -g<n> suffix on
their upload_id (n = reverts so far), so a file that was accepted, reverted
and accepted again is a new row, not a repeat.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "dataset"
INTAKE = ROOT / "intake"
LEDGER = INTAKE / "uploads.csv"
FILES = INTAKE / "files"
REJECTED = INTAKE / "rejected.csv"
CURRENT = ROOT / "golden" / "current"

LEDGER_COLUMNS = ["upload_id", "received_at", "received_by", "target", "filename",
                  "rows", "new_rows", "changed_rows", "new_columns", "note"]
REJECTED_COLUMNS = [*LEDGER_COLUMNS, "problem"]
REVERT = "revert"  # the ledger row's target when it is a revert, not an upload
SUPABASE_TABLE = "intake_uploads"
SUPABASE_PAGE = 200
ENV_FILE = ROOT / ".env"
COMMAND = "python3 golden/intake.py --add {file} --target {target} --by \"{who}\" && python3 golden/build_golden.py && python3 build.py"
REVERT_COMMAND = "python3 golden/intake.py --revert --by \"{who}\" && python3 golden/build_golden.py && python3 build.py"

# What each file is keyed on. `family` files are a pattern: connections_<surname>.csv
# may be a new file (a connector joining the roster) as well as a refresh of one on file.
SCHEMAS: dict[str, dict] = {
    "intro_requests.csv": {"keys": ["request_id"]},
    "intro_outcomes.csv": {"keys": ["request_id"]},
    "crm_accounts.csv": {"keys": ["account_id"]},
    "connector_roster.csv": {"keys": ["name"]},
    "investor_network.csv": {"keys": ["person", "portfolio_company", "prior_employer"]},
    "connections_*.csv": {"keys": ["name", "company"], "family": True},
    "slack_threads.jsonl": {"keys": ["request_id"], "format": "jsonl"},
}
THREAD_FIELDS = ("request_id", "messages")
MESSAGE_FIELDS = ("ts", "user", "text")


# ---------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------
def fnv1a(text: str) -> str:
    """FNV-1a, 64-bit, over the UTF-8 bytes, as 16 hex digits. Small enough to
    write identically in the browser (no BigInt tricks beyond a multiply), and
    the only thing the two sides must agree on for an upload to be one upload."""
    h = 0xCBF29CE484222325
    for b in text.encode("utf-8"):
        h = ((h ^ b) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def upload_id(target: str, content: str, generation: int = 0) -> str:
    """<stem>-<hash>, plus -g<generation> once a revert has happened (generation = reverts so far)."""
    return f"{Path(target).stem}-{fnv1a(content.lstrip(chr(0xFEFF)))}" + (f"-g{generation}" if generation else "")


def revert_id(at: str) -> str:
    return f"{REVERT}-{fnv1a(at)}"


def schema_of(target: str) -> dict | None:
    """The SCHEMAS entry a target file name falls under, or None."""
    if target in SCHEMAS:
        return SCHEMAS[target]
    for pattern, s in SCHEMAS.items():
        if s.get("family") and re.fullmatch(pattern.replace("*", r"[a-z0-9_\-]+"), target):
            return s
    return None


def format_of(target: str) -> str:
    return "jsonl" if target.endswith(".jsonl") else "csv"


def target_problem(target: str) -> str | None:
    """Why a target name cannot be accepted, or None."""
    if not target or target != Path(target).name or target.startswith("."):
        return f"target {target!r} is not a plain file name"
    if schema_of(target) is None:
        return f"target {target!r} is not one of {', '.join(SCHEMAS)}"
    return None


def existing_targets(base: Path = DATASET, path: Path = LEDGER) -> list[str]:
    """Every file an upload can be applied to right now: dataset/ plus new files earlier uploads created."""
    names = {p.name for p in base.iterdir() if p.is_file() and schema_of(p.name)}
    names.update(r["target"] for r in active(ledger(path)))
    return sorted(names)


def columns_on_file(base: Path = DATASET, files: Path = FILES, path: Path = LEDGER) -> dict[str, list[str]]:
    """target -> its columns as it stands ([] for slack_threads.jsonl), for guess_target."""
    out = {}
    for name in existing_targets(base, path):
        if format_of(name) == "jsonl":
            out[name] = []
        else:
            out[name] = current_source(name, base, files, path=path)[0]
    return out


def guess_target(filename: str, columns: list[str] | None, files: dict[str, list[str]]) -> tuple[str, str]:
    """(target, why) for an upload named `filename` with these columns (None for a
    JSON upload), given the files on record and their columns: the file it
    should be applied to, or "" when nothing fits or two fit equally. The
    browser makes the same guess (live_priorities.js guessTarget); either way
    the person accepting can pick another target."""
    name = Path(filename).name.lower()
    if columns is None:
        return "slack_threads.jsonl", "Slack threads"
    have = set(columns)
    fits = lambda t: set(schema_of(t)["keys"]) <= have  # noqa: E731
    if name in files and fits(name):
        return name, "same file name"
    family = next(s for s in SCHEMAS.values() if s.get("family"))
    conn_cols = {c for t, cols in files.items() if schema_of(t) is family for c in cols} | set(family["keys"])
    conn = len(conn_cols & have) if set(family["keys"]) <= have else -1
    scored = sorted(((len(set(cols) & have), t) for t, cols in files.items()
                     if schema_of(t) is not family and format_of(t) == "csv" and fits(t)), reverse=True)
    best = scored[0] if scored else (-1, "")
    if best[0] > conn and (len(scored) == 1 or scored[1][0] < best[0]):
        return best[1], f"{best[0]} of {len(files[best[1]])} columns match"
    if conn >= 0 and conn >= best[0]:
        stem = re.sub(r"[^a-z0-9]+", "_", Path(name).stem).strip("_")
        m = re.fullmatch(r"connections?_(.+)", stem)
        if m:
            new = f"connections_{m.group(1)}.csv"
            return new, ("same file name" if new in files else "connections columns; a new file, named from the upload")
        if stem in ("connections", "connection", ""):
            return "", "connections columns: pick whose (connections_<surname>.csv)"
        return f"connections_{stem}.csv", "connections columns; a new file, named from the upload"
    if best[0] >= 0:
        tied = [t for n, t in scored if n == best[0]]
        return "", f"could be {' or '.join(tied)}: pick one"
    return "", "no file on record has these columns"


# ---------------------------------------------------------------------------
# reading uploads
# ---------------------------------------------------------------------------
def parse_csv(text: str) -> tuple[list[str], list[dict]]:
    """(columns, rows) of a CSV text; a BOM and either line ending are fine.
    Raises ValueError when there is no header or a row has more cells than the header."""
    text = text.lstrip("\ufeff")
    reader = csv.reader(io.StringIO(text, newline=""))
    rows = [r for r in reader]
    while rows and not any(c.strip() for c in rows[-1]):
        rows.pop()
    if not rows or not any(c.strip() for c in rows[0]):
        raise ValueError("no header row")
    columns = [c.strip() for c in rows[0]]
    if len(set(columns)) != len(columns) or "" in columns:
        raise ValueError("header has a blank or repeated column name")
    out = []
    for i, r in enumerate(rows[1:], 2):
        if not any(c.strip() for c in r):
            continue
        if len(r) > len(columns):
            raise ValueError(f"line {i}: {len(r)} cells, header has {len(columns)}")
        out.append({c: (r[j] if j < len(r) else "") for j, c in enumerate(columns)})
    return columns, out


def parse_threads(text: str) -> list[dict]:
    """The threads in a Slack upload: JSONL, a JSON array, or {"threads": [...]}.
    Raises ValueError on anything else, or a thread without request_id / messages
    or a message without ts, user and text."""
    text = text.lstrip("\ufeff").strip()
    if not text:
        raise ValueError("empty file")
    threads: list = []
    whole = None
    try:
        whole = json.loads(text)
    except json.JSONDecodeError:
        pass
    if isinstance(whole, list):
        threads = whole
    elif isinstance(whole, dict) and isinstance(whole.get("threads"), list) and "request_id" not in whole:
        threads = whole["threads"]
    elif isinstance(whole, dict):
        threads = [whole]
    elif whole is None:
        for i, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                threads.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"line {i}: {e.msg}") from None
    if not isinstance(threads, list) or not threads:
        raise ValueError("no threads")
    for i, t in enumerate(threads, 1):
        if not isinstance(t, dict) or not isinstance(t.get("request_id"), str) or not t["request_id"].strip():
            raise ValueError(f"thread {i}: needs a request_id")
        if not isinstance(t.get("messages"), list) or not t["messages"]:
            raise ValueError(f"thread {i} ({t['request_id']}): needs a non-empty messages list")
        for j, m in enumerate(t["messages"], 1):
            if not isinstance(m, dict) or any(not isinstance(m.get(k), str) for k in MESSAGE_FIELDS):
                raise ValueError(f"thread {i} ({t['request_id']}) message {j}: needs ts, user and text")
    return threads


def read_verbatim(path: Path) -> str:
    """The file's text with its line endings as they are (read_text would translate them)."""
    return path.read_bytes().decode("utf-8")


def write_verbatim(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def read_threads(path: Path) -> list[dict]:
    return parse_threads(read_verbatim(path)) if path.exists() else []


def read_csv_file(path: Path) -> tuple[list[str], list[dict]]:
    if not path.exists():
        return [], []
    return parse_csv(read_verbatim(path))


# ---------------------------------------------------------------------------
# merge rules (mirrored in live_priorities.js: mergeCsv / mergeThreads)
# ---------------------------------------------------------------------------
def row_key(r: dict, keys: list[str]) -> tuple[str, ...]:
    return tuple((r.get(k) or "").strip() for k in keys)


def merge_csv(base_cols: list[str], base_rows: list[dict], up_cols: list[str], up_rows: list[dict],
              keys: list[str]) -> tuple[list[str], list[dict], dict]:
    """Apply an upload to a CSV's rows. Returns (columns, rows, summary); the
    summary is what the tab shows before Accept. Raises ValueError when the
    upload lacks a key column or a row has an empty key."""
    missing = [k for k in keys if k not in up_cols]
    if missing:
        raise ValueError(f"no {', '.join(missing)} column")
    columns = [*base_cols, *(c for c in up_cols if c not in base_cols)]
    new_columns = columns[len(base_cols):]
    rows = [{c: r.get(c, "") for c in columns} for r in base_rows]
    index = {row_key(r, keys): r for r in rows}
    new_rows, changes, seen, dup, unchanged = [], [], set(), 0, 0
    fresh_ids: set[int] = set()
    for i, u in enumerate(up_rows, 2):
        k = row_key(u, keys)
        if not all(k):
            raise ValueError(f"line {i}: empty {keys[k.index('')]}")
        if k in seen:
            dup += 1
        seen.add(k)
        r = index.get(k)
        if r is None:
            r = {c: u.get(c, "") for c in columns}
            rows.append(r)
            index[k] = r
            new_rows.append(r)
            fresh_ids.add(id(r))
            continue
        if id(r) in fresh_ids:  # a repeat of a row this upload added: the later row wins, nothing on file is touched
            r.update((c, v) for c in up_cols if (v := u.get(c, "")).strip())
            continue
        touched = False
        for c in up_cols:
            v = u.get(c, "")
            if not v.strip() or r[c] == v:
                continue
            changes.append({"key": " / ".join(k), "column": c, "from": r[c], "to": v})
            r[c] = v
            touched = True
        if not touched:
            unchanged += 1
    summary = {
        "format": "csv", "rows": len(up_rows), "new_rows": len(new_rows), "changed_rows": len({c["key"] for c in changes}),
        "changes": changes, "new_columns": new_columns, "unchanged_rows": unchanged, "duplicate_keys": dup,
        "columns": columns, "keys": keys, "sample": new_rows[:20],
    }
    return columns, rows, summary


def message_sig(m: dict) -> tuple[str, str, str]:
    return tuple(m.get(k, "") for k in MESSAGE_FIELDS)  # type: ignore[return-value]


def merge_threads(base: list[dict], up: list[dict]) -> tuple[list[dict], dict]:
    """Apply a Slack upload to the threads on file. Returns (threads, summary)."""
    threads = [json.loads(json.dumps(t)) for t in base]
    by = {t["request_id"]: t for t in threads}
    base_fields = {k for t in base for k in t}
    new, extended, messages, changes, unchanged, dup, seen, new_fields = [], 0, 0, [], 0, 0, set(), []
    for u in up:
        rid = u["request_id"].strip()
        if rid in seen:
            dup += 1
        seen.add(rid)
        for k in u:
            if k not in base_fields and k not in new_fields:
                new_fields.append(k)
        t = by.get(rid)
        if t is None:
            t = {**u, "request_id": rid}
            threads.append(t)
            by[rid] = t
            new.append(t)
            continue
        have = {message_sig(m) for m in t["messages"]}
        fresh = [m for m in u["messages"] if message_sig(m) not in have]
        t["messages"].extend(fresh)
        touched = bool(fresh)
        if fresh:
            extended += 1
            messages += len(fresh)
        for k, v in u.items():
            if k in THREAD_FIELDS or v in ("", None) or t.get(k) == v:
                continue
            changes.append({"key": rid, "column": k, "from": "" if t.get(k) is None else str(t.get(k)), "to": str(v)})
            t[k] = v
            touched = True
        if not touched:
            unchanged += 1
    summary = {
        "format": "jsonl", "rows": len(up), "new_rows": len(new), "changed_rows": len({c["key"] for c in changes}),
        "changes": changes, "new_columns": new_fields, "unchanged_rows": unchanged, "duplicate_keys": dup,
        "extended_threads": extended, "new_messages": messages, "keys": ["request_id"],
        "sample": [{"request_id": t["request_id"], "channel": str(t.get("channel", "")), "posted": t["messages"][0]["ts"][:10],
                    "user": t["messages"][0]["user"], "text": t["messages"][0]["text"], "replies": len(t["messages"]) - 1}
                   for t in new[:20]],
    }
    return threads, summary


# ---------------------------------------------------------------------------
# the ledger
# ---------------------------------------------------------------------------
def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _write(path: Path, columns: list[str], rows: list[dict]) -> None:
    if DATASET in path.resolve().parents:
        sys.exit(f"refusing to write {path}: dataset/ is read-only input")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\r\n", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in columns})


def ledger(path: Path = LEDGER) -> list[dict]:
    """intake/uploads.csv, in the order accepted (uploads and reverts alike)."""
    return _read(path)


def reverts(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["target"] == REVERT]


def generation(rows: list[dict]) -> int:
    return len(reverts(rows))


def active(rows: list[dict]) -> list[dict]:
    """The uploads that apply: those accepted after the last revert."""
    last = max((i for i, r in enumerate(rows) if r["target"] == REVERT), default=-1)
    return [r for r in rows[last + 1:] if r["target"] != REVERT]


def file_of(row: dict, files: Path = FILES) -> Path:
    return files / f"{row['upload_id']}.{format_of(row['target'])}"


def current_source(target: str, base: Path = DATASET, files: Path = FILES, rows: list[dict] | None = None,
                   path: Path = LEDGER):
    """The file as it stands with every accepted upload applied: (columns, rows)
    for a CSV, a list of threads for slack_threads.jsonl. `rows` is the ledger
    to apply (default: the whole ledger at `path`)."""
    uploads = [r for r in active(ledger(path) if rows is None else rows) if r["target"] == target]
    if format_of(target) == "jsonl":
        threads = read_threads(base / target)
        for r in uploads:
            threads, _ = merge_threads(threads, parse_threads(read_verbatim(file_of(r, files))))
        return threads
    cols, data = read_csv_file(base / target)
    for r in uploads:
        up_cols, up_rows = parse_csv(read_verbatim(file_of(r, files)))
        cols, data, _ = merge_csv(cols, data, up_cols, up_rows, schema_of(target)["keys"])
    return cols, data


def preview(target: str, content: str, base: Path = DATASET, files: Path = FILES, path: Path = LEDGER) -> dict:
    """The summary Accept would show for `content` applied to `target`, on top
    of everything already accepted. Raises ValueError when it cannot be applied.
    Reads only; nothing is written."""
    if problem := target_problem(target):
        raise ValueError(problem)
    rows = ledger(path)
    if format_of(target) == "jsonl":
        _, summary = merge_threads(current_source(target, base, files, rows), parse_threads(content))
    else:
        cols, data = current_source(target, base, files, rows)
        up_cols, up_rows = parse_csv(content)
        _, _, summary = merge_csv(cols, data, up_cols, up_rows, schema_of(target)["keys"])
    summary["target"] = target
    summary["new_file"] = not (base / target).exists() and target not in {r["target"] for r in active(rows)}
    return summary


def ledger_row(uid: str, target: str, summary: dict, by: str, filename: str, note: str, at: str) -> dict:
    return {
        "upload_id": uid, "received_at": at, "received_by": by, "target": target, "filename": filename,
        "rows": summary["rows"], "new_rows": summary["new_rows"], "changed_rows": summary["changed_rows"],
        "new_columns": ";".join(summary["new_columns"]), "note": note,
    }


def add(target: str, content: str, by: str, filename: str = "", note: str = "", at: str = "",
        uid: str = "", base: Path = DATASET, files: Path = FILES, path: Path = LEDGER) -> tuple[dict | None, dict]:
    """Accept an upload: write intake/files/<upload_id>.* and append the ledger
    row. Returns (row, summary); row is None when the upload_id is already on
    file (nothing written). Raises ValueError when it cannot be applied."""
    rows = ledger(path)
    uid = uid or upload_id(target, content, generation(rows))
    summary = preview(target, content, base, files, path)
    if any(r["upload_id"] == uid for r in rows):
        return None, summary
    at = at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = ledger_row(uid, target, summary, by.strip() or "unknown", filename, note, at)
    files.mkdir(parents=True, exist_ok=True)
    write_verbatim(file_of(row, files), content)
    _write(path, LEDGER_COLUMNS, [*rows, row])
    return row, summary


def revert(by: str, note: str = "", at: str = "", uid: str = "", path: Path = LEDGER) -> dict | None:
    """Back to the September export: append a revert row, after which no earlier
    upload applies (they stay in the ledger as history). Returns the row, or
    None when that revert is already on file."""
    rows = ledger(path)
    at = at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    uid = uid or revert_id(at)
    if any(r["upload_id"] == uid for r in rows):
        return None
    row = {"upload_id": uid, "received_at": at, "received_by": by.strip() or "unknown", "target": REVERT, "filename": "",
           "rows": "", "new_rows": "", "changed_rows": "", "new_columns": "", "note": note}
    _write(path, LEDGER_COLUMNS, [*rows, row])
    return row


def reverted_request_ids(base: Path = DATASET, files: Path = FILES, path: Path = LEDGER) -> set[str]:
    """The request_ids that reached golden_requests.csv only through uploads a
    revert set aside: every request_id in a reverted intro_requests.csv or
    slack_threads.jsonl upload that the current files (dataset/ plus the
    uploads still applied) do not have. golden_requests.csv is append-only
    otherwise; the build drops these so a revert really is one."""
    rows = ledger(path)
    live = {r["upload_id"] for r in active(rows)}
    gone = [r for r in rows if r["target"] != REVERT and r["upload_id"] not in live]
    if not gone:
        return set()
    ids: set[str] = set()
    for r in gone:
        text = read_verbatim(file_of(r, files))
        if r["target"] == "slack_threads.jsonl":
            ids.update(t["request_id"].strip() for t in parse_threads(text))
        elif r["target"] == "intro_requests.csv":
            ids.update(u.get("request_id", "").strip() for u in parse_csv(text)[1])
    ids.discard("")
    if ids:
        _, data = current_source("intro_requests.csv", base, files, rows, path)
        ids.difference_update(u.get("request_id", "").strip() for u in data)
        ids.difference_update(t["request_id"].strip() for t in current_source("slack_threads.jsonl", base, files, rows, path))
    return ids


# ---------------------------------------------------------------------------
# golden/current/: dataset/ with the ledger applied
# ---------------------------------------------------------------------------
def line_ending(path: Path) -> str:
    """The CSV's line ending; a file not on record gets CRLF like the export."""
    return "\r\n" if not path.exists() or b"\r\n" in path.read_bytes()[:4096] else "\n"


def csv_text(columns: list[str], rows: list[dict], eol: str = "\r\n") -> str:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=columns, lineterminator=eol, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in columns})
    return out.getvalue()


def threads_text(threads: list[dict]) -> str:
    return "".join(json.dumps(t, ensure_ascii=False) + "\n" for t in threads)


def materialize(base: Path = DATASET, out: Path = CURRENT, files: Path = FILES, path: Path = LEDGER) -> dict[str, int]:
    """Write golden/current/: every file in dataset/ (byte for byte where no
    upload touches it), the accepted uploads applied in ledger order, plus new
    files uploads created. Files in out/ that neither has are removed. Returns
    {file name: uploads applied}. Idempotent: the same inputs write the same bytes."""
    dest = out.resolve()
    for raw in {DATASET.resolve(), base.resolve()}:
        if dest == raw or raw in dest.parents:
            sys.exit(f"refusing to write {out}: dataset/ is read-only input")
    rows = ledger(path)
    uploads: dict[str, int] = {}
    for r in active(rows):
        uploads[r["target"]] = uploads.get(r["target"], 0) + 1
    out.mkdir(parents=True, exist_ok=True)
    keep = set()
    for p in sorted(base.iterdir()):
        if not p.is_file():
            continue
        keep.add(p.name)
        if p.name not in uploads:
            if not (out / p.name).exists() or (out / p.name).read_bytes() != p.read_bytes():
                shutil.copyfile(p, out / p.name)
    for target in sorted(uploads):
        keep.add(target)
        if format_of(target) == "jsonl":
            text = threads_text(current_source(target, base, files, rows))
        else:
            cols, data = current_source(target, base, files, rows)
            text = csv_text(cols, data, line_ending(base / target))
        dest = out / target
        if not dest.exists() or read_verbatim(dest) != text:
            write_verbatim(dest, text)
    for p in out.iterdir():
        if p.is_file() and p.name not in keep:
            p.unlink()
    return uploads


# ---------------------------------------------------------------------------
# the Supabase table
# ---------------------------------------------------------------------------
def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    """The variables in .env (gitignored; KEY=value lines, # comments), also
    placed in os.environ where not already set, so SUPABASE_* work the same
    locally and under Actions secrets."""
    found: dict[str, str] = {}
    if not path.exists():
        return found
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip().removeprefix("export ").strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        found[key] = value
        os.environ.setdefault(key, value)
    return found


def supabase_rest(url: str) -> str:
    """The REST root for a project URL given with or without /rest/v1."""
    base = url.strip().rstrip("/")
    return base if base.endswith("/rest/v1") else base + "/rest/v1"


def fetch_supabase_uploads(url: str, key: str, opener=None) -> list[dict]:
    """Every row of the intake_uploads table, oldest first, with the service key."""
    opener = opener or urllib.request.urlopen
    endpoint = f"{supabase_rest(url)}/{SUPABASE_TABLE}?select=*&order=received_at.asc,upload_id.asc"
    rows, start = [], 0
    while True:
        req = urllib.request.Request(endpoint, headers={
            "apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json",
            "Range-Unit": "items", "Range": f"{start}-{start + SUPABASE_PAGE - 1}",
        })
        with opener(req, timeout=60) as resp:
            page = json.loads(resp.read().decode("utf-8") or "[]")
        rows.extend(page)
        if len(page) < SUPABASE_PAGE:
            return rows
        start += SUPABASE_PAGE


def apply_table_rows(rows: list[dict], base: Path = DATASET, files: Path = FILES, path: Path = LEDGER,
                     rejected_path: Path = REJECTED) -> tuple[int, int, list[dict]]:
    """Bring table rows into the ledger: each one not yet on file is accepted
    (add) or, when it cannot be applied, set aside in intake/rejected.csv with
    the reason (anyone with the publishable key can insert, so a bad row must
    not stop the rebuild). Returns (added, already on file, rejected)."""
    have = {r["upload_id"] for r in ledger(path)}
    rejected_have = {r["upload_id"] for r in _read(rejected_path)}
    added, already, rejected = 0, 0, []
    for raw in rows:
        r = {k: ("" if raw.get(k) is None else str(raw.get(k))) for k in ("upload_id", "received_at", "received_by", "target", "filename", "content", "note")}
        uid = r["upload_id"].strip()
        if not uid:
            continue
        if uid in have or uid in rejected_have:
            already += 1
            continue
        at = r["received_at"][:19].replace(" ", "T").rstrip("Z") + "Z" if r["received_at"] else ""
        try:
            if not re.fullmatch(r"[A-Za-z0-9_\-]+", uid):
                raise ValueError("upload_id is not a plain token")
            if r["target"].strip() == REVERT:
                row = revert(r["received_by"], r["note"], at, uid, path)
            else:
                row, _ = add(r["target"].strip(), r["content"], r["received_by"], r["filename"], r["note"],
                             at=at, uid=uid, base=base, files=files, path=path)
        except ValueError as e:
            rejected.append({"upload_id": uid, "received_at": r["received_at"], "received_by": r["received_by"], "target": r["target"],
                             "filename": r["filename"], "note": r["note"], "problem": str(e)})
            rejected_have.add(uid)
            continue
        have.add(uid)
        added += 1 if row else 0
    if rejected:
        _write(rejected_path, REJECTED_COLUMNS, [*_read(rejected_path), *rejected])
    return added, already, rejected


def pull(source: str | None, fetch=fetch_supabase_uploads) -> None:
    """--pull supabase: the table into intake/. A table that cannot be read ends
    the build, except one that does not exist yet (404: config/supabase_schema.sql
    not run), which is a notice: nothing has been accepted through the browser
    until the table is there, so the build has nothing to miss."""
    if not source:
        return
    if source != "supabase":
        sys.exit(f"--pull {source}: only 'supabase' is known")
    load_env()
    url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not (url and key):
        sys.exit("--pull supabase needs SUPABASE_URL and SUPABASE_SERVICE_KEY (environment or .env)")
    try:
        rows = fetch(url, key)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            sys.exit(f"could not read the Supabase {SUPABASE_TABLE} table: {e}\n"
                     f"the build still works without it: python3 golden/intake.py --add FILE")
        print(f"intake/uploads.csv    no Supabase {SUPABASE_TABLE} table yet (HTTP 404): run the {SUPABASE_TABLE} "
              f"section of config/supabase_schema.sql for Accept to persist; {len(ledger())} on file", file=sys.stderr)
        return
    except Exception as e:  # noqa: BLE001 - any failure to read the table is one message
        sys.exit(f"could not read the Supabase {SUPABASE_TABLE} table: {e}\n"
                 f"the build still works without it: python3 golden/intake.py --add FILE")
    added, already, rejected = apply_table_rows(rows)
    if rejected:
        print(f"supabase {SUPABASE_TABLE}: {len(rejected)} upload(s) set aside -> {REJECTED.name}\n  "
              + "\n  ".join(f"{r['upload_id']}: {r['problem']}" for r in rejected), file=sys.stderr)
    print(f"intake/uploads.csv    {added} upload(s) added from supabase ({len(rows)} in the table, {already} already on file), "
          f"{len(ledger())} on file")


def describe(summary: dict) -> str:
    s = summary
    parts = [f"{s['rows']} rows in the upload", f"{s['new_rows']} new"]
    if s["format"] == "jsonl":
        parts.append(f"{s['extended_threads']} threads extended by {s['new_messages']} messages")
    parts.append(f"{s['changed_rows']} with values overridden ({len(s['changes'])} cells)")
    parts.append(f"{s['unchanged_rows']} unchanged")
    if s["new_columns"]:
        parts.append(f"new columns: {', '.join(s['new_columns'])}")
    if s["duplicate_keys"]:
        parts.append(f"{s['duplicate_keys']} keys repeated within the upload (the last row wins)")
    return "; ".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preview", type=Path, metavar="FILE", help="show what accepting FILE would change; write nothing")
    ap.add_argument("--add", type=Path, metavar="FILE", help="accept FILE into intake/")
    ap.add_argument("--target", help="the dataset/ file it updates (default: guessed from the name and columns)")
    ap.add_argument("--by", default="", help="who accepted it (received_by)")
    ap.add_argument("--note", default="")
    ap.add_argument("--revert", action="store_true", help="back to the September export: no accepted upload applies until the next --add")
    ap.add_argument("--pull", choices=["supabase"], help="pull the Supabase intake_uploads table into intake/ first")
    args = ap.parse_args()
    pull(args.pull)
    if args.revert:
        row = revert(args.by, args.note)
        print("intake/uploads.csv    " + (f"reverted to dataset/ as {row['upload_id']}" if row else "already reverted just now"))
    src = args.preview or args.add
    if src is not None:
        if not src.exists():
            sys.exit(f"{src}: no such file")
        content = read_verbatim(src)
        target = args.target
        if not target:
            try:
                cols = None if src.suffix.lower() in (".json", ".jsonl") else parse_csv(content)[0]
            except ValueError as e:
                sys.exit(f"{src}: {e}")
            target, why = guess_target(src.name, cols, columns_on_file())
            if not target:
                sys.exit(f"{src}: {why}; say which file it updates with --target")
            print(f"target                {target} ({why})")
        try:
            if args.add:
                row, summary = add(target, content, args.by, src.name, args.note)
                print(f"intake/uploads.csv    {'already on file' if row is None else 'added'} {upload_id(target, content, generation(ledger()))}")
            else:
                summary = preview(target, content)
        except ValueError as e:
            sys.exit(f"{src} -> {target}: {e}")
        print(f"{target:<22}{describe(summary)}")
        for c in summary["changes"][:30]:
            print(f"  override {c['key']} · {c['column']}: {c['from']!r} -> {c['to']!r}")
        if len(summary["changes"]) > 30:
            print(f"  ... {len(summary['changes']) - 30} more")
        if args.preview:
            return
    applied = materialize()
    rows = ledger()
    print(f"golden/current/       {len(list(CURRENT.iterdir()))} files from dataset/ + {len(active(rows))} accepted upload(s)"
          + (": " + ", ".join(f"{t} ({n})" for t, n in sorted(applied.items())) if applied else "")
          + (f" ({len(rows) - len(active(rows)) - generation(rows)} reverted)" if generation(rows) else ""))


if __name__ == "__main__":
    main()
