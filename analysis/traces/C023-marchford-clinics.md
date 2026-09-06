# Marchford Clinics  (C023)

- stage: Prospect | industry: Healthcare | owner: Curtis Hartigan | deal value: $2,200,000 | largest request: $2,000,000
- CRM accounts: A1018 (marchfordclinics.com)
- also goes by: nothing else
- 6 requests from 5 people wanting 6 different titles: Chief Information Officer | Chief Technology Officer | Head of Developer Productivity | Head of Platform Engineering | SVP Digital | VP Engineering

## 2. Where the files disagree

- R1121: filed "Stalled" but intro_outcomes.csv says Marcus Aldridge sent the intro on 2025-09-26
- R1009: filed "Intro sent" but intro_outcomes.csv has no row at all

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.081 | 0.519 | Marcus Aldridge (Advisor) | direct | Kofi Jarrold — Chief Information Officer | connections_aldridge.csv: Kofi Jarrold, Chief Information Officer at Marchford Clinics, connected 2023-09-18 |
| 0.063 | 0.310 | Priya Raghunathan (Investor) | direct | Teodor Zubkov — Program Manager | connections_raghunathan.csv: Teodor Zubkov, Program Manager at Marchford Clinics, connected 2020-12-24 |
| 0.035 | 0.310 | Owen Trask (Investor) | direct | Teodor Zubkov — Program Manager | connections_trask.csv: Teodor Zubkov, Program Manager at Marchford Clinics, connected 2020-05-24 |

strongest path, not where it went: Marcus Aldridge, direct 0.519, at capacity 4/4, holds R1004; R1142 unrouted (capacity exhausted this cycle)

## 4. Chronology (31 events, 6 requests, as of 2026-09-06)

```
   2025-09-11  intro_requests.csv   Sloane Fairweather   R1121 raised by Sloane Fairweather (Strategic AE): wants VP Engineering, $80,000, Medium urgency, filed "Stalled"
   2025-09-11  slack_threads.jsonl  Sloane Fairweather   R1121 slack: "Ferrowick Insurance introduced us to Pelham Beverage, but the account I actually need is Marchford Clinics (VP Engineering)."
   2025-09-14  slack_threads.jsonl  Bertrand Vandermolen R1121 slack: "no idea sorry"
   2025-09-17  intro_outcomes.csv   Marcus Aldridge      R1121 asked
++ 2025-09-23  intro_outcomes.csv   Marcus Aldridge      R1121 replied (6 days after the ask)
++ 2025-09-26  intro_outcomes.csv   Marcus Aldridge      R1121 intro sent

   2025-09-26  intro_requests.csv   Rafael Salcedo       R1142 raised by Rafael Salcedo (AE, Transport & Logistics): wants Chief Technology Officer, $2,000,000, Low urgency, filed "Stalled"
   2025-09-26  slack_threads.jsonl  Rafael Salcedo       R1142 slack: "who do we know at Marchford Clinics? Chief Technology Officer would be ideal but I'll take anyone senior"
   2025-09-28  slack_threads.jsonl  Hana Nakashima       R1142 slack: "no idea sorry"

   2026-02-17  intro_requests.csv   Yusuf Petrossian     R1114 raised by Yusuf Petrossian (SDR Lead): wants Head of Platform Engineering, $2,000,000, Medium urgency, filed "Stalled"
   2026-02-17  slack_threads.jsonl  Yusuf Petrossian     R1114 slack: "trying to reach Head of Platform Engineering at Marchford Clinics — anyone have a path?"
   2026-02-19  slack_threads.jsonl  Nadia Okonkwo        R1114 slack: "I think their procurement is frozen until Q1"
   2026-02-19  intro_outcomes.csv   Marcus Aldridge      R1114 asked
   2026-02-21  slack_threads.jsonl  Bertrand Vandermolen R1114 slack: "wrong channel? this feels like a partner ask"
++ 2026-02-24  intro_outcomes.csv   Marcus Aldridge      R1114 replied (5 days after the ask)
<- 2026-09-06  intro_outcomes.csv   Marcus Aldridge      R1114 said yes 194 days ago and never forwarded

!! 2026-04-15  intro_requests.csv   Yusuf Petrossian     R1009 raised by Yusuf Petrossian (SDR Lead): wants SVP Digital, $1,200,000, High urgency, filed "Intro sent"  [no intro in intro_outcomes.csv]
   2026-04-15  slack_threads.jsonl  Yusuf Petrossian     R1009 slack: "long shot — Marchford Clinics. Ansel Lomsadze-Ingleby (SVP Digital). Anyone?"
   2026-04-16  slack_threads.jsonl  Rafael Salcedo       R1009 slack: "no idea sorry"
   2026-04-18  slack_threads.jsonl  Rafael Salcedo       R1009 slack: "did we not already lose this one?"
   2026-04-19  slack_threads.jsonl  Bertrand Vandermolen R1009 slack: "no idea sorry"

   2026-06-02  intro_requests.csv   Curtis Hartigan      R1162 raised by Curtis Hartigan (AE, Financial Services): wants Chief Information Officer, $80,000, High urgency, filed "Open"
   2026-06-02  slack_threads.jsonl  Curtis Hartigan      R1162 slack: "Marchford Clinics is the target. Our champion at Calderon Aerospace used to work with their team, and I think Meridian Peak Foods is a supplier of theirs. Any path?"
   2026-06-02  slack_threads.jsonl  Curtis Hartigan      R1162 slack: "no idea sorry"
   2026-06-04  intro_outcomes.csv   Marcus Aldridge      R1162 asked
<- 2026-09-06  intro_outcomes.csv   Marcus Aldridge      R1162 never replied (asked 2026-06-04, 94 days ago)

   2026-07-06  intro_requests.csv   Imani Mkhize         R1004 raised by Imani Mkhize (Enterprise AE, West): wants Head of Developer Productivity, $750,000, Medium urgency, filed "Open"
   2026-07-06  slack_threads.jsonl  Imani Mkhize         R1004 slack: "long shot — Marchford Clinics. Silas Mkhize-Thackeray (Head of Developer Productivity). Anyone?"
   2026-07-06  slack_threads.jsonl  Yusuf Petrossian     R1004 slack: "wrong channel? this feels like a partner ask"
   2026-07-07  slack_threads.jsonl  Imani Mkhize         R1004 slack: "is this the same as the one from last month?"

!! 2025-07-15  crm_accounts.csv     Curtis Hartigan      last CRM touch on A1018  [418 days ago, nothing since]
```
