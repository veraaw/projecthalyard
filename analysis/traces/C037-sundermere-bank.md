# Sundermere Bank  (C037)

- stage: Pilot | industry: Financial Services | owner: Imani Mkhize | deal value: $600,000 | largest request: $400,000
- CRM accounts: A1014 (sundermere.com)
- also goes by: nothing else
- 1 request from 1 person wanting 1 different title: Chief Data Officer

## 2. Where the files disagree

- R1034: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 1 paths
- R1034: Nadia Okonkwo offered in slack_threads.jsonl on 2025-10-13 ("their Head of Platform reports to someone I've known for a decade, leave it with me") but intro_outcomes.csv never asked them

## 3. Who can reach them

| strength | connector | reach | contact | evidence |
|---|---|---|---|---|
| 0.800 | Nadia Okonkwo (not on roster) | offer | Head of Platform | slack_threads.jsonl R1034 2025-10-13 Nadia Okonkwo: "their Head of Platform reports to someone I've known for a decade, leave it with me" |

## 4. Chronology (6 events, 1 request, as of 2026-09-05)

```
   2025-10-13  intro_requests.csv   Sloane Fairweather   R1034 raised by Sloane Fairweather (Strategic AE): wants Chief Data Officer, $400,000, High urgency, filed "Open"
   2025-10-13  slack_threads.jsonl  Sloane Fairweather   R1034 slack: "long shot — Sundermere Bank. Margot Vasquez-Salcedo (Chief Data Officer). Anyone?"
** 2025-10-13  slack_threads.jsonl  Nadia Okonkwo        R1034 slack: "their Head of Platform reports to someone I've known for a decade, leave it with me"  [never taken up]
   2025-10-16  slack_threads.jsonl  Imani Mkhize         R1034 slack: "did we not already lose this one?"
   2025-10-17  slack_threads.jsonl  Nadia Okonkwo        R1034 slack: "adding Nadia Okonkwo who might know"

!! 2026-06-04  crm_accounts.csv     Imani Mkhize         last CRM touch on A1014  [93 days ago, nothing since]
```

## 5. Next steps, by person, cheapest first

| # | who | role | action | why | requests |
|---|---|---|---|---|---|
| 1 | Nadia Okonkwo | off-roster connector | take them up on it; send the ask (batch 2026-09 Nadia Okonkwo) | offered on 2025-10-13 ("their Head of Platform reports to someone I've known for a decade, leave it with me") and was never asked — free, they already said yes; allocated in golden_allocation.csv via offer path, score 0.213 | R1034 |
| 2 | Imani Mkhize | CRM owner (A1014) | check in on the account | last touch 2026-06-04, 93 days ago | — |
| 3 | Sloane Fairweather (327 days) | 1 rep still waiting, longest first | tell them it's with Nadia Okonkwo | 1 rep raised this and has heard nothing; the oldest has been waiting 327 days | R1034 |
