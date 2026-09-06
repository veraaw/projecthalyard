# Marlowe Freight Systems  (C024)

- stage: Pilot | industry: Logistics | owner: Imani Mkhize | deal value: $600,000 | largest request: $1,200,000
- CRM accounts: A1047 (marlowefreight.com)
- also goes by: nothing else
- 3 requests from 3 people wanting 3 different titles: Chief Digital Officer | Chief Technology Officer | VP Enterprise Architecture

## 2. Where the files disagree

- R1045: filed "Closed - no path" but supply_reach.csv has 1 path into Marlowe Freight Systems
- R1129: filed "Routed" but intro_outcomes.csv says Marcus Aldridge sent the intro on 2026-05-19

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.161 | 0.465 | Marcus Aldridge (Advisor) | direct | Marcus Merriweather — Chief Data Officer | connections_aldridge.csv: Marcus Merriweather, Chief Data Officer at Marlowe Freight Systems, connected 2021-01-07 |

strongest path, not where it went: Marcus Aldridge, direct 0.465, at capacity 4/4; R1134 unrouted (already introduced: Marcus Aldridge on 2026-05-19 (R1129, meeting booked))

## 4. Chronology (19 events, 3 requests, as of 2026-09-06)

```
!! 2025-09-06  intro_requests.csv   Yusuf Petrossian     R1045 raised by Yusuf Petrossian (SDR Lead): wants VP Enterprise Architecture, $750,000, High urgency, filed "Closed - no path"  [1 paths in supply_reach.csv]
   2025-09-06  slack_threads.jsonl  Yusuf Petrossian     R1045 slack: "who do we know at Marlowe Freight Systems? VP Enterprise Architecture would be ideal but I'll take anyone senior"
   2025-09-08  intro_outcomes.csv   Marcus Aldridge      R1045 asked
++ 2025-09-13  intro_outcomes.csv   Marcus Aldridge      R1045 replied (5 days after the ask)
++ 2025-09-27  intro_outcomes.csv   Marcus Aldridge      R1045 intro sent

   2026-03-05  intro_requests.csv   Bertrand Vandermolen R1134 raised by Bertrand Vandermolen (AE, EMEA): wants Chief Technology Officer, $1,200,000, High urgency, filed "Open"
   2026-03-05  slack_threads.jsonl  Bertrand Vandermolen R1134 slack: "Harrowgate Health introduced us to Copperline Water, but the account I actually need is Marlowe Freight Systems (Chief Technology Officer)."
   2026-03-06  slack_threads.jsonl  Hana Nakashima       R1134 slack: "bumping this"
   2026-03-06  slack_threads.jsonl  Imani Mkhize         R1134 slack: "wrong channel? this feels like a partner ask"

   2026-05-06  intro_requests.csv   Nadia Okonkwo        R1129 raised by Nadia Okonkwo (AE, Industrials): wants Chief Digital Officer, $1,200,000, Critical urgency, filed "Routed"
   2026-05-06  slack_threads.jsonl  Nadia Okonkwo        R1129 slack: "Sundermere Bank introduced us to Redtree Foods, but the account I actually need is Marlowe Freight Systems (Chief Digital Officer)."
   2026-05-07  intro_outcomes.csv   Marcus Aldridge      R1129 asked
   2026-05-10  slack_threads.jsonl  Hana Nakashima       R1129 slack: "wrong channel? this feels like a partner ask"
   2026-05-10  slack_threads.jsonl  Bertrand Vandermolen R1129 slack: "is this the same as the one from last month?"
++ 2026-05-17  intro_outcomes.csv   Marcus Aldridge      R1129 replied (10 days after the ask)
++ 2026-05-19  intro_outcomes.csv   Marcus Aldridge      R1129 intro sent
++ 2026-05-19  intro_outcomes.csv   Marcus Aldridge      R1129 meeting booked
++ 2026-05-19  intro_outcomes.csv   Marcus Aldridge      R1129 opportunity created, $1,200,000

!! 2026-02-02  crm_accounts.csv     Imani Mkhize         last CRM touch on A1047  [216 days ago, nothing since]
```

## 5. Additional Investor and Operator Network

2 people from investor_network.csv, 0 askable as investor_network paths, 2 with no warm path; a view of section 3 and the roster's exports, nothing here is scored or allocated on its own

| person | role | fund | board seat | source | warm path |
|---|---|---|---|---|---|
| Matteo Falkenrath-Merriweather | Venture capital investor | Cobalt Lane Ventures | no | portfolio_company | no warm path |
| Otto Højgaard-Ferreira | Venture capital investor | Cobalt Lane Ventures | no | portfolio_company | no warm path |
