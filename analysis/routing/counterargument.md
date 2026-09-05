# Steelman against the routing-layer thesis

Thesis under attack: *Halyard needs a routing layer, and better communication amongst reps on a single account.*
Constraint: argue from `dataset/` only (no `golden/`, no dashboard KPIs). Every number below was recomputed
from the raw CSV/JSONL. "Reach" = a roster connector has a row for the target company in their
`connections_*.csv`, or an `investor_network.csv` portfolio/prior-employer match, after light name normalisation.

## 1. The 115 unasked requests are mostly correct behaviour

200 requests, 85 with a row in `intro_outcomes.csv`, 115 without. Two independent facts explain almost all of
the 115, and together cover **105 of them**:

| Reason the ask would have been wrong | Unasked requests |
| --- | ---: |
| No connector has any reach to the target company (45) or no company was even named (25) | 70 |
| Company is reachable but already has an asked request (dedupe); 27 of these were filed on or after that ask | 35 |
| Either of the above | **105 / 115** |
| Neither — genuinely unexplained | 10 ($8.3M) |

Of the 10 unexplained (R1001, R1002, R1048, R1054, R1073, R1080, R1111, R1178, R1191, R1198), 3 already carry a
terminal status set by the requester (`Closed - no path`), 1 says `Intro sent` (R1111 — the intro happened without
the roster) and 1 says `Routed` (R1054). That leaves five requests where "nobody asked and somebody could have" is
unambiguous. A routing layer is a heavy fix for five requests.

Supporting points:

- **The unasked set is lower value, not higher.** Median deal value $400k unasked vs $750k asked. Someone is already
  prioritising by value without a router.
- **"No path" is the honest outcome, not a failure.** 18 of the unasked requests were closed by the requester as
  `Closed - no path`; 24 carry `path_found_flag = No path found`. 57% of all requests resolve to "nobody here knows
  anyone there" — a router cannot manufacture reach that does not exist in six connection exports.
- **Re-filing is the requesters' habit, not the system's gap.** 22 unasked requests literally say "again"/"asking
  again" in `raw_ask`; the pattern "asking again" appears in 41 raw asks overall. Those are the same rep re-posting
  the same company, and the correct response to a duplicate is to *not* generate a second ask.
- **Urgency is self-declared and uncorrelated with value.** 27 of the 115 are flagged `Critical`, but median deal
  value is $400k for Critical, High and Low alike (Medium is $750k). Routing on declared urgency would route noise.

## 2. Path-based routing would not have improved outcomes

The dataset already contains a natural experiment: 57 asks went to a connector who had reach to the target in their
own connections file, 28 went to a connector with no such reach.

| Connector had own reach? | Asks | Responded | Intro sent | Meeting booked |
| --- | ---: | ---: | ---: | ---: |
| Yes | 57 | 35 (61%) | 19 (33%) | 7 (12%) |
| No | 28 | 20 (71%) | 13 (46%) | 7 (25%) |

The "wrongly routed" asks did *better* on every funnel step. If matching a connector to a documented path is what a
routing layer optimises, the data says that is not where the leverage is. The 7 opportunities created came from 7
different requests spanning both groups, and every `opportunity_value_usd` equals the original `deal_value_usd` —
outcomes track the deal, not the route.

Capacity is not binding either: `stated_monthly_capacity` is exceeded in only 2 connector-months out of 12 months of
asks (Priya Raghunathan, 4 vs 3, twice). Beckett, Duvall, Aldridge and Raghunathan average 1.2–1.75 asks/month against
stated capacities of 3–8. Nobody is saturated, so there is no queue to route.

## 3. Reps already coordinate — badly worded, but functionally

- 34 Slack replies are "adding X who might know", tagging another rep into the thread. That *is*
  account-level rep-to-rep communication happening today, in the channel, without tooling.
- 35 unasked requests sit on companies that already had an ask. That is the visible footprint of *not* double-asking a
  connector for the same account — the exact behaviour a communication fix is meant to produce.
- The 43 no-reply threads split 18 asked / 25 not asked. Silence in Slack did not block asks; the 18 were routed to
  roster connectors (Aldridge 6, Raghunathan 6) with no thread discussion at all.

## 4. Is `intro_outcomes.csv` a log of asks, or only of asks that got a response?

**It is a log of asks.** The evidence:

- 30 of 85 rows have `responded = N`. All 30 have an `asked_date`, and all 30 have blank `response_date`,
  `intro_date`, `opportunity_value_usd`. A response-only log could not contain them.
- The 30 non-responses are spread across every month from 2025-08 to 2026-07 (2–5 per month), not bunched at the end
  as "pending" rows would be. They are closed non-responses, recorded as such.
- Every row has an `asked_date` 0–6 days after `request_date` (never later), and response lag is 1–12 days. Entries are
  written when the ask is made, not back-filled from a reply.
- One row per `request_id`, always. The log records *the* ask for a request, so a second connector approached on the same
  request can never appear (see the 4 Slack offers that never became rows).

What the log is **not**: a complete record of all outreach. 14 requests carry `status = Intro sent` in
`intro_requests.csv` with no outcomes row at all (R1009, R1016, R1021, R1040, R1043, R1062, R1097, R1103, R1111, R1115,
R1146, R1148, R1164, R1173 — $9.7M), and 4 asked rows have `intro_sent = N` while the request says `Intro sent`. So
intros happen that the roster never made: reps got them done themselves. That cuts *against* the thesis — the system
routes around the roster when the roster is not the path — and it also means "115 unasked" overstates the gap by at
least those 14.

What distinguishes the two populations in the file: nothing structural. `responded = N` rows are not lower value, not
lower urgency (12 High / 9 Medium / 6 Low / 3 Critical), and not concentrated on one connector (every roster member has
both Y and N rows). The only signal is the status the *requester* later set: 17 of 30 non-responses are still `Open`,
versus 18 of 55 responses. The requester keeps a dead ask open — that is a hygiene problem in `intro_requests.csv`, not
a routing problem.

## 5. Where the counterargument is weakest (for the record)

- 45 unasked requests *do* have reach on the roster ($34.7M), even if 35 of them are dedupe cases and only 27 of
  those were filed after the sibling ask (8 were filed *before* it — the later request got the ask, the earlier one
  was left open). If the sibling ask
  went nowhere (26 of 85 asked requests are still `Open` with `intro_sent = N`), "already asked" is a thin excuse.
- 4 Slack offers to help ($3.75M) never became an ask. That is a hand-off failure, and a small router would catch it.
- The reach-vs-outcome table has n=28 in the "no reach" arm; it argues that path matching is not sufficient, not that
  it is useless.
