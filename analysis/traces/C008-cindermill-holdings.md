# Cindermill Holdings  (C008)

- stage: Discovery | industry: Mining | owner: Nadia Okonkwo | deal value: $600,000 | largest request: $750,000
- CRM accounts: A1025 (cindermill.com)
- also goes by: Cindermill Mining
- 4 requests from 3 people wanting 4 different titles: Chief Digital Officer | Chief Information Officer | VP Data & Analytics | VP Engineering

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.119 | 0.330 | Elena Duvall (Advisor) | direct | Bertrand Glückstein — Chief Data Officer | connections_duvall.csv: Bertrand Glückstein, Chief Data Officer at Cindermill Mining, connected 2015-08-26 |
| 0.067 | 0.187 | Elena Duvall (Advisor) | alumni | Bertrand Glückstein — ex-Cindermill Mining (2011-2016), now Chief Data Officer at Cindermill Mining | investor_network.csv: Bertrand Glückstein prior_employer=Cindermill Mining (2011-2016); connections_duvall.csv: connection of Elena Duvall since 2015-08-26 |
| 0.061 | 0.381 | Tomás Beckett (Internal) | direct | Bo Marchetti — Platform Lead | connections_beckett.csv: Bo Marchetti, Platform Lead at Cindermill Mining, connected 2022-02-02 |
| 0.061 | 0.381 | Tomás Beckett (Internal) | direct | Leandro Brenneman — Director of Software Engineering | connections_beckett.csv: Leandro Brenneman, Director of Software Engineering at Cindermill Mining, connected 2021-08-25 |
| 0.050 | 0.319 | Marcus Aldridge (Advisor) | direct | Bo Marchetti — Platform Lead | connections_aldridge.csv: Bo Marchetti, Platform Lead at Cindermill Mining, connected 2019-08-23 |
| 0.049 | 0.426 | Owen Trask (Investor) | direct | Leandro Brenneman — Director of Software Engineering | connections_trask.csv: Leandro Brenneman, Director of Software Engineering at Cindermill Mining, connected 2023-10-26 |
| 0.038 | 0.330 | Owen Trask (Investor) | direct | Bertrand Glückstein — Chief Data Officer | connections_trask.csv: Bertrand Glückstein, Chief Data Officer at Cindermill Mining, connected 2015-05-17 |
| 0.021 | 0.187 | Owen Trask (Investor) | alumni | Bertrand Glückstein — ex-Cindermill Mining (2011-2016), now Chief Data Officer at Cindermill Mining | investor_network.csv: Bertrand Glückstein prior_employer=Cindermill Mining (2011-2016); connections_trask.csv: connection of Owen Trask since 2015-05-17 |

strongest path, not where it went: Owen Trask, direct 0.426, at capacity 2/2; R1059 routed to Elena Duvall, R1144 routed to Elena Duvall, R1184 routed to Elena Duvall

## 4. Chronology (17 events, 4 requests, as of 2026-09-06)

```
   2025-08-17  intro_requests.csv   Curtis Hartigan      R1144 raised by Curtis Hartigan (AE, Financial Services): wants VP Engineering, $400,000, Critical urgency, filed "Open"
   2025-08-17  slack_threads.jsonl  Curtis Hartigan      R1144 slack: "long shot — Cindermill Mining. Amara Højgaard-Egerton (VP Engineering). Anyone?"
   2025-08-17  slack_threads.jsonl  Hana Nakashima       R1144 slack: "wrong channel? this feels like a partner ask"
   2025-08-19  slack_threads.jsonl  Nadia Okonkwo        R1144 slack: "I think their procurement is frozen until Q1"

   2025-09-06  intro_requests.csv   Bertrand Vandermolen R1059 raised by Bertrand Vandermolen (AE, EMEA): wants VP Data & Analytics, $250,000, High urgency, filed "Open"
   2025-09-06  slack_threads.jsonl  Bertrand Vandermolen R1059 slack: "Cindermill Mining is the target. Our champion at Quillon Pharma used to work with their team, and I think Pemberton Retail is a supplier of theirs. Any path?"
   2025-09-07  slack_threads.jsonl  Hana Nakashima       R1059 slack: "is this the same as the one from last month?"

   2026-06-23  intro_requests.csv   Yusuf Petrossian     R1015 raised by Yusuf Petrossian (SDR Lead): wants Chief Information Officer, $80,000, High urgency, filed "Stalled"
   2026-06-23  slack_threads.jsonl  Yusuf Petrossian     R1015 slack: "long shot — Cindermill Mining. Niall Zettergren-Isenberg (Chief Information Officer). Anyone?"
   2026-06-26  slack_threads.jsonl  Nadia Okonkwo        R1015 slack: "bumping this"
   2026-06-26  intro_outcomes.csv   Owen Trask           R1015 asked
   2026-06-27  slack_threads.jsonl  Yusuf Petrossian     R1015 slack: "I think their procurement is frozen until Q1"
   2026-06-27  slack_threads.jsonl  Imani Mkhize         R1015 slack: "did we not already lose this one?"
<- 2026-09-06  intro_outcomes.csv   Owen Trask           R1015 never replied (asked 2026-06-26, 72 days ago)

   2026-07-26  intro_requests.csv   Bertrand Vandermolen R1184 raised by Bertrand Vandermolen (AE, EMEA): wants Chief Digital Officer, $750,000, Critical urgency, filed "Open"
   2026-07-26  slack_threads.jsonl  Bertrand Vandermolen R1184 slack: "long shot — Cindermill Mining. Bo Zettergren-Wexford (Chief Digital Officer). Anyone?"

!! 2025-07-10  crm_accounts.csv     Nadia Okonkwo        last CRM touch on A1025  [423 days ago, nothing since]
```

## 5. Next steps, by person, cheapest first

| # | who | role | action | why | requests |
|---|---|---|---|---|---|
| 1 | Elena Duvall | Advisor (former COO, industrial manufacturing) (advisor connector) | send the ask (batch 2026-09 Elena Duvall) | allocated in golden_allocation.csv via direct path to Bertrand Glückstein, score 0.119; allocated in golden_allocation.csv via direct path to Bertrand Glückstein, score 0.119; allocated in golden_allocation.csv via direct path to Bertrand Glückstein, score 0.119 | R1059, R1144, R1184 |
| 2 | Nadia Okonkwo | CRM owner (A1025) | check in on the account | last touch 2025-07-10, 423 days ago | — |
| 3 | Curtis Hartigan (385 days), Bertrand Vandermolen (365 days), Yusuf Petrossian (75 days) | 3 reps still waiting, longest first | tell them it's with Elena Duvall / Owen Trask | 3 reps raised this and have heard nothing; the oldest has been waiting 385 days | R1144, R1059, R1184, R1015 |
