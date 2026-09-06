# Duncastle Holdings  (C010)

- stage: Prospect | industry: Hospitality | owner: Bertrand Vandermolen | deal value: $600,000 | largest request: $750,000
- CRM accounts: A1029 (duncastle.com)
- also goes by: Duncastle Hotels | duncastle.com
- 5 requests from 4 people wanting 4 different titles: Chief Digital Officer | Chief Information Officer | SVP Digital | VP Enterprise Architecture

## 2. Where the files disagree

- R1032: filed "Closed - no path" but supply_reach.csv has 1 path into Duncastle Holdings
- R1071: filed "Closed - no path" but supply_reach.csv has 1 path into Duncastle Holdings

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.184 | 0.900 | Priya Raghunathan (Investor) | investor (board seat) | CEO / exec team — Redtree Capital board seat | investor_network.csv: Priya Raghunathan (Partner, Redtree Capital), portfolio_company=Duncastle Hotels, board_seat=True |

strongest path, not where it went: Priya Raghunathan, investor 0.900, at capacity 3/3; R1183 unrouted (capacity exhausted this cycle)

## 4. Chronology (27 events, 5 requests, as of 2026-09-06)

```
   2025-08-02  intro_requests.csv   Sloane Fairweather   R1082 raised by Sloane Fairweather (Strategic AE): wants Chief Information Officer, $400,000, Medium urgency, filed "Stalled"
   2025-08-02  slack_threads.jsonl  Sloane Fairweather   R1082 slack: "trying to reach Chief Information Officer at Duncastle Hotels. I know we sell into Wrenfield Robotics and Yarrowdale Media — could either of those relationships get us there?"
   2025-08-02  slack_threads.jsonl  Bertrand Vandermolen R1082 slack: "is this the same as the one from last month?"
   2025-08-04  slack_threads.jsonl  Yusuf Petrossian     R1082 slack: "is this the same as the one from last month?"
   2025-08-04  slack_threads.jsonl  Rafael Salcedo       R1082 slack: "bumping this"
   2025-08-05  intro_outcomes.csv   Priya Raghunathan    R1082 asked
++ 2025-08-17  intro_outcomes.csv   Priya Raghunathan    R1082 replied (12 days after the ask)
<- 2026-09-06  intro_outcomes.csv   Priya Raghunathan    R1082 said yes 385 days ago and never forwarded

!! 2025-09-11  intro_requests.csv   Hana Nakashima       R1032 raised by Hana Nakashima (AE, Healthcare): wants VP Enterprise Architecture, $80,000, Critical urgency, filed "Closed - no path"  [1 paths in supply_reach.csv]
   2025-09-11  slack_threads.jsonl  Hana Nakashima       R1032 slack: "who do we know at Duncastle Hotels? VP Enterprise Architecture would be ideal but I'll take anyone senior"
   2025-09-11  slack_threads.jsonl  Curtis Hartigan      R1032 slack: "bumping this"
   2025-09-11  slack_threads.jsonl  Bertrand Vandermolen R1032 slack: "wrong channel? this feels like a partner ask"
   2025-09-15  slack_threads.jsonl  Yusuf Petrossian     R1032 slack: "I think their procurement is frozen until Q1"
   2025-09-17  intro_outcomes.csv   Priya Raghunathan    R1032 asked
++ 2025-09-27  intro_outcomes.csv   Priya Raghunathan    R1032 replied (10 days after the ask)
++ 2025-09-30  intro_outcomes.csv   Priya Raghunathan    R1032 intro sent

!! 2025-10-28  intro_requests.csv   Yusuf Petrossian     R1120 raised by Yusuf Petrossian (SDR Lead): wants Chief Information Officer, $80,000, High urgency, filed "Stalled"  [same title as R1082, 87 days earlier]
   2025-10-28  slack_threads.jsonl  Yusuf Petrossian     R1120 slack: "asking again: Duncastle Hotels. Chief Information Officer. Happy to draft the forward myself if someone can vouch."
   2025-10-30  intro_outcomes.csv   Priya Raghunathan    R1120 asked
   2025-11-01  slack_threads.jsonl  Sloane Fairweather   R1120 slack: "did we not already lose this one?"
<- 2026-09-06  intro_outcomes.csv   Priya Raghunathan    R1120 never replied (asked 2025-10-30, 311 days ago)

!! 2026-01-29  intro_requests.csv   Curtis Hartigan      R1071 raised by Curtis Hartigan (AE, Financial Services): wants Chief Digital Officer, $400,000, Critical urgency, filed "Closed - no path"  [1 paths in supply_reach.csv]
   2026-01-29  slack_threads.jsonl  Curtis Hartigan      R1071 slack: "trying to reach Chief Digital Officer at Duncastle Hotels. I know we sell into Blackwood Industrial and Ellerby Semiconductor — could either of those relationships get us there?"

   2026-04-29  intro_requests.csv   Yusuf Petrossian     R1183 raised by Yusuf Petrossian (SDR Lead): wants SVP Digital, $750,000, High urgency, filed "Open"
   2026-04-29  slack_threads.jsonl  Yusuf Petrossian     R1183 slack: "looking for a path to Leandro Okonkwo-Oldfield — email domain is duncastle.com, that's all I have"
   2026-05-03  slack_threads.jsonl  Rafael Salcedo       R1183 slack: "I think their procurement is frozen until Q1"

!! 2025-12-07  crm_accounts.csv     Bertrand Vandermolen last CRM touch on A1029  [273 days ago, nothing since]
```

## 5. Next steps, by person, cheapest first

| # | who | role | action | why | requests |
|---|---|---|---|---|---|
| 1 | Priya Raghunathan | Partner, Redtree Capital (investor connector) | nudge, don't re-ask | said yes on 2025-08-17 and never forwarded | R1082 |
| 2 | Bertrand Vandermolen | CRM owner (A1029) | check in on the account | last touch 2025-12-07, 273 days ago | — |
| 3 | Sloane Fairweather (400 days), Yusuf Petrossian (313 days), Curtis Hartigan (220 days) | 3 reps still waiting, longest first | tell them it's with Priya Raghunathan | 3 reps raised this and have heard nothing; the oldest has been waiting 400 days | R1082, R1120, R1183, R1071 |
| 4 | Hana Nakashima | AE, Healthcare, was introduced | no action: intro already made | Priya Raghunathan introduced VP Enterprise Architecture on 2025-09-30 (R1032) and no meeting followed in 341 days, so the allocator treats the company as a retry; nothing is allocated this cycle | R1032 |
