# Harrowgate Health  (C018)

- stage: Pilot | industry: Healthcare | owner: Imani Mkhize | deal value: $3,500,000 (CRM ARR potential) | by request: R1057 $250,000, R1157 $750,000, R1136 $1,200,000, R1090 $400,000, R1153 $750,000, R1072 $750,000, R1173 $150,000, R1140 $80,000, R1137 $250,000
- CRM accounts: A1050 (harrowgatehealth.com)
- also goes by: nothing else
- 9 requests from 7 people wanting 6 different titles: Chief Digital Officer | Chief Information Officer | Chief Operating Officer | SVP Digital | VP Engineering | VP Enterprise Architecture

## 2. Where the files disagree

- R1090: filed "Closed - no path" but supply_reach.csv has 11 paths into Harrowgate Health
- R1136: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 11 paths
- R1136: Elena Duvall offered in slack_threads.jsonl on 2026-03-16 ("their Head of Platform reports to someone I've known for a decade, leave it with me") but intro_outcomes.csv never asked them
- R1140: filed "Open" but intro_outcomes.csv says Tomás Beckett sent the intro on 2025-10-08
- R1173: filed "Intro sent" but intro_outcomes.csv has no row at all

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.079 | 0.492 | Tomás Beckett (Internal) | direct | Marcus Salcedo — Director of Software Engineering | connections_beckett.csv: Marcus Salcedo, Director of Software Engineering at Harrowgate Health, connected 2026-03-16 |
| 0.079 | 0.384 | Priya Raghunathan (Investor) | direct | Amara Thackeray — Chief Operating Officer | connections_raghunathan.csv: Amara Thackeray, Chief Operating Officer at Harrowgate Health, connected 2018-10-25 |
| 0.070 | 0.448 | Marcus Aldridge (Advisor) | direct | Marcus Salcedo — Director of Software Engineering | connections_aldridge.csv: Marcus Salcedo, Director of Software Engineering at Harrowgate Health, connected 2024-04-17 |
| 0.064 | 0.330 | Dana Whitfield (Internal) | direct | Amara Thackeray — Chief Operating Officer | connections_whitfield.csv: Amara Thackeray, Chief Operating Officer at Harrowgate Health, connected 2016-11-21 |
| 0.060 | 0.309 | Dana Whitfield (Internal) | direct | Ingrid Marchetti — Head of Developer Productivity | connections_whitfield.csv: Ingrid Marchetti, Head of Developer Productivity at Harrowgate Health, connected 2017-10-05 |
| 0.045 | 0.218 | Priya Raghunathan (Investor) | alumni | Amara Thackeray — ex-Harrowgate Health (2012-2019), now Chief Operating Officer at Harrowgate Health | investor_network.csv: Amara Thackeray prior_employer=Harrowgate Health (2012-2019); connections_raghunathan.csv: connection of Priya Raghunathan since 2018-10-25 |
| 0.039 | 0.202 | Dana Whitfield (Internal) | alumni | Ingrid Marchetti — ex-Harrowgate Health (2015-2018), now Head of Developer Productivity at Harrowgate Health | investor_network.csv: Ingrid Marchetti prior_employer=Harrowgate Health (2015-2018); connections_whitfield.csv: connection of Dana Whitfield since 2017-10-05 |
| 0.036 | 0.187 | Dana Whitfield (Internal) | alumni | Amara Thackeray — ex-Harrowgate Health (2012-2019), now Chief Operating Officer at Harrowgate Health | investor_network.csv: Amara Thackeray prior_employer=Harrowgate Health (2012-2019); connections_whitfield.csv: connection of Dana Whitfield since 2016-11-21 |
| 0.032 | 0.285 | Owen Trask (Investor) | direct | Ingrid Marchetti — Head of Developer Productivity | connections_trask.csv: Ingrid Marchetti, Head of Developer Productivity at Harrowgate Health, connected 2016-01-02 |
| 0.021 | 0.187 | Owen Trask (Investor) | alumni | Ingrid Marchetti — ex-Harrowgate Health (2015-2018), now Head of Developer Productivity at Harrowgate Health | investor_network.csv: Ingrid Marchetti prior_employer=Harrowgate Health (2015-2018); connections_trask.csv: connection of Owen Trask since 2016-01-02 |
| 0.000 | 0.800 | Elena Duvall (Advisor) | offer | Head of Platform | slack_threads.jsonl R1136 2026-03-16 Elena Duvall: "their Head of Platform reports to someone I've known for a decade, leave it with me" |

why not #1: Elena Duvall at capacity 3/3, outside focus (Healthcare) -> R1136, R1140 unrouted (capacity exhausted); R1153 to Tomás Beckett

## 4. Chronology (51 events, 9 requests, newest first, as of 2026-09-06)

```
<- 2026-09-06  intro_outcomes.csv   Tomás Beckett        R1157 said yes 120 days ago and never forwarded
++ 2026-05-09  intro_outcomes.csv   Tomás Beckett        R1157 replied (8 days after the ask)
   2026-05-02  slack_threads.jsonl  Bertrand Vandermolen R1157 slack: "I think their procurement is frozen until Q1"
   2026-05-01  intro_outcomes.csv   Tomás Beckett        R1157 asked
   2026-04-29  slack_threads.jsonl  Yusuf Petrossian     R1157 slack: "is this the same as the one from last month?"
   2026-04-28  slack_threads.jsonl  Nadia Okonkwo        R1157 slack: "what's the deal size here?"
   2026-04-28  slack_threads.jsonl  Yusuf Petrossian     R1157 slack: "does anyone know anyone at Harrowgate Health? looking for VP Enterprise Architecture, ideally warm"
   2026-04-28  intro_requests.csv   Yusuf Petrossian     R1157 raised by Yusuf Petrossian (SDR Lead): wants VP Enterprise Architecture, $750,000, Medium urgency, filed "Stalled"

<- 2026-09-06  intro_outcomes.csv   Tomás Beckett        R1137 never replied (asked 2025-09-16, 355 days ago)
   2025-09-17  slack_threads.jsonl  Imani Mkhize         R1137 slack: "bumping this"
   2025-09-16  intro_outcomes.csv   Tomás Beckett        R1137 asked
   2025-09-16  slack_threads.jsonl  Yusuf Petrossian     R1137 slack: "no idea sorry"
   2025-09-15  slack_threads.jsonl  Imani Mkhize         R1137 slack: "trying to reach Chief Digital Officer at Harrowgate Health — anyone have a path?"
   2025-09-15  intro_requests.csv   Imani Mkhize         R1137 raised by Imani Mkhize (Enterprise AE, West): wants Chief Digital Officer, $250,000, High urgency, filed "Open"

<- 2026-09-06  intro_outcomes.csv   Tomás Beckett        R1090 never replied (asked 2025-12-20, 260 days ago)
   2025-12-20  intro_outcomes.csv   Tomás Beckett        R1090 asked
   2025-12-19  slack_threads.jsonl  Nadia Okonkwo        R1090 slack: "is this the same as the one from last month?"
   2025-12-18  slack_threads.jsonl  Sloane Fairweather   R1090 slack: "no idea sorry"
   2025-12-17  slack_threads.jsonl  Hana Nakashima       R1090 slack: "any connections into Harrowgate Health? we're up against a renewal window and I need an intro to VP Engineering"
!! 2025-12-17  intro_requests.csv   Hana Nakashima       R1090 raised by Hana Nakashima (AE, Healthcare): wants VP Engineering, $400,000, Medium urgency, filed "Closed - no path"  [11 paths in supply_reach.csv; same title as R1173, 72 days earlier]

<- 2026-09-06  intro_outcomes.csv   Tomás Beckett        R1072 never replied (asked 2025-11-03, 307 days ago)
   2025-11-04  slack_threads.jsonl  Rafael Salcedo       R1072 slack: "no idea sorry"
   2025-11-03  intro_outcomes.csv   Tomás Beckett        R1072 asked
   2025-11-02  slack_threads.jsonl  Bertrand Vandermolen R1072 slack: "adding Sloane Fairweather who might know"
   2025-10-31  slack_threads.jsonl  Sloane Fairweather   R1072 slack: "long shot — Harrowgate Health. Liesel Marchetti-Wolstenholme (SVP Digital). Anyone?"
   2025-10-31  intro_requests.csv   Sloane Fairweather   R1072 raised by Sloane Fairweather (Strategic AE): wants SVP Digital, $750,000, Low urgency, filed "Open"

<- 2026-09-06  intro_outcomes.csv   Tomás Beckett        R1057 said yes 65 days ago and never forwarded
++ 2026-07-03  intro_outcomes.csv   Tomás Beckett        R1057 replied (12 days after the ask)
   2026-06-21  intro_outcomes.csv   Tomás Beckett        R1057 asked
   2026-06-18  slack_threads.jsonl  Rafael Salcedo       R1057 slack: "wrong channel? this feels like a partner ask"
   2026-06-18  slack_threads.jsonl  Sloane Fairweather   R1057 slack: "what's the deal size here?"
   2026-06-16  slack_threads.jsonl  Yusuf Petrossian     R1057 slack: "bumping this"
   2026-06-16  slack_threads.jsonl  Curtis Hartigan      R1057 slack: "any connections into Harrowgate Health? we're up against a renewal window and I need an intro to Chief Information Officer"
   2026-06-16  intro_requests.csv   Curtis Hartigan      R1057 raised by Curtis Hartigan (AE, Financial Services): wants Chief Information Officer, $250,000, High urgency, filed "Stalled"

   2026-03-17  slack_threads.jsonl  Bertrand Vandermolen R1136 slack: "what's the deal size here?"
** 2026-03-16  slack_threads.jsonl  Elena Duvall         R1136 slack: "their Head of Platform reports to someone I've known for a decade, leave it with me"  [never taken up]
   2026-03-14  slack_threads.jsonl  Nadia Okonkwo        R1136 slack: "who do we know at Harrowgate Health? SVP Digital would be ideal but I'll take anyone senior"
!! 2026-03-14  intro_requests.csv   Nadia Okonkwo        R1136 raised by Nadia Okonkwo (AE, Industrials): wants SVP Digital, $1,200,000, Low urgency, filed "Open"  [same title as R1072, 134 days earlier]

   2025-11-29  slack_threads.jsonl  Nadia Okonkwo        R1153 slack: "does anyone know anyone at Harrowgate Health? looking for Chief Operating Officer, ideally warm"
   2025-11-29  intro_requests.csv   Nadia Okonkwo        R1153 raised by Nadia Okonkwo (AE, Industrials): wants Chief Operating Officer, $750,000, Critical urgency, filed "Stalled"

++ 2025-10-08  intro_outcomes.csv   Tomás Beckett        R1140 intro sent
++ 2025-09-27  intro_outcomes.csv   Tomás Beckett        R1140 replied (9 days after the ask)
   2025-09-21  slack_threads.jsonl  Rafael Salcedo       R1140 slack: "bumping this"
   2025-09-18  intro_outcomes.csv   Tomás Beckett        R1140 asked
   2025-09-18  slack_threads.jsonl  Yusuf Petrossian     R1140 slack: "wrong channel? this feels like a partner ask"
   2025-09-17  slack_threads.jsonl  Yusuf Petrossian     R1140 slack: "what's the deal size here?"
   2025-09-17  slack_threads.jsonl  Yusuf Petrossian     R1140 slack: "need help getting to Harrowgate Health. Freya Lindqvist-Eastcott is the Chief Digital Officer there, cold outbound is going nowhere"
!! 2025-09-17  intro_requests.csv   Yusuf Petrossian     R1140 raised by Yusuf Petrossian (SDR Lead): wants Chief Digital Officer, $80,000, Low urgency, filed "Open"  [same title as R1137, 2 days earlier]

   2025-10-06  slack_threads.jsonl  Rafael Salcedo       R1173 slack: "does anyone know anyone at Harrowgate Health? looking for VP Engineering, ideally warm"
!! 2025-10-06  intro_requests.csv   Rafael Salcedo       R1173 raised by Rafael Salcedo (AE, Transport & Logistics): wants VP Engineering, $150,000, Medium urgency, filed "Intro sent"  [no intro in intro_outcomes.csv]

!! 2026-05-14  crm_accounts.csv     Imani Mkhize         last CRM touch on A1050  [115 days ago, nothing since]
```

## 5. Additional Investor and Operator Network

2 people from investor_network.csv, 0 askable as investor_network paths, 0 with no warm path; a view of section 3 and the roster's exports, nothing here is scored or allocated on its own

| person | role | fund | board seat | source | warm path |
|---|---|---|---|---|---|
| Amara Thackeray | Operator (work history) |  | no | prior_employer | via Raghunathan, Whitfield |
| Ingrid Marchetti | Operator (work history) |  | no | prior_employer | via Trask, Whitfield |
