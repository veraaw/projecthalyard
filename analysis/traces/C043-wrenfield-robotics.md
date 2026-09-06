# Wrenfield Robotics  (C043)

- stage: Discovery | industry: Technology | owner: Rafael Salcedo | deal value: $1,400,000 | largest request: $1,200,000
- CRM accounts: A1036 (wrenfield.ai)
- also goes by: WRENFIELDROBOTICS
- 3 requests from 3 people wanting 3 different titles: Chief Technology Officer | Head of Developer Productivity | SVP Digital

## 2. Where the files disagree

- R1156: filed "Routed" but intro_outcomes.csv says Priya Raghunathan sent the intro on 2025-10-18

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.130 | 0.285 | Priya Raghunathan (Investor) | direct | Saoirse Prendergast — Head of Platform Engineering | connections_raghunathan.csv: Saoirse Prendergast, Head of Platform Engineering at Wrenfield Robotics, connected 2014-01-26 |
| 0.085 | 0.187 | Priya Raghunathan (Investor) | alumni | Saoirse Prendergast — ex-Wrenfield Robotics (2012-2015), now Head of Platform Engineering at Wrenfield Robotics | investor_network.csv: Saoirse Prendergast prior_employer=Wrenfield Robotics (2012-2015); connections_raghunathan.csv: connection of Priya Raghunathan since 2014-01-26 |

strongest path, not where it went: Priya Raghunathan, direct 0.285, at capacity 3/3; R1018 unrouted (capacity exhausted this cycle), R1195 unrouted (capacity exhausted this cycle)

## 4. Chronology (14 events, 3 requests, as of 2026-09-06)

```
   2025-10-01  intro_requests.csv   Hana Nakashima       R1156 raised by Hana Nakashima (AE, Healthcare): wants Head of Developer Productivity, $1,200,000, High urgency, filed "Routed"
   2025-10-01  slack_threads.jsonl  Hana Nakashima       R1156 slack: "long shot — Wrenfield Robotics. Astrid Vandermolen-Petrossian (Head of Developer Productivity). Anyone?"
   2025-10-01  intro_outcomes.csv   Priya Raghunathan    R1156 asked
++ 2025-10-09  intro_outcomes.csv   Priya Raghunathan    R1156 replied (8 days after the ask)
++ 2025-10-18  intro_outcomes.csv   Priya Raghunathan    R1156 intro sent

   2026-04-27  intro_requests.csv   Nadia Okonkwo        R1195 raised by Nadia Okonkwo (AE, Industrials): wants SVP Digital, $1,200,000, Low urgency, filed "Open"
   2026-04-27  slack_threads.jsonl  Nadia Okonkwo        R1195 slack: "trying to reach SVP Digital at Wrenfield Robotics. I know we sell into Copperline Water and Harrowgate Health — could either of those relationships get us there?"
   2026-04-27  slack_threads.jsonl  Nadia Okonkwo        R1195 slack: "no idea sorry"
   2026-04-27  slack_threads.jsonl  Hana Nakashima       R1195 slack: "what's the deal size here?"
   2026-04-29  slack_threads.jsonl  Hana Nakashima       R1195 slack: "did we not already lose this one?"

   2026-05-31  intro_requests.csv   Yusuf Petrossian     R1018 raised by Yusuf Petrossian (SDR Lead): wants Chief Technology Officer, $1,200,000, High urgency, filed "Open"
   2026-05-31  slack_threads.jsonl  Yusuf Petrossian     R1018 slack: "who do we know at Wrenfield Robotics? Chief Technology Officer would be ideal but I'll take anyone senior"
   2026-06-03  slack_threads.jsonl  Sloane Fairweather   R1018 slack: "is this the same as the one from last month?"

!! 2025-10-15  crm_accounts.csv     Rafael Salcedo       last CRM touch on A1036  [326 days ago, nothing since]
```

## 5. Next steps, by person, cheapest first

| # | who | role | action | why | requests |
|---|---|---|---|---|---|
| 1 | Rafael Salcedo | CRM owner (A1036) | check in on the account | last touch 2025-10-15, 326 days ago | — |
| 2 | Nadia Okonkwo (132 days), Yusuf Petrossian (98 days) | 2 reps still waiting, longest first | tell them it's with Priya Raghunathan | 2 reps raised this and have heard nothing; the oldest has been waiting 132 days | R1195, R1018 |

## 6. Additional Investor and Operator Network

2 people from investor_network.csv, 1 with no warm path; read-only: not scored, not allocated, not on supply_reach.csv

| person | role | fund | board seat | source | warm path |
|---|---|---|---|---|---|
| Saoirse Prendergast | Operator (work history) |  | no | prior_employer | via Raghunathan |
| Matteo Ferreira-Yarrow | Private equity investor | Ironvale Partners | no | portfolio_company | no warm path |
