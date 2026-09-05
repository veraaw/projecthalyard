# Dataset integrity — summary

One-page digest of `scoping/integrity_checks.md` (full detail, examples and regeneration via `scoping/integrity_checks.py`). Reference date for "future" checks: 2026-09-03. Nothing in `dataset/` was modified.

## Headline

Referential integrity is largely intact; the three real problems are **requests that claim progress but have no outcome record**, **requesters recorded as connectors**, and **LinkedIn connection dates in the future**.

| Check | Result |
| --- | --- |
| `intro_outcomes.request_id` with no matching request | 0 / 85 — clean |
| `intro_requests` with no outcome row | **115 / 200** — see below |
| Duplicate `request_id` in outcomes | 0 |
| `connector_asked` not in `connector_roster.csv` | **5 / 85** |
| `crm_accounts.owner` vs `intro_requests.requested_by` | Same 8 people; nobody appears in only one |
| `response_date` < `asked_date` | 0 |
| `intro_date` < `response_date` | 0 |
| Any outcome / request / CRM date after 2026-09-03 | 0 |
| `connections_*.connected_on` in the future | **10 / 5,075** |
| `responded = N` with a `response_date` | 0 |
| `intro_sent = N` with an `intro_date` | 0 |

## Findings that need attention

### 1. 115 requests have no `intro_outcomes` row

Expected for `Open` (55) and `Closed - no path` (18), but **14 `Intro sent`, 13 `Routed` and 15 `Stalled`** requests also have no outcome row. Either the status was set without an ask being logged, or outcomes are only recorded for a subset of connectors. Any funnel built from `intro_outcomes` alone under-counts intros sent.

### 2. Five outcomes name a non-connector as `connector_asked`

`Yusuf Petrossian` (R1066), `Hana Nakashima` (R1108), `Curtis Hartigan` (R1122), `Bertrand Vandermolen` (R1169), `Imani Mkhize` (R1176). All five are CRM account owners / intro requesters — the requester appears to have been entered in the connector column. These rows should be excluded from (or corrected before) any per-connector metric such as response rate or capacity usage.

### 3. Ten `connected_on` dates are in the future

Spread across all six connection files (Aldridge 3, Beckett 2, Duvall 2, Raghunathan 1, Trask 1, Whitfield 1), ranging from 2026-09-15 to 2027-05-09. Likely export/typo artefacts; harmless for pathfinding but they will distort any "relationship age" weighting.

## What is clean

- Every outcome joins back to a request; no duplicate outcomes per request.
- Owners and requesters are the identical population (`Bertrand Vandermolen`, `Curtis Hartigan`, `Hana Nakashima`, `Imani Mkhize`, `Nadia Okonkwo`, `Rafael Salcedo`, `Sloane Fairweather`, `Yusuf Petrossian`).
- Dates in `intro_outcomes` are internally ordered (asked ≤ response ≤ intro) and none are in the future; same for `intro_requests.request_date` and `crm_accounts.last_touch_date`.
- Y/N flags are consistent with their dates in both directions, and the funnel flags are monotonic (`N/N/N/N` 30, `Y/N/N/N` 23, `Y/Y/N/N` 18, `Y/Y/Y/N` 7, `Y/Y/Y/Y` 7).
