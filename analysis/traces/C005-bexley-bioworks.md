# Bexley Bioworks  (C005)

- stage: Negotiation | industry: Biotech | owner: Sloane Fairweather | deal value: $1,400,000 | largest request: $750,000
- CRM accounts: A1045 (bexleybio.com)
- also goes by: nothing else
- 1 request from 1 person wanting 1 different title: Chief Data Officer

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.409 | 0.900 | Priya Raghunathan (Investor) | investor (board seat) | CEO / exec team — Redtree Capital board seat | investor_network.csv: Priya Raghunathan (Partner, Redtree Capital), portfolio_company=Bexley Bioworks, board_seat=True |
| 0.273 | 0.600 | Priya Raghunathan (Investor) | direct | Yusuf Wolstenholme — Chief Information Officer | connections_raghunathan.csv: Yusuf Wolstenholme, Chief Information Officer at Bexley Bioworks, connected 2026-07-07 |
| 0.211 | 0.465 | Priya Raghunathan (Investor) | direct | Malik Egerton — Chief Digital Officer | connections_raghunathan.csv: Malik Egerton, Chief Digital Officer at Bexley Bioworks, connected 2021-07-21 |
| 0.096 | 0.600 | Tomás Beckett (Internal) | direct | Yusuf Wolstenholme — Chief Information Officer | connections_beckett.csv: Yusuf Wolstenholme, Chief Information Officer at Bexley Bioworks, connected 2026-11-16 |
| 0.084 | 0.438 | Dana Whitfield (Internal) | direct | Sabine Nakashima — Chief Data Officer | connections_whitfield.csv: Sabine Nakashima, Chief Data Officer at Bexley Bioworks, connected 2020-05-27 |
| 0.066 | 0.411 | Tomás Beckett (Internal) | direct | Malik Egerton — Chief Digital Officer | connections_beckett.csv: Malik Egerton, Chief Digital Officer at Bexley Bioworks, connected 2019-09-28 |
| 0.064 | 0.411 | Marcus Aldridge (Advisor) | direct | Sabine Nakashima — Chief Data Officer | connections_aldridge.csv: Sabine Nakashima, Chief Data Officer at Bexley Bioworks, connected 2019-05-20 |
| 0.000 | 0.379 | Elena Duvall (Advisor) | direct | Kwame Achterberg — Head of Platform Engineering | connections_duvall.csv: Kwame Achterberg, Head of Platform Engineering at Bexley Bioworks, connected 2020-09-15 |

strongest path, not where it went: Priya Raghunathan, investor 0.900, at capacity 3/3; R1048 routed to Tomás Beckett

## 4. Chronology (5 events, 1 request, as of 2026-09-06)

```
   2026-04-14  intro_requests.csv   Bertrand Vandermolen R1048 raised by Bertrand Vandermolen (AE, EMEA): wants Chief Data Officer, $750,000, High urgency, filed "Stalled"
   2026-04-14  slack_threads.jsonl  Bertrand Vandermolen R1048 slack: "any connections into Bexley Bioworks? we're up against a renewal window and I need an intro to Chief Data Officer"
   2026-04-15  slack_threads.jsonl  Yusuf Petrossian     R1048 slack: "I think their procurement is frozen until Q1"
   2026-04-18  slack_threads.jsonl  Hana Nakashima       R1048 slack: "adding Curtis Hartigan who might know"

!! 2026-03-01  crm_accounts.csv     Sloane Fairweather   last CRM touch on A1045  [189 days ago, nothing since]
```

## 5. Next steps, by person, cheapest first

| # | who | role | action | why | requests |
|---|---|---|---|---|---|
| 1 | Tomás Beckett | VP Partnerships (internal connector) | send the ask (batch 2026-09 Tomás Beckett) | allocated in golden_allocation.csv via direct path to Yusuf Wolstenholme, score 0.096 | R1048 |
| 2 | Sloane Fairweather | CRM owner (A1045) | check in on the account | last touch 2026-03-01, 189 days ago | — |
| 3 | Bertrand Vandermolen (145 days) | 1 rep still waiting, longest first | tell them it's with Priya Raghunathan | 1 rep raised this and has heard nothing; the oldest has been waiting 145 days | R1048 |

## 6. Additional Investor and Operator Network

1 person from investor_network.csv, 0 with no warm path; read-only: not scored, not allocated, not on supply_reach.csv

| person | role | fund | board seat | source | warm path |
|---|---|---|---|---|---|
| Priya Raghunathan | Partner, Redtree Capital | Redtree Capital | yes | portfolio_company | on the roster |
