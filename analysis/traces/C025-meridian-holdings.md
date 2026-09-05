# Meridian Holdings  (C025)

- stage: Evaluation | industry: Consumer | owner: Bertrand Vandermolen | deal value: $250,000 | largest request: $750,000
- CRM accounts: A1034 (meridianpeakfoods.com)
- also goes by: Meridian Peak Foods
- 2 requests from 2 people wanting 1 different title: VP Engineering

## 2. Where the files disagree

- R1172: filed "Intro sent" but intro_outcomes.csv has no intro (asked Priya Raghunathan, intro_sent=N)
- R1168: filed "Open" but intro_outcomes.csv says Priya Raghunathan sent the intro on 2026-08-04

## 3. Who can reach them

| strength | connector | reach | contact | evidence |
|---|---|---|---|---|
| 0.472 | Priya Raghunathan (Investor) | direct | Dev Ingleby — Head of Platform Engineering | connections_raghunathan.csv: Dev Ingleby, Head of Platform Engineering at Meridian Peak Foods, connected 2024-11-02 |
| 0.415 | Dana Whitfield (Internal) | direct | Desmond Cardoso — Director of IT | connections_whitfield.csv: Desmond Cardoso, Director of IT at Meridian Peak Foods, connected 2022-03-01 |
| 0.346 | Owen Trask (Investor) | direct | Desmond Cardoso — Director of IT | connections_trask.csv: Desmond Cardoso, Director of IT at Meridian Peak Foods, connected 2019-10-24 |

## 4. Chronology (15 events, 2 requests, as of 2026-09-05)

```
!! 2025-10-21  intro_requests.csv   Hana Nakashima       R1172 raised by Hana Nakashima (AE, Healthcare): wants VP Engineering, $150,000, High urgency, filed "Intro sent"  [no intro in intro_outcomes.csv]
   2025-10-21  slack_threads.jsonl  Hana Nakashima       R1172 slack: "any connections into Meridian Peak Foods? we're up against a renewal window and I need an intro to VP Engineering"
   2025-10-21  intro_outcomes.csv   Priya Raghunathan    R1172 asked
<- 2026-09-05  intro_outcomes.csv   Priya Raghunathan    R1172 never replied (asked 2025-10-21, 319 days ago)

!! 2026-07-22  intro_requests.csv   Bertrand Vandermolen R1168 raised by Bertrand Vandermolen (AE, EMEA): wants VP Engineering, $750,000, Medium urgency, filed "Open"  [same title as R1172, 274 days earlier]
   2026-07-22  slack_threads.jsonl  Bertrand Vandermolen R1168 slack: "any connections into Meridian Peak Foods? we're up against a renewal window and I need an intro to VP Engineering"
   2026-07-23  intro_outcomes.csv   Priya Raghunathan    R1168 asked
   2026-07-24  slack_threads.jsonl  Rafael Salcedo       R1168 slack: "what's the deal size here?"
++ 2026-07-24  intro_outcomes.csv   Priya Raghunathan    R1168 replied (1 days after the ask)
   2026-07-26  slack_threads.jsonl  Hana Nakashima       R1168 slack: "bumping this"
   2026-07-26  slack_threads.jsonl  Nadia Okonkwo        R1168 slack: "bumping this"
++ 2026-08-04  intro_outcomes.csv   Priya Raghunathan    R1168 intro sent
++ 2026-08-04  intro_outcomes.csv   Priya Raghunathan    R1168 meeting booked
++ 2026-08-04  intro_outcomes.csv   Priya Raghunathan    R1168 opportunity created, $750,000

!! 2026-04-21  crm_accounts.csv     Bertrand Vandermolen last CRM touch on A1034  [137 days ago, nothing since]
```

## 5. Next steps, by person, cheapest first

| # | who | role | action | why | requests |
|---|---|---|---|---|---|
| 1 | Bertrand Vandermolen | CRM owner (A1034) | check in on the account | last touch 2026-04-21, 137 days ago | — |
| 2 | Hana Nakashima | 1 rep still waiting | tell them where it is | no intro logged on their request | R1172 |
