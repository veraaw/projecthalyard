# Meridian Holdings  (C025)

- stage: Evaluation | industry: Consumer | owner: Bertrand Vandermolen | deal value: $250,000 | largest request: $750,000
- CRM accounts: A1034 (meridianpeakfoods.com)
- also goes by: Meridian Peak Foods
- 2 requests from 2 people wanting 1 different title: VP Engineering

## 2. Where the files disagree

- R1172: filed "Intro sent" but intro_outcomes.csv has no intro (asked Priya Raghunathan, intro_sent=N)
- R1168: filed "Open" but intro_outcomes.csv says Priya Raghunathan sent the intro on 2026-08-04

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.178 | 0.415 | Dana Whitfield (Internal) | direct | Desmond Cardoso — Director of IT | connections_whitfield.csv: Desmond Cardoso, Director of IT at Meridian Peak Foods, connected 2022-03-01 |
| 0.097 | 0.472 | Priya Raghunathan (Investor) | direct | Dev Ingleby — Head of Platform Engineering | connections_raghunathan.csv: Dev Ingleby, Head of Platform Engineering at Meridian Peak Foods, connected 2024-11-02 |
| 0.039 | 0.346 | Owen Trask (Investor) | direct | Desmond Cardoso — Director of IT | connections_trask.csv: Desmond Cardoso, Director of IT at Meridian Peak Foods, connected 2019-10-24 |

## 4. Chronology (15 events, 2 requests, as of 2026-09-06)

```
!! 2025-10-21  intro_requests.csv   Hana Nakashima       R1172 raised by Hana Nakashima (AE, Healthcare): wants VP Engineering, $150,000, High urgency, filed "Intro sent"  [no intro in intro_outcomes.csv]
   2025-10-21  slack_threads.jsonl  Hana Nakashima       R1172 slack: "any connections into Meridian Peak Foods? we're up against a renewal window and I need an intro to VP Engineering"
   2025-10-21  intro_outcomes.csv   Priya Raghunathan    R1172 asked
<- 2026-09-06  intro_outcomes.csv   Priya Raghunathan    R1172 never replied (asked 2025-10-21, 320 days ago)

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

!! 2026-04-21  crm_accounts.csv     Bertrand Vandermolen last CRM touch on A1034  [138 days ago, nothing since]
```

## 5. Additional Investor and Operator Network

1 person from investor_network.csv, 1 with no warm path; read-only: not scored, not allocated, not on supply_reach.csv

| person | role | fund | board seat | source | warm path |
|---|---|---|---|---|---|
| Perrine Brenneman-Wexford | Private equity investor | Meridian Peak Partners | no | portfolio_company | no warm path |
