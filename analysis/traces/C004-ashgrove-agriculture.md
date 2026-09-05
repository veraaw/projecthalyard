# Ashgrove Agriculture  (C004)

- stage: Pilot | industry: Agriculture | owner: Hana Nakashima | Rafael Salcedo | deal value: $600,000 | largest request: $400,000
- CRM accounts: A1035 | A91035 (ashgroveag.com) | duplicates: yes - owners disagree
- also goes by: Ashgrove Agriculture Inc
- 1 request from 1 person wanting 1 different title: Chief Digital Officer

## 2. Where the files disagree

- crm_accounts.csv: two accounts, two owners: A1035 -> Hana Nakashima; A91035 -> Rafael Salcedo
- R1187: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 1 paths

## 3. Who can reach them

| strength | connector | reach | contact | evidence |
|---|---|---|---|---|
| 0.800 | Priya Raghunathan (Investor) | offer | Kwame Marchetti-Drummond | slack_threads.jsonl R1187 2025-10-29 Priya Raghunathan: "I know Kwame Marchetti-Drummond there well, happy to intro" |

## 4. Chronology (10 events, 1 request, as of 2026-09-05)

```
   2025-10-29  intro_requests.csv   Bertrand Vandermolen R1187 raised by Bertrand Vandermolen (AE, EMEA): wants Chief Digital Officer, $400,000, Critical urgency, filed "Open"
   2025-10-29  slack_threads.jsonl  Bertrand Vandermolen R1187 slack: "who do we know at Ashgrove Agriculture? Chief Digital Officer would be ideal but I'll take anyone senior"
** 2025-10-29  slack_threads.jsonl  Priya Raghunathan    R1187 slack: "I know Kwame Marchetti-Drummond there well, happy to intro"
   2025-11-01  slack_threads.jsonl  Rafael Salcedo       R1187 slack: "what's the deal size here?"
   2025-11-01  intro_outcomes.csv   Priya Raghunathan    R1187 asked
   2025-11-02  slack_threads.jsonl  Rafael Salcedo       R1187 slack: "did we not already lose this one?"
   2025-11-02  slack_threads.jsonl  Yusuf Petrossian     R1187 slack: "did we not already lose this one?"
++ 2025-11-03  intro_outcomes.csv   Priya Raghunathan    R1187 replied (2 days after the ask)
<- 2026-09-05  intro_outcomes.csv   Priya Raghunathan    R1187 said yes 306 days ago and never forwarded

!! 2026-01-31  crm_accounts.csv     Hana Nakashima       last CRM touch on A1035  [217 days ago, nothing since]
```

## 5. Next steps, by person, cheapest first

| # | who | role | action | why | requests |
|---|---|---|---|---|---|
| 1 | Priya Raghunathan | Partner, Redtree Capital (investor connector) | nudge, don't re-ask | said yes on 2025-11-03 and never forwarded | R1187 |
| 2 | Hana Nakashima | CRM owner (A1035) | check in on the account | last touch 2026-01-31, 217 days ago | — |
| 3 | Bertrand Vandermolen (311 days) | 1 rep still waiting, longest first | tell them it's with Priya Raghunathan | 1 rep raised this and has heard nothing; the oldest has been waiting 311 days | R1187 |
