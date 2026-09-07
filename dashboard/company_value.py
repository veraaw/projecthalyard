"""One $ per company, the same on both pages.

Live Data (`dashboard/data_cuts.py`) and Live Priorities (`dashboard/live_priorities.py`)
price a company here rather than each summing its own column, so a $ on either page
means the same thing: a company counts once however many requests name it, at

    its CRM ARR potential (golden_companies.csv value_usd, the max across its
    accounts) when it is linked to a CRM account that carries one          -> "crm"
    else the value_usd on its most recent golden request that carries one  -> "deal"
    else 0                                                                 -> "none"

A request that resolved to no company cannot be tied to a CRM account or to its
sibling requests, so it stands on its own at its own deal value.
"""


def usd(v) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def company_value(company: dict, requests: list[dict]) -> tuple[int, str]:
    """(usd, source) for one company: `company` its golden_companies.csv row (or {}),
    `requests` its golden_requests.csv rows."""
    if company.get("crm_account_ids") and usd(company.get("value_usd")):
        return usd(company["value_usd"]), "crm"
    for r in sorted(requests, key=lambda r: (r["request_date"], r["request_id"]), reverse=True):
        if usd(r["value_usd"]):
            return usd(r["value_usd"]), "deal"
    return 0, "none"


def total(rows: list[dict], companies: dict[str, dict], by_company: dict[str, list[dict]]) -> int:
    """Sum of one $ per distinct company_id across `rows` (golden request rows, or any
    row carrying company_id and value_usd), plus value_usd for each row with no company.
    `companies` is golden_companies.csv by company_id, `by_company` golden requests by company_id."""
    seen: set[str] = set()
    out = 0
    for r in rows:
        cid = r.get("company_id", "")
        if not cid:
            out += usd(r.get("value_usd", ""))
        elif cid not in seen:
            seen.add(cid)
            out += company_value(companies.get(cid, {}), by_company.get(cid, []))[0]
    return out
