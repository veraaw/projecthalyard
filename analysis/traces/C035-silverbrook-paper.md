# Silverbrook Paper  (C035)

- stage: Closed Lost | industry: Materials | owner: Curtis Hartigan | Yusuf Petrossian | deal value: $600,000 | largest request: $2,000,000
- CRM accounts: A1032 | A91032 (silverbrookpaper.com) | duplicates: yes - owners disagree
- also goes by: Silverbrook Paper Corp
- 2 requests from 2 people wanting 2 different titles: Chief Operating Officer | Chief Technology Officer

## 2. Where the files disagree

- crm_accounts.csv: two accounts, two owners: A1032 -> Curtis Hartigan; A91032 -> Yusuf Petrossian

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.041 | 0.356 | Owen Trask (Investor) | direct | Elena Rushworth — Head of Automation | connections_trask.csv: Elena Rushworth, Head of Automation at Silverbrook Paper, connected 2019-11-27 |

strongest path, not where it went: Owen Trask, direct 0.356, at capacity 2/2; R1063 unrouted (capacity exhausted this cycle)

## 4. Chronology (12 events, 2 requests, newest first, as of 2026-09-06)

```
<- 2026-09-06  intro_outcomes.csv   Owen Trask           R1008 never replied (asked 2026-01-07, 242 days ago)
   2026-01-10  slack_threads.jsonl  Curtis Hartigan      R1008 slack: "what's the deal size here?"
   2026-01-08  slack_threads.jsonl  Curtis Hartigan      R1008 slack: "what's the deal size here?"
   2026-01-07  intro_outcomes.csv   Owen Trask           R1008 asked
   2026-01-07  slack_threads.jsonl  Yusuf Petrossian     R1008 slack: "trying to reach Chief Technology Officer at Silverbrook Paper — anyone have a path?"
   2026-01-07  intro_requests.csv   Yusuf Petrossian     R1008 raised by Yusuf Petrossian (SDR Lead): wants Chief Technology Officer, $2,000,000, High urgency, filed "Open"

   2025-11-10  slack_threads.jsonl  Hana Nakashima       R1063 slack: "is this the same as the one from last month?"
   2025-11-07  slack_threads.jsonl  Hana Nakashima       R1063 slack: "bumping this"
   2025-11-07  slack_threads.jsonl  Sloane Fairweather   R1063 slack: "I think their procurement is frozen until Q1"
   2025-11-06  slack_threads.jsonl  Sloane Fairweather   R1063 slack: "trying to reach Chief Operating Officer at Silverbrook Paper — anyone have a path?"
   2025-11-06  intro_requests.csv   Sloane Fairweather   R1063 raised by Sloane Fairweather (Strategic AE): wants Chief Operating Officer, $80,000, High urgency, filed "Routed"

!! 2026-05-10  crm_accounts.csv     Curtis Hartigan      last CRM touch on A1032  [119 days ago, nothing since]
```
