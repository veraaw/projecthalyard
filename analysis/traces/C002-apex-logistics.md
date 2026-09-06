# Apex Logistics  (C002)

- stage: Prospect | industry: Logistics | owner: Rafael Salcedo | Yusuf Petrossian | deal value: $2,200,000 (CRM ARR potential) | by request: R1024 $2,000,000, R1038 $250,000, R1041 $750,000, R1197 $250,000
- CRM accounts: A1001 | A91001 (apexlogistics.com) | duplicates: yes - owners disagree
- also goes by: Apex Logistics, Inc.
- 4 requests from 4 people wanting 4 different titles: Chief Operating Officer | Director of Software Engineering | Head of Developer Productivity | SVP Digital

## 2. Where the files disagree

- crm_accounts.csv: two accounts, two owners: A1001 -> Rafael Salcedo; A91001 -> Yusuf Petrossian
- R1197: filed "Intro sent" but intro_outcomes.csv has no intro (asked Elena Duvall, intro_sent=N)

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.133 | 0.383 | Marcus Aldridge (Advisor) | direct | Curtis Prendergast — SVP Digital | connections_aldridge.csv: Curtis Prendergast, SVP Digital at Apex Logistics, connected 2019-08-28 |
| 0.000 | 0.459 | Elena Duvall (Advisor) | direct | Curtis Prendergast — SVP Digital | connections_duvall.csv: Curtis Prendergast, SVP Digital at Apex Logistics, connected 2022-02-04 |

why not #1: Elena Duvall at capacity 3/3, outside focus (Logistics) -> R1024, R1041 to Marcus Aldridge

## 4. Chronology (25 events, 4 requests, newest first, as of 2026-09-06)

```
<- 2026-09-06  intro_outcomes.csv   Elena Duvall         R1197 said yes 378 days ago and never forwarded
++ 2025-08-24  intro_outcomes.csv   Elena Duvall         R1197 replied (10 days after the ask)
   2025-08-14  intro_outcomes.csv   Elena Duvall         R1197 asked
   2025-08-10  slack_threads.jsonl  Nadia Okonkwo        R1197 slack: "adding Rafael Salcedo who might know"
   2025-08-09  slack_threads.jsonl  Rafael Salcedo       R1197 slack: "bumping this"
   2025-08-08  slack_threads.jsonl  Imani Mkhize         R1197 slack: "need an intro at Apex Logistics — anyone?"
!! 2025-08-08  intro_requests.csv   Imani Mkhize         R1197 raised by Imani Mkhize (Enterprise AE, West): wants Head of Developer Productivity, $250,000, Low urgency, filed "Intro sent"  [no intro in intro_outcomes.csv]

   2026-07-08  slack_threads.jsonl  Nadia Okonkwo        R1024 slack: "adding Rafael Salcedo who might know"
   2026-07-07  slack_threads.jsonl  Sloane Fairweather   R1024 slack: "I think their procurement is frozen until Q1"
   2026-07-06  slack_threads.jsonl  Rafael Salcedo       R1024 slack: "is this the same as the one from last month?"
   2026-07-04  slack_threads.jsonl  Curtis Hartigan      R1024 slack: "who do we know at Apex Logistics? Director of Software Engineering would be ideal but I'll take anyone senior"
   2026-07-04  intro_requests.csv   Curtis Hartigan      R1024 raised by Curtis Hartigan (AE, Financial Services): wants Director of Software Engineering, $2,000,000, High urgency, filed "Routed"

++ 2026-06-10  intro_outcomes.csv   Elena Duvall         R1038 meeting booked
++ 2026-06-10  intro_outcomes.csv   Elena Duvall         R1038 intro sent
++ 2026-06-02  intro_outcomes.csv   Elena Duvall         R1038 replied (11 days after the ask)
   2026-05-22  intro_outcomes.csv   Elena Duvall         R1038 asked
   2026-05-21  slack_threads.jsonl  Imani Mkhize         R1038 slack: "did we not already lose this one?"
   2026-05-18  slack_threads.jsonl  Hana Nakashima       R1038 slack: "no idea sorry"
   2026-05-18  slack_threads.jsonl  Nadia Okonkwo        R1038 slack: "trying to reach Chief Operating Officer at Apex Logistics. I know we sell into Larkhall Software and Cindermill Mining — could either of those relationships get us there?"
   2026-05-18  intro_requests.csv   Nadia Okonkwo        R1038 raised by Nadia Okonkwo (AE, Industrials): wants Chief Operating Officer, $250,000, High urgency, filed "Intro sent"

   2025-12-05  slack_threads.jsonl  Imani Mkhize         R1041 slack: "is this the same as the one from last month?"
   2025-12-03  slack_threads.jsonl  Imani Mkhize         R1041 slack: "bumping this"
   2025-12-02  slack_threads.jsonl  Hana Nakashima       R1041 slack: "trying to reach SVP Digital at Apex Logistics — anyone have a path?"
   2025-12-02  intro_requests.csv   Hana Nakashima       R1041 raised by Hana Nakashima (AE, Healthcare): wants SVP Digital, $750,000, Medium urgency, filed "Open"

!! 2026-04-03  crm_accounts.csv     Rafael Salcedo       last CRM touch on A1001  [156 days ago, nothing since]
```
