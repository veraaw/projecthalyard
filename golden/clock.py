"""The build clock: one `today` for every step of a build.

    python3 build.py --as-of 2026-09-05                  # every step, one date
    HALYARD_AS_OF=2026-09-05 python3 golden/build_golden.py

build.py puts the date in HALYARD_AS_OF and every step reads it back through
as_of(): the allocator's cycle and decided_at, the traces, the CRM write-back,
the integrity audit's future-date check, the dashboard's rolling windows and
every "as of" the pages print. Unset, it is today's date in UTC, the clock the
scheduled rebuild runs on; a build that crosses midnight still stamps one date.
"""
import os
from datetime import date, datetime, timezone

ENV = "HALYARD_AS_OF"


def as_of() -> date:
    s = os.environ.get(ENV, "").strip()
    if not s:
        return datetime.now(timezone.utc).date()
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise SystemExit(f"{ENV}={s!r} is not a YYYY-MM-DD date") from None
