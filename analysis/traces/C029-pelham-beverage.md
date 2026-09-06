# Pelham Beverage  (C029)

- stage: Evaluation | industry: Consumer | owner: Yusuf Petrossian | deal value: $3,500,000 (CRM ARR potential) | by request: R1176 $400,000, R1200 $750,000, R1047 $250,000
- CRM accounts: A1043 (pelhambev.com)
- also goes by: nothing else
- 3 requests from 3 people wanting 2 different titles: Director of Software Engineering | Head of Platform Engineering

## 2. Where the files disagree

- R1176: filed "Stalled" but intro_outcomes.csv says Imani Mkhize sent the intro on 2026-04-19
- R1176: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 1 paths

## Currently routing to: Imani Mkhize

- this cycle: R1047, R1200 unrouted (already introduced)
- the next request goes to the top askable path: Imani Mkhize, offer via ?, route score 0.262, 0/2 capacity used this cycle

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence | unresolved ask |
|---|---|---|---|---|---|---|
| 0.262 | 0.800 | Imani Mkhize (not on roster) | offer | Head of Platform | slack_threads.jsonl R1176 2026-04-05 Imani Mkhize: "their Head of Platform reports to someone I've known for a decade, leave it with me" |  |

strongest path, not where it went: Imani Mkhize, offer 0.800, 0/2 used this cycle; R1047 unrouted (already introduced: Imani Mkhize on 2026-04-19 (R1176, meeting booked)), R1200 unrouted (already introduced: Imani Mkhize on 2026-04-19 (R1176, meeting booked))

## 4. Chronology (17 events, 3 requests, newest first, as of 2026-09-06)

```
++ 2026-04-19  intro_outcomes.csv   Imani Mkhize         R1176 opportunity created, $400,000
++ 2026-04-19  intro_outcomes.csv   Imani Mkhize         R1176 meeting booked
++ 2026-04-19  intro_outcomes.csv   Imani Mkhize         R1176 intro sent
++ 2026-04-14  intro_outcomes.csv   Imani Mkhize         R1176 replied (11 days after the ask)
   2026-04-05  slack_threads.jsonl  Hana Nakashima       R1176 slack: "wrong channel? this feels like a partner ask"
** 2026-04-05  slack_threads.jsonl  Imani Mkhize         R1176 slack: "their Head of Platform reports to someone I've known for a decade, leave it with me"
   2026-04-03  intro_outcomes.csv   Imani Mkhize         R1176 asked
   2026-04-03  slack_threads.jsonl  Yusuf Petrossian     R1176 slack: "does anyone know anyone at Pelham Beverage? looking for Head of Platform Engineering, ideally warm"
   2026-04-03  intro_requests.csv   Yusuf Petrossian     R1176 raised by Yusuf Petrossian (SDR Lead): wants Head of Platform Engineering, $400,000, Critical urgency, filed "Stalled"

   2026-02-15  slack_threads.jsonl  Imani Mkhize         R1200 slack: "wrong channel? this feels like a partner ask"
   2026-02-15  slack_threads.jsonl  Hana Nakashima       R1200 slack: "Pelham Beverage is the target. Our champion at Northwind Freight used to work with their team, and I think Apex Logistics is a supplier of theirs. Any path?"
!! 2026-02-15  intro_requests.csv   Hana Nakashima       R1200 raised by Hana Nakashima (AE, Healthcare): wants Director of Software Engineering, $750,000, Medium urgency, filed "Open"  [same title as R1047, 182 days earlier]

   2025-08-21  slack_threads.jsonl  Sloane Fairweather   R1047 slack: "I think their procurement is frozen until Q1"
   2025-08-21  slack_threads.jsonl  Bertrand Vandermolen R1047 slack: "bumping this"
   2025-08-17  slack_threads.jsonl  Rafael Salcedo       R1047 slack: "Calderon Aerospace introduced us to Kestrel Airlines, but the account I actually need is Pelham Beverage (Director of Software Engineering)."
   2025-08-17  intro_requests.csv   Rafael Salcedo       R1047 raised by Rafael Salcedo (AE, Transport & Logistics): wants Director of Software Engineering, $250,000, High urgency, filed "Stalled"

!! 2026-01-20  crm_accounts.csv     Yusuf Petrossian     last CRM touch on A1043  [229 days ago, nothing since]
```
