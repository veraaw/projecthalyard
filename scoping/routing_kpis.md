# Routing KPIs

Source: `dataset/` — 200 Slack threads, 200 intro requests, 85 outcome rows. Regenerate with `python3 scoping/routing_kpis.py`; this file is append-only as KPIs are added.

## Median lag: Slack request -> connector ask

`intro_outcomes.asked_date` is date-only and every thread opens on its request's `request_date`, so the lag is a whole number of calendar days from the Slack request to the ask being logged. Only requests that were asked at all are in scope.

- Asks measured: **85** (of 85 outcome rows, 200 requests)
- **Median: 3 days**
- Mean 3.0 d, p25 2 d, p75 4 d, min 0 d, max 6 d
- Asked the same day: 11 (13%); nothing is asked later than 6 days, so the lag is bounded rather than long-tailed

| Lag (days) | Asks |
| ---: | ---: |
| 0 | 11 |
| 1 | 10 |
| 2 | 13 |
| 3 | 19 |
| 4 | 11 |
| 5 | 10 |
| 6 | 11 |

| Cohort | Asks | Median lag | Mean lag |
| --- | ---: | ---: | ---: |
| Thread contained an offer of help | 11 | 3 d | 3.2 d |
| No offer on the thread | 74 | 3 d | 2.9 d |

An offer on the thread does not speed the ask up, which is the first sign that the ask is not actually triggered by the thread.

## Threads containing a concrete offer of help

A concrete offer is a reply matching `happy to intro`, `leave it with me`, `I'll take this one`, `I met their <title>`, or `happy to reach out` — an offer to act, as opposed to `adding X who might know` (a redirect) or `no idea sorry`.

- Threads with at least one concrete offer: **15 / 200 (7.5%)**
- Offer replies: 15 of 323 replies (4.6%)
- Threads with a reply but no concrete offer: 142
- Threads with no reply at all: 43

| request_id | Offered by | deal_value_usd | request status | Ask logged? |
| --- | --- | ---: | --- | --- |
| R1003 | Dana Whitfield | 400000 | Stalled | yes |
| R1034 | Nadia Okonkwo | 400000 | Open | no |
| R1066 | Yusuf Petrossian | 750000 | Open | yes |
| R1108 | Hana Nakashima | 250000 | Stalled | yes |
| R1109 | Owen Trask | 150000 | Closed - no path | no |
| R1115 | Priya Raghunathan | 2000000 | Intro sent | no |
| R1122 | Curtis Hartigan | 1200000 | Intro sent | yes |
| R1124 | Priya Raghunathan | 1200000 | Open | yes |
| R1130 | Tomás Beckett | 80000 | Stalled | yes |
| R1136 | Elena Duvall | 1200000 | Open | no |
| R1163 | Elena Duvall | 400000 | Open | yes |
| R1167 | Priya Raghunathan | 250000 | Stalled | yes |
| R1169 | Bertrand Vandermolen | 150000 | Stalled | yes |
| R1176 | Imani Mkhize | 400000 | Stalled | yes |
| R1187 | Priya Raghunathan | 400000 | Open | yes |

## Requests with an outcome row, and where the ask came from

- Requests with at least one outcome row: **85 / 200 (42.5%)**
- Of those, the connector asked had offered on the thread: **11 (12.9%)**
- Of those, the connector asked did **not** come from a Slack offer: **74 (87.1%)**

Breakdown of the 74 asks with no originating offer:

| Thread state | Requests |
| --- | ---: |
| Thread got no reply at all | 18 |
| Thread had replies, none a concrete offer | 56 |

So routing is mostly *not* driven by the channel: the ask is logged against a connector who never volunteered in the thread.

| Cohort | Requests | Responded | Intro sent | Meeting booked |
| --- | ---: | ---: | ---: | ---: |
| Ask came from a Slack offer | 11 | 9 | 5 | 4 |
| Ask did not come from an offer | 74 | 46 | 27 | 10 |

Asks that did come from an offer convert better at every stage — meetings booked 36% vs 14% — on a small base (11 requests).
