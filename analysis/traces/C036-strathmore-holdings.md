# Strathmore Holdings  (C036)

- stage: Prospect | industry: Transport | owner: Imani Mkhize | deal value: $250,000 | largest request: $1,200,000
- CRM accounts: A1026 (strathmorerail.com)
- also goes by: Strathmore Rail
- 7 requests from 5 people wanting 5 different titles: Chief Operating Officer | Chief Technology Officer | Head of Platform Engineering | VP Data & Analytics | VP Engineering

## 2. Where the files disagree

- R1093: filed "Closed - no path" but supply_reach.csv has 12 paths into Strathmore Holdings

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.053 | 0.330 | Tomás Beckett (Internal) | direct | Bertrand Lomsadze — Chief Digital Officer | connections_beckett.csv: Bertrand Lomsadze, Chief Digital Officer at Strathmore Rail, connected 2015-09-22 |
| 0.045 | 0.289 | Marcus Aldridge (Advisor) | direct | Tomás Dobrescu — VP Engineering | connections_aldridge.csv: Tomás Dobrescu, VP Engineering at Strathmore Rail, connected 2018-12-16 |
| 0.043 | 0.269 | Tomás Beckett (Internal) | direct | Tomás Dobrescu — VP Engineering | connections_beckett.csv: Tomás Dobrescu, VP Engineering at Strathmore Rail, connected 2017-12-20 |
| 0.042 | 0.271 | Marcus Aldridge (Advisor) | direct | Yusuf Vasquez — Director of Software Engineering | connections_aldridge.csv: Yusuf Vasquez, Director of Software Engineering at Strathmore Rail, connected 2015-08-28 |
| 0.034 | 0.218 | Marcus Aldridge (Advisor) | alumni | Tomás Dobrescu — ex-Strathmore Rail (2013-2018), now VP Engineering at Strathmore Rail | investor_network.csv: Tomás Dobrescu prior_employer=Strathmore Rail (2013-2018); connections_aldridge.csv: connection of Marcus Aldridge since 2018-12-16 |
| 0.032 | 0.202 | Tomás Beckett (Internal) | alumni | Tomás Dobrescu — ex-Strathmore Rail (2013-2018), now VP Engineering at Strathmore Rail | investor_network.csv: Tomás Dobrescu prior_employer=Strathmore Rail (2013-2018); connections_beckett.csv: connection of Tomás Beckett since 2017-12-20 |
| 0.030 | 0.187 | Tomás Beckett (Internal) | alumni | Bertrand Lomsadze — ex-Strathmore Rail (2013-2017), now Chief Digital Officer at Strathmore Rail | investor_network.csv: Bertrand Lomsadze prior_employer=Strathmore Rail (2013-2017); connections_beckett.csv: connection of Tomás Beckett since 2015-09-22 |
| 0.029 | 0.187 | Marcus Aldridge (Advisor) | alumni | Yusuf Vasquez — ex-Strathmore Rail (2014-2017), now Director of Software Engineering at Strathmore Rail | investor_network.csv: Yusuf Vasquez prior_employer=Strathmore Rail (2014-2017); connections_aldridge.csv: connection of Marcus Aldridge since 2015-08-28 |
| 0.000 | 0.357 | Elena Duvall (Advisor) | direct | Bertrand Lomsadze — Chief Digital Officer | connections_duvall.csv: Bertrand Lomsadze, Chief Digital Officer at Strathmore Rail, connected 2017-03-25 |
| 0.000 | 0.271 | Elena Duvall (Advisor) | direct | Yusuf Vasquez — Director of Software Engineering | connections_duvall.csv: Yusuf Vasquez, Director of Software Engineering at Strathmore Rail, connected 2015-02-06 |
| 0.000 | 0.202 | Elena Duvall (Advisor) | alumni | Bertrand Lomsadze — ex-Strathmore Rail (2013-2017), now Chief Digital Officer at Strathmore Rail | investor_network.csv: Bertrand Lomsadze prior_employer=Strathmore Rail (2013-2017); connections_duvall.csv: connection of Elena Duvall since 2017-03-25 |
| 0.000 | 0.187 | Elena Duvall (Advisor) | alumni | Yusuf Vasquez — ex-Strathmore Rail (2014-2017), now Director of Software Engineering at Strathmore Rail | investor_network.csv: Yusuf Vasquez prior_employer=Strathmore Rail (2014-2017); connections_duvall.csv: connection of Elena Duvall since 2015-02-06 |

strongest path, not where it went: Elena Duvall, direct 0.357, at capacity 3/3, Transport is outside their focus (route score 0.000); R1027 routed to Tomás Beckett, R1125 routed to Tomás Beckett, R1132 routed to Tomás Beckett

## 4. Chronology (36 events, 7 requests, as of 2026-09-06)

```
   2025-10-27  intro_requests.csv   Yusuf Petrossian     R1102 raised by Yusuf Petrossian (SDR Lead): wants VP Engineering, $400,000, Low urgency, filed "Routed"
   2025-10-27  slack_threads.jsonl  Yusuf Petrossian     R1102 slack: "any connections into Strathmore Rail? we're up against a renewal window and I need an intro to VP Engineering"
   2025-10-27  slack_threads.jsonl  Curtis Hartigan      R1102 slack: "no idea sorry"
   2025-10-30  slack_threads.jsonl  Yusuf Petrossian     R1102 slack: "I think their procurement is frozen until Q1"
   2025-10-31  slack_threads.jsonl  Hana Nakashima       R1102 slack: "is this the same as the one from last month?"
   2025-10-31  intro_outcomes.csv   Marcus Aldridge      R1102 asked
++ 2025-11-01  intro_outcomes.csv   Marcus Aldridge      R1102 replied (1 days after the ask)
<- 2026-09-06  intro_outcomes.csv   Marcus Aldridge      R1102 said yes 309 days ago and never forwarded

   2025-12-13  intro_requests.csv   Sloane Fairweather   R1132 raised by Sloane Fairweather (Strategic AE): wants Chief Operating Officer, $150,000, High urgency, filed "Routed"
   2025-12-13  slack_threads.jsonl  Sloane Fairweather   R1132 slack: "asking again: Strathmore Rail. Chief Operating Officer. Happy to draft the forward myself if someone can vouch."

!! 2025-12-16  intro_requests.csv   Curtis Hartigan      R1093 raised by Curtis Hartigan (AE, Financial Services): wants Head of Platform Engineering, $1,200,000, Critical urgency, filed "Closed - no path"  [12 paths in supply_reach.csv]
   2025-12-16  slack_threads.jsonl  Curtis Hartigan      R1093 slack: "long shot — Strathmore Rail. Rafael Hartigan-Zubkov (Head of Platform Engineering). Anyone?"
   2025-12-16  intro_outcomes.csv   Marcus Aldridge      R1093 asked
   2025-12-17  slack_threads.jsonl  Nadia Okonkwo        R1093 slack: "wrong channel? this feels like a partner ask"
   2025-12-18  slack_threads.jsonl  Curtis Hartigan      R1093 slack: "adding Bertrand Vandermolen who might know"
   2025-12-19  slack_threads.jsonl  Hana Nakashima       R1093 slack: "is this the same as the one from last month?"
<- 2026-09-06  intro_outcomes.csv   Marcus Aldridge      R1093 never replied (asked 2025-12-16, 264 days ago)

   2026-06-16  intro_requests.csv   Rafael Salcedo       R1053 raised by Rafael Salcedo (AE, Transport & Logistics): wants VP Data & Analytics, $400,000, Medium urgency, filed "Stalled"
   2026-06-16  slack_threads.jsonl  Rafael Salcedo       R1053 slack: "asking again: Strathmore Rail. VP Data & Analytics. Happy to draft the forward myself if someone can vouch."
   2026-06-22  intro_outcomes.csv   Marcus Aldridge      R1053 asked
<- 2026-09-06  intro_outcomes.csv   Marcus Aldridge      R1053 never replied (asked 2026-06-22, 76 days ago)

!! 2026-06-23  intro_requests.csv   Hana Nakashima       R1094 raised by Hana Nakashima (AE, Healthcare): wants VP Data & Analytics, $750,000, High urgency, filed "Open"  [same title as R1053, 7 days earlier]
   2026-06-23  slack_threads.jsonl  Hana Nakashima       R1094 slack: "long shot — Strathmore Rail. Hugo Glückstein-Sandoval (VP Data & Analytics). Anyone?"
   2026-06-23  intro_outcomes.csv   Marcus Aldridge      R1094 asked
<- 2026-09-06  intro_outcomes.csv   Marcus Aldridge      R1094 never replied (asked 2026-06-23, 75 days ago)

   2026-07-05  intro_requests.csv   Hana Nakashima       R1027 raised by Hana Nakashima (AE, Healthcare): wants Chief Technology Officer, $400,000, High urgency, filed "Routed"
   2026-07-05  slack_threads.jsonl  Hana Nakashima       R1027 slack: "asking again: Strathmore Rail. Chief Technology Officer. Happy to draft the forward myself if someone can vouch."
   2026-07-06  slack_threads.jsonl  Nadia Okonkwo        R1027 slack: "I think their procurement is frozen until Q1"
   2026-07-07  slack_threads.jsonl  Hana Nakashima       R1027 slack: "adding Yusuf Petrossian who might know"
   2026-07-09  slack_threads.jsonl  Sloane Fairweather   R1027 slack: "I think their procurement is frozen until Q1"

!! 2026-07-05  intro_requests.csv   Sloane Fairweather   R1125 raised by Sloane Fairweather (Strategic AE): wants Chief Operating Officer, $400,000, High urgency, filed "Open"  [same title as R1132, 204 days earlier]
   2026-07-05  slack_threads.jsonl  Sloane Fairweather   R1125 slack: "asking again: Strathmore Rail. Chief Operating Officer. Happy to draft the forward myself if someone can vouch."
   2026-07-06  slack_threads.jsonl  Imani Mkhize         R1125 slack: "what's the deal size here?"
   2026-07-06  slack_threads.jsonl  Nadia Okonkwo        R1125 slack: "bumping this"
   2026-07-06  slack_threads.jsonl  Nadia Okonkwo        R1125 slack: "did we not already lose this one?"

   2026-06-23  crm_accounts.csv     Imani Mkhize         last CRM touch on A1026
```

## 5. Additional Investor and Operator Network

4 people from investor_network.csv, 1 with no warm path; read-only: not scored, not allocated, not on supply_reach.csv

| person | role | fund | board seat | source | warm path |
|---|---|---|---|---|---|
| Bertrand Lomsadze | Operator (work history) |  | no | prior_employer | via Beckett, Duvall |
| Tomás Dobrescu | Operator (work history) |  | no | prior_employer | via Aldridge, Beckett |
| Yusuf Vasquez | Operator (work history) |  | no | prior_employer | via Aldridge, Duvall |
| Freya Oldfield-Ibarra | Venture capital investor | Ashgrove Capital | no | portfolio_company | no warm path |
