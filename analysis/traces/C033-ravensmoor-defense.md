# Ravensmoor Defense  (C033)

- stage: Negotiation | industry: Defense | owner: Hana Nakashima | deal value: $1,400,000 | largest request: $2,000,000
- CRM accounts: A1031 (ravensmoor.com)
- also goes by: nothing else
- 4 requests from 3 people wanting 4 different titles: Chief Data Officer | Chief Digital Officer | Head of Developer Productivity | VP Engineering

## 2. Where the files disagree

- R1109: filed "Closed - no path" but supply_reach.csv has 1 path into Ravensmoor Defense
- R1109: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 1 paths
- R1109: Owen Trask offered in slack_threads.jsonl on 2025-10-26 ("their Head of Platform reports to someone I've known for a decade, leave it with me") but intro_outcomes.csv never asked them
- R1039: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 1 paths
- R1005: filed "Closed - no path" but supply_reach.csv has 1 path into Ravensmoor Defense
- R1005: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 1 paths

## 3. Who can reach them

| strength | connector | reach | contact | evidence |
|---|---|---|---|---|
| 0.800 | Owen Trask (Investor) | offer | Head of Platform | slack_threads.jsonl R1109 2025-10-26 Owen Trask: "their Head of Platform reports to someone I've known for a decade, leave it with me" |

## 4. Chronology (17 events, 4 requests, as of 2026-09-06)

```
   2025-10-07  intro_requests.csv   Nadia Okonkwo        R1049 raised by Nadia Okonkwo (AE, Industrials): wants Chief Digital Officer, $750,000, Critical urgency, filed "Open"
   2025-10-07  slack_threads.jsonl  Nadia Okonkwo        R1049 slack: "long shot — Ravensmoor Defense. Rhys Ferreira-Ingleby (Chief Digital Officer). Anyone?"
   2025-10-07  slack_threads.jsonl  Rafael Salcedo       R1049 slack: "no idea sorry"
   2025-10-09  slack_threads.jsonl  Rafael Salcedo       R1049 slack: "adding Imani Mkhize who might know"
   2025-10-11  slack_threads.jsonl  Curtis Hartigan      R1049 slack: "wrong channel? this feels like a partner ask"

!! 2025-10-24  intro_requests.csv   Bertrand Vandermolen R1109 raised by Bertrand Vandermolen (AE, EMEA): wants VP Engineering, $150,000, Critical urgency, filed "Closed - no path"  [1 paths in supply_reach.csv]
   2025-10-24  slack_threads.jsonl  Bertrand Vandermolen R1109 slack: "need help getting to Ravensmoor Defense. Liesel Bellinger-Dellinger is the VP Engineering there, cold outbound is going nowhere"
   2025-10-24  slack_threads.jsonl  Rafael Salcedo       R1109 slack: "what's the deal size here?"
** 2025-10-26  slack_threads.jsonl  Owen Trask           R1109 slack: "their Head of Platform reports to someone I've known for a decade, leave it with me"  [never taken up]

   2026-01-29  intro_requests.csv   Nadia Okonkwo        R1039 raised by Nadia Okonkwo (AE, Industrials): wants Head of Developer Productivity, $2,000,000, High urgency, filed "Stalled"
   2026-01-29  slack_threads.jsonl  Nadia Okonkwo        R1039 slack: "asking again: Ravensmoor Defense. Head of Developer Productivity. Happy to draft the forward myself if someone can vouch."
   2026-01-31  slack_threads.jsonl  Imani Mkhize         R1039 slack: "no idea sorry"
   2026-01-31  slack_threads.jsonl  Bertrand Vandermolen R1039 slack: "did we not already lose this one?"
   2026-02-01  slack_threads.jsonl  Sloane Fairweather   R1039 slack: "no idea sorry"

!! 2026-03-05  intro_requests.csv   Rafael Salcedo       R1005 raised by Rafael Salcedo (AE, Transport & Logistics): wants Chief Data Officer, $150,000, Low urgency, filed "Closed - no path"  [1 paths in supply_reach.csv]
   2026-03-05  slack_threads.jsonl  Rafael Salcedo       R1005 slack: "need help getting to Ravensmoor Defense. Curtis Ashdown-Kirkbride is the Chief Data Officer there, cold outbound is going nowhere"

!! 2025-10-12  crm_accounts.csv     Hana Nakashima       last CRM touch on A1031  [329 days ago, nothing since]
```

## 5. Next steps, by person, cheapest first

| # | who | role | action | why | requests |
|---|---|---|---|---|---|
| 1 | Owen Trask | Angel investor / advisor (investor connector) | take them up on it; send the ask (batch 2026-09 Owen Trask) | offered on 2025-10-26 ("their Head of Platform reports to someone I've known for a decade, leave it with me") and was never asked — free, they already said yes; allocated in golden_allocation.csv via offer path, score 0.091; allocated in golden_allocation.csv via offer path, score 0.091 | R1109, R1039, R1049 |
| 2 | Hana Nakashima | CRM owner (A1031) | check in on the account | last touch 2025-10-12, 329 days ago | — |
| 3 | Nadia Okonkwo (334 days), Bertrand Vandermolen (317 days), Rafael Salcedo (185 days) | 3 reps still waiting, longest first | tell them it's with Owen Trask | 3 reps raised this and have heard nothing; the oldest has been waiting 334 days | R1049, R1039, R1109, R1005 |
