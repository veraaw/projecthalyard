# Sundermere Bank  (C037)

- stage: Pilot | industry: Financial Services | owner: Imani Mkhize | deal value: $600,000 | largest request: $400,000
- CRM accounts: A1014 (sundermere.com)
- also goes by: nothing else
- 1 request from 1 person wanting 1 different title: Chief Data Officer

## 2. Where the files disagree

- R1034: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 1 paths
- R1034: Nadia Okonkwo offered in slack_threads.jsonl on 2025-10-13 ("their Head of Platform reports to someone I've known for a decade, leave it with me") but intro_outcomes.csv never asked them

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.213 | 0.800 | Nadia Okonkwo (not on roster) | offer | Head of Platform | slack_threads.jsonl R1034 2025-10-13 Nadia Okonkwo: "their Head of Platform reports to someone I've known for a decade, leave it with me" |

## 4. Chronology (6 events, 1 request, newest first, as of 2026-09-06)

```
   2025-10-17  slack_threads.jsonl  Nadia Okonkwo        R1034 slack: "adding Nadia Okonkwo who might know"
   2025-10-16  slack_threads.jsonl  Imani Mkhize         R1034 slack: "did we not already lose this one?"
** 2025-10-13  slack_threads.jsonl  Nadia Okonkwo        R1034 slack: "their Head of Platform reports to someone I've known for a decade, leave it with me"  [never taken up]
   2025-10-13  slack_threads.jsonl  Sloane Fairweather   R1034 slack: "long shot — Sundermere Bank. Margot Vasquez-Salcedo (Chief Data Officer). Anyone?"
   2025-10-13  intro_requests.csv   Sloane Fairweather   R1034 raised by Sloane Fairweather (Strategic AE): wants Chief Data Officer, $400,000, High urgency, filed "Open"

!! 2026-06-04  crm_accounts.csv     Imani Mkhize         last CRM touch on A1014  [94 days ago, nothing since]
```
