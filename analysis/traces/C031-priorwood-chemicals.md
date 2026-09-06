# Priorwood Chemicals  (C031)

- stage: Discovery | industry: Chemicals | owner: Bertrand Vandermolen | deal value: $3,500,000 | largest request: $2,000,000
- CRM accounts: A1030 (priorwood.com)
- also goes by: nothing else
- 9 requests from 6 people wanting 7 different titles: Chief Data Officer | Chief Information Officer | Chief Operating Officer | Chief Technology Officer | Head of Developer Productivity | Head of Platform Engineering | VP Enterprise Architecture

## 2. Where the files disagree

- R1033: filed "Closed - no path" but supply_reach.csv has 8 paths into Priorwood Chemicals
- R1150: filed "Stalled" but intro_outcomes.csv says Tomás Beckett sent the intro on 2026-03-16
- R1196: filed "Stalled" but intro_outcomes.csv says Tomás Beckett sent the intro on 2026-02-20

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.108 | 0.300 | Elena Duvall (Advisor) | direct | Curtis Marchetti — VP Enterprise Architecture | connections_duvall.csv: Curtis Marchetti, VP Enterprise Architecture at Priorwood Chemicals, connected 2014-02-22 |
| 0.067 | 0.187 | Elena Duvall (Advisor) | alumni | Curtis Marchetti — ex-Priorwood Chemicals (2010-2017), now VP Enterprise Architecture at Priorwood Chemicals | investor_network.csv: Curtis Marchetti prior_employer=Priorwood Chemicals (2010-2017); connections_duvall.csv: connection of Elena Duvall since 2014-02-22 |
| 0.048 | 0.300 | Tomás Beckett (Internal) | direct | Curtis Marchetti — VP Enterprise Architecture | connections_beckett.csv: Curtis Marchetti, VP Enterprise Architecture at Priorwood Chemicals, connected 2014-07-13 |
| 0.044 | 0.271 | Tomás Beckett (Internal) | direct | Margot Havercamp — Director of Software Engineering | connections_beckett.csv: Margot Havercamp, Director of Software Engineering at Priorwood Chemicals, connected 2015-01-12 |
| 0.042 | 0.271 | Marcus Aldridge (Advisor) | direct | Margot Havercamp — Director of Software Engineering | connections_aldridge.csv: Margot Havercamp, Director of Software Engineering at Priorwood Chemicals, connected 2014-03-11 |
| 0.030 | 0.187 | Tomás Beckett (Internal) | alumni | Curtis Marchetti — ex-Priorwood Chemicals (2010-2017), now VP Enterprise Architecture at Priorwood Chemicals | investor_network.csv: Curtis Marchetti prior_employer=Priorwood Chemicals (2010-2017); connections_beckett.csv: connection of Tomás Beckett since 2014-07-13 |
| 0.030 | 0.187 | Tomás Beckett (Internal) | alumni | Margot Havercamp — ex-Priorwood Chemicals (2011-2017), now Director of Software Engineering at Priorwood Chemicals | investor_network.csv: Margot Havercamp prior_employer=Priorwood Chemicals (2011-2017); connections_beckett.csv: connection of Tomás Beckett since 2015-01-12 |
| 0.029 | 0.187 | Marcus Aldridge (Advisor) | alumni | Margot Havercamp — ex-Priorwood Chemicals (2011-2017), now Director of Software Engineering at Priorwood Chemicals | investor_network.csv: Margot Havercamp prior_employer=Priorwood Chemicals (2011-2017); connections_aldridge.csv: connection of Marcus Aldridge since 2014-03-11 |

strongest path, not where it went: Elena Duvall, direct 0.300, at capacity 3/3; R1092 unrouted (already introduced: Tomás Beckett on 2026-03-16 (R1150, meeting booked)), R1174 unrouted (already introduced: Tomás Beckett on 2026-03-16 (R1150, meeting booked))

## 4. Chronology (56 events, 9 requests, as of 2026-09-06)

```
   2025-08-18  intro_requests.csv   Imani Mkhize         R1192 raised by Imani Mkhize (Enterprise AE, West): wants Chief Operating Officer, $2,000,000, High urgency, filed "Intro sent"
   2025-08-18  slack_threads.jsonl  Imani Mkhize         R1192 slack: "trying to reach Chief Operating Officer at Priorwood Chemicals — anyone have a path?"
   2025-08-18  slack_threads.jsonl  Sloane Fairweather   R1192 slack: "did we not already lose this one?"
   2025-08-19  slack_threads.jsonl  Imani Mkhize         R1192 slack: "I think their procurement is frozen until Q1"
   2025-08-20  slack_threads.jsonl  Nadia Okonkwo        R1192 slack: "is this the same as the one from last month?"
   2025-08-23  intro_outcomes.csv   Tomás Beckett        R1192 asked
++ 2025-08-26  intro_outcomes.csv   Tomás Beckett        R1192 replied (3 days after the ask)
++ 2025-08-31  intro_outcomes.csv   Tomás Beckett        R1192 intro sent
++ 2025-08-31  intro_outcomes.csv   Tomás Beckett        R1192 meeting booked
++ 2025-08-31  intro_outcomes.csv   Tomás Beckett        R1192 opportunity created, $2,000,000

   2025-08-19  intro_requests.csv   Yusuf Petrossian     R1052 raised by Yusuf Petrossian (SDR Lead): wants Head of Platform Engineering, $80,000, Low urgency, filed "Open"
   2025-08-19  slack_threads.jsonl  Yusuf Petrossian     R1052 slack: "asking again: Priorwood Chemicals. Head of Platform Engineering. Happy to draft the forward myself if someone can vouch."
   2025-08-20  intro_outcomes.csv   Tomás Beckett        R1052 asked
   2025-08-21  slack_threads.jsonl  Nadia Okonkwo        R1052 slack: "bumping this"
<- 2026-09-06  intro_outcomes.csv   Tomás Beckett        R1052 never replied (asked 2025-08-20, 382 days ago)

!! 2025-09-15  intro_requests.csv   Nadia Okonkwo        R1118 raised by Nadia Okonkwo (AE, Industrials): wants Chief Operating Officer, $1,200,000, Critical urgency, filed "Open"  [same title as R1192, 28 days earlier]
   2025-09-15  slack_threads.jsonl  Nadia Okonkwo        R1118 slack: "trying to reach Chief Operating Officer at Priorwood Chemicals — anyone have a path?"
   2025-09-16  intro_outcomes.csv   Tomás Beckett        R1118 asked
++ 2025-09-17  intro_outcomes.csv   Tomás Beckett        R1118 replied (1 days after the ask)
   2025-09-18  slack_threads.jsonl  Rafael Salcedo       R1118 slack: "wrong channel? this feels like a partner ask"
<- 2026-09-06  intro_outcomes.csv   Tomás Beckett        R1118 said yes 354 days ago and never forwarded

   2026-02-03  intro_requests.csv   Bertrand Vandermolen R1196 raised by Bertrand Vandermolen (AE, EMEA): wants Chief Technology Officer, $1,200,000, Medium urgency, filed "Stalled"
   2026-02-03  slack_threads.jsonl  Bertrand Vandermolen R1196 slack: "asking again: Priorwood Chemicals. Chief Technology Officer. Happy to draft the forward myself if someone can vouch."
   2026-02-07  intro_outcomes.csv   Tomás Beckett        R1196 asked
++ 2026-02-08  intro_outcomes.csv   Tomás Beckett        R1196 replied (1 days after the ask)
++ 2026-02-20  intro_outcomes.csv   Tomás Beckett        R1196 intro sent
++ 2026-02-20  intro_outcomes.csv   Tomás Beckett        R1196 meeting booked

   2026-03-09  intro_requests.csv   Curtis Hartigan      R1150 raised by Curtis Hartigan (AE, Financial Services): wants Chief Information Officer, $750,000, High urgency, filed "Stalled"
   2026-03-09  slack_threads.jsonl  Curtis Hartigan      R1150 slack: "long shot — Priorwood Chemicals. Odette Balogun-Dobrescu (Chief Information Officer). Anyone?"
   2026-03-09  intro_outcomes.csv   Tomás Beckett        R1150 asked
   2026-03-11  slack_threads.jsonl  Nadia Okonkwo        R1150 slack: "bumping this"
++ 2026-03-11  intro_outcomes.csv   Tomás Beckett        R1150 replied (2 days after the ask)
++ 2026-03-16  intro_outcomes.csv   Tomás Beckett        R1150 intro sent
++ 2026-03-16  intro_outcomes.csv   Tomás Beckett        R1150 meeting booked
++ 2026-03-16  intro_outcomes.csv   Tomás Beckett        R1150 opportunity created, $750,000

   2026-03-20  intro_requests.csv   Curtis Hartigan      R1098 raised by Curtis Hartigan (AE, Financial Services): wants Chief Data Officer, $150,000, Medium urgency, filed "Open"
   2026-03-20  slack_threads.jsonl  Curtis Hartigan      R1098 slack: "need help getting to Priorwood Chemicals. Liesel Merriweather-Lomsadze is the Chief Data Officer there, cold outbound is going nowhere"
   2026-03-20  slack_threads.jsonl  Yusuf Petrossian     R1098 slack: "wrong channel? this feels like a partner ask"
   2026-03-20  slack_threads.jsonl  Nadia Okonkwo        R1098 slack: "adding Sloane Fairweather who might know"
   2026-03-24  slack_threads.jsonl  Sloane Fairweather   R1098 slack: "wrong channel? this feels like a partner ask"
   2026-03-26  intro_outcomes.csv   Tomás Beckett        R1098 asked
++ 2026-03-28  intro_outcomes.csv   Tomás Beckett        R1098 replied (2 days after the ask)
<- 2026-09-06  intro_outcomes.csv   Tomás Beckett        R1098 said yes 162 days ago and never forwarded

   2026-03-28  intro_requests.csv   Sloane Fairweather   R1092 raised by Sloane Fairweather (Strategic AE): wants VP Enterprise Architecture, $750,000, Critical urgency, filed "Stalled"
   2026-03-28  slack_threads.jsonl  Sloane Fairweather   R1092 slack: "who do we know at Priorwood Chemicals? VP Enterprise Architecture would be ideal but I'll take anyone senior"

!! 2026-05-29  intro_requests.csv   Yusuf Petrossian     R1174 raised by Yusuf Petrossian (SDR Lead): wants Head of Platform Engineering, $150,000, Critical urgency, filed "Open"  [same title as R1052, 283 days earlier]
   2026-05-29  slack_threads.jsonl  Yusuf Petrossian     R1174 slack: "trying to reach Head of Platform Engineering at Priorwood Chemicals — anyone have a path?"
   2026-05-29  slack_threads.jsonl  Sloane Fairweather   R1174 slack: "did we not already lose this one?"
   2026-05-31  slack_threads.jsonl  Nadia Okonkwo        R1174 slack: "what's the deal size here?"

!! 2026-06-02  intro_requests.csv   Curtis Hartigan      R1033 raised by Curtis Hartigan (AE, Financial Services): wants Head of Developer Productivity, $750,000, High urgency, filed "Closed - no path"  [8 paths in supply_reach.csv]
   2026-06-02  slack_threads.jsonl  Curtis Hartigan      R1033 slack: "long shot — Priorwood Chemicals. Astrid Thackeray-Grimsby (Head of Developer Productivity). Anyone?"
   2026-06-06  slack_threads.jsonl  Imani Mkhize         R1033 slack: "adding Nadia Okonkwo who might know"
   2026-06-07  intro_outcomes.csv   Tomás Beckett        R1033 asked
++ 2026-06-11  intro_outcomes.csv   Tomás Beckett        R1033 replied (4 days after the ask)
<- 2026-09-06  intro_outcomes.csv   Tomás Beckett        R1033 said yes 87 days ago and never forwarded

!! 2025-10-17  crm_accounts.csv     Bertrand Vandermolen last CRM touch on A1030  [324 days ago, nothing since]
```
