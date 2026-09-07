"""One state per request, the same on both pages.

Live Data (`dashboard/data_cuts.py`) and Live Priorities (`dashboard/live_priorities.py`)
import `state()` from here rather than each classifying a request its own way, so a
request_id lands under one name on either page and every count is a filter over the
same classified table. Where a request stands, first match wins:

    a row in the ask log (intro_outcomes.csv with completions applied)  -> "asked"
    a current-cycle golden_allocation.csv row naming a connector          -> "allocated, not yet asked"
    a current-cycle golden_allocation.csv row with an exception_reason    -> its text before the first ":"
    no allocation row                                                     -> "status gate: " + status_as_filed

golden_requests.csv's blocked_reason is not an input: it ranks what would unblock a
request (a per-row detail column), not why the system stopped.
"""
from golden import build_golden as bg

ASKED = "asked"
ALLOCATED = "allocated, not yet asked"
STATUS_GATE = "status gate: "  # + status_as_filed: no allocation row, the status kept the request from the allocator
COMPANY_UNRESOLVED = "company unresolved"  # the exception_reason build_golden files when the ask names no resolvable company
GATE_CLOSED, GATE_INTRO_SENT = STATUS_GATE + "Closed - no path", STATUS_GATE + "Intro sent"

# the Accounts donut's three slices over the blocked states -> (label, the states it sums); the
# allocator's own exception prefixes, so the wedges and Unrouted Exceptions share one vocabulary
SLICES = {
    "supply": ("supply", [bg.NO_PATH]),
    "process": ("process", [GATE_CLOSED, GATE_INTRO_SENT, COMPANY_UNRESOLVED, bg.CAPACITY_EXHAUSTED]),
    "closed": ("correctly not asked", [bg.ALREADY_INTRODUCED]),
}


def current_allocation(history):
    """The latest cycle of golden_allocation.csv keyed by request_id: the one
    allocation read both pages classify against."""
    return {a["request_id"].strip(): a for a in bg.latest_cycle(history)}


def state(status_as_filed, outcome, alloc):
    """Where one request stands (see the module docstring), from its ask-log row
    and its current-cycle allocation row, either of which may be None."""
    if outcome is not None:
        return ASKED
    if alloc and alloc["allocated_to"].strip():
        return ALLOCATED
    if alloc and alloc["exception_reason"].strip():
        return alloc["exception_reason"].split(":")[0].strip()
    return STATUS_GATE + status_as_filed.strip()


def filed_status(r):
    """status_as_filed on a golden row, `status` on a raw intro_requests.csv row."""
    return r.get("status_as_filed", r.get("status", ""))


def classify(requests, outcome_by_rid, alloc_by_rid):
    """{request_id: state} over every request: the classified table both pages
    filter. `alloc_by_rid` is current_allocation()."""
    return {r["request_id"].strip(): state(filed_status(r), outcome_by_rid.get(r["request_id"].strip()), alloc_by_rid.get(r["request_id"].strip()))
            for r in requests}
