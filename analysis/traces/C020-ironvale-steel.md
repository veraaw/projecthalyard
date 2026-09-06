# Ironvale Steel  (C020)

- stage: Negotiation | industry: Industrials | owner: Hana Nakashima | deal value: $600,000 | largest request: $400,000
- CRM accounts: A1009 (ironvalesteel.com)
- also goes by: nothing else
- 5 requests from 4 people wanting 3 different titles: Chief Data Officer | Chief Technology Officer | VP Enterprise Architecture

## 2. Where the files disagree

- R1040: filed "Intro sent" but intro_outcomes.csv has no row at all
- R1089: filed "Closed - no path" but supply_reach.csv has 6 paths into Ironvale Steel

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.208 | 0.600 | Marcus Aldridge (Advisor) | direct | Tanvi Eastcott — Chief Data Officer | connections_aldridge.csv: Tanvi Eastcott, Chief Data Officer at Ironvale Steel, connected 2026-07-05 |
| 0.123 | 0.600 | Priya Raghunathan (Investor) | direct | Tanvi Eastcott — Chief Data Officer | connections_raghunathan.csv: Tanvi Eastcott, Chief Data Officer at Ironvale Steel, connected 2027-07-04 |
| 0.121 | 0.349 | Marcus Aldridge (Advisor) | direct | Tomás Ferreira — VP Enterprise Architecture | connections_aldridge.csv: Tomás Ferreira, VP Enterprise Architecture at Ironvale Steel, connected 2018-11-19 |
| 0.076 | 0.218 | Marcus Aldridge (Advisor) | alumni | Tomás Ferreira — ex-Ironvale Steel (2015-2020), now VP Enterprise Architecture at Ironvale Steel | investor_network.csv: Tomás Ferreira prior_employer=Ironvale Steel (2015-2020); connections_aldridge.csv: connection of Marcus Aldridge since 2018-11-19 |
| 0.067 | 0.325 | Priya Raghunathan (Investor) | direct | Tomás Ferreira — VP Enterprise Architecture | connections_raghunathan.csv: Tomás Ferreira, VP Enterprise Architecture at Ironvale Steel, connected 2017-06-21 |
| 0.041 | 0.202 | Priya Raghunathan (Investor) | alumni | Tomás Ferreira — ex-Ironvale Steel (2015-2020), now VP Enterprise Architecture at Ironvale Steel | investor_network.csv: Tomás Ferreira prior_employer=Ironvale Steel (2015-2020); connections_raghunathan.csv: connection of Priya Raghunathan since 2017-06-21 |

## 4. Chronology (31 events, 5 requests, as of 2026-09-06)

```
   2025-11-25  intro_requests.csv   Curtis Hartigan      R1141 raised by Curtis Hartigan (AE, Financial Services): wants VP Enterprise Architecture, $400,000, High urgency, filed "Intro sent"
   2025-11-25  slack_threads.jsonl  Curtis Hartigan      R1141 slack: "need help getting to Ironvale Steel. Priya Rushworth-Fairweather is the VP Enterprise Architecture there, cold outbound is going nowhere"
   2025-11-25  intro_outcomes.csv   Priya Raghunathan    R1141 asked
   2025-11-26  slack_threads.jsonl  Bertrand Vandermolen R1141 slack: "did we not already lose this one?"
   2025-11-26  slack_threads.jsonl  Nadia Okonkwo        R1141 slack: "what's the deal size here?"
   2025-11-26  slack_threads.jsonl  Nadia Okonkwo        R1141 slack: "did we not already lose this one?"
++ 2025-11-28  intro_outcomes.csv   Priya Raghunathan    R1141 replied (3 days after the ask)
++ 2025-12-06  intro_outcomes.csv   Priya Raghunathan    R1141 intro sent

   2025-11-26  intro_requests.csv   Imani Mkhize         R1031 raised by Imani Mkhize (Enterprise AE, West): wants Chief Data Officer, $80,000, High urgency, filed "Open"
   2025-11-26  slack_threads.jsonl  Imani Mkhize         R1031 slack: "does anyone know anyone at Ironvale Steel? looking for Chief Data Officer, ideally warm"
   2025-11-28  slack_threads.jsonl  Yusuf Petrossian     R1031 slack: "is this the same as the one from last month?"
   2025-11-28  slack_threads.jsonl  Hana Nakashima       R1031 slack: "what's the deal size here?"
   2025-11-30  slack_threads.jsonl  Rafael Salcedo       R1031 slack: "wrong channel? this feels like a partner ask"
   2025-11-30  intro_outcomes.csv   Priya Raghunathan    R1031 asked
<- 2026-09-06  intro_outcomes.csv   Priya Raghunathan    R1031 never replied (asked 2025-11-30, 280 days ago)

!! 2026-02-17  intro_requests.csv   Sloane Fairweather   R1086 raised by Sloane Fairweather (Strategic AE): wants VP Enterprise Architecture, $150,000, Critical urgency, filed "Open"  [same title as R1141, 84 days earlier]
   2026-02-17  slack_threads.jsonl  Sloane Fairweather   R1086 slack: "who do we know at Ironvale Steel? VP Enterprise Architecture would be ideal but I'll take anyone senior"
   2026-02-17  slack_threads.jsonl  Imani Mkhize         R1086 slack: "no idea sorry"
   2026-02-18  slack_threads.jsonl  Rafael Salcedo       R1086 slack: "adding Hana Nakashima who might know"
   2026-02-20  slack_threads.jsonl  Sloane Fairweather   R1086 slack: "is this the same as the one from last month?"
   2026-02-20  intro_outcomes.csv   Priya Raghunathan    R1086 asked
<- 2026-09-06  intro_outcomes.csv   Priya Raghunathan    R1086 never replied (asked 2026-02-20, 198 days ago)

!! 2026-02-18  intro_requests.csv   Hana Nakashima       R1089 raised by Hana Nakashima (AE, Healthcare): wants VP Enterprise Architecture, $400,000, High urgency, filed "Closed - no path"  [6 paths in supply_reach.csv; same title as R1141, 85 days earlier]
   2026-02-18  slack_threads.jsonl  Hana Nakashima       R1089 slack: "who do we know at Ironvale Steel? VP Enterprise Architecture would be ideal but I'll take anyone senior"
   2026-02-22  slack_threads.jsonl  Imani Mkhize         R1089 slack: "what's the deal size here?"

!! 2026-06-29  intro_requests.csv   Sloane Fairweather   R1040 raised by Sloane Fairweather (Strategic AE): wants Chief Technology Officer, $80,000, High urgency, filed "Intro sent"  [no intro in intro_outcomes.csv]
   2026-06-29  slack_threads.jsonl  Sloane Fairweather   R1040 slack: "trying to reach Chief Technology Officer at Ironvale Steel — anyone have a path?"
   2026-06-29  slack_threads.jsonl  Nadia Okonkwo        R1040 slack: "no idea sorry"
   2026-06-30  slack_threads.jsonl  Hana Nakashima       R1040 slack: "adding Sloane Fairweather who might know"
   2026-07-01  slack_threads.jsonl  Nadia Okonkwo        R1040 slack: "wrong channel? this feels like a partner ask"

!! 2026-04-16  crm_accounts.csv     Hana Nakashima       last CRM touch on A1009  [143 days ago, nothing since]
```
