# Hollowbrook Grocers  (C019)

- stage: Pilot | industry: Retail | owner: Imani Mkhize | Nadia Okonkwo | deal value: $600,000 (CRM ARR potential) | by request: R1084 $2,000,000, R1065 $80,000, R1159 $1,200,000, R1124 $1,200,000
- CRM accounts: A1024 | A91024 (hollowbrook.com) | duplicates: yes - owners disagree
- also goes by: Hollowbrook Grocers Inc.
- 4 requests from 2 people wanting 3 different titles: Director of Software Engineering | VP Engineering | VP Enterprise Architecture

## 2. Where the files disagree

- crm_accounts.csv: two accounts, two owners: A1024 -> Nadia Okonkwo; A91024 -> Imani Mkhize
- R1124: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 6 paths

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key; investor_network rows rank below every roster path and take a 10% haircut on route score

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.184 | 0.900 | Priya Raghunathan (Investor) | investor (board seat) | CEO / exec team — Redtree Capital board seat | investor_network.csv: Priya Raghunathan (Partner, Redtree Capital), portfolio_company=Hollowbrook Grocers, board_seat=True |
| 0.164 | 0.800 | Priya Raghunathan (Investor) | offer | Chief Operating Officer | slack_threads.jsonl R1124 2025-11-10 Priya Raghunathan: "I met their Chief Operating Officer at a conference last spring, happy to reach out" |
| 0.128 | 0.300 | Dana Whitfield (Internal) | direct | Freya Havercamp — Staff Engineer | connections_whitfield.csv: Freya Havercamp, Staff Engineer at Hollowbrook Grocers, connected 2020-12-25 |
| 0.069 | 0.337 | Priya Raghunathan (Investor) | direct | Freya Havercamp — Staff Engineer | connections_raghunathan.csv: Freya Havercamp, Staff Engineer at Hollowbrook Grocers, connected 2022-05-16 |
| 0.172 | 0.720 | Arjun Fairweather-Brenneman (investor network) | investor_network | CEO / exec team — Redtree Capital portfolio company | investor_network.csv: Arjun Fairweather-Brenneman (Growth equity investor), portfolio_company=Hollowbrook Grocers, board_seat=False |
| 0.172 | 0.720 | Priya Dobrescu-Prendergast (investor network) | investor_network | CEO / exec team — Thornbury Equity portfolio company | investor_network.csv: Priya Dobrescu-Prendergast (Private equity investor), portfolio_company=Hollowbrook Grocers, board_seat=False |

why not #1: Priya Raghunathan at capacity 3/3 (holds R1084, R1159) -> R1065 to Dana Whitfield

## 4. Chronology (18 events, 4 requests, newest first, as of 2026-09-06)

```
<- 2026-09-06  intro_outcomes.csv   Priya Raghunathan    R1124 never replied (asked 2025-11-13, 297 days ago)
   2025-11-13  intro_outcomes.csv   Priya Raghunathan    R1124 asked
** 2025-11-10  slack_threads.jsonl  Priya Raghunathan    R1124 slack: "I met their Chief Operating Officer at a conference last spring, happy to reach out"
   2025-11-10  slack_threads.jsonl  Yusuf Petrossian     R1124 slack: "need help getting to Hollowbrook Grocers. Anouk Halloran-Lindqvist is the VP Engineering there, cold outbound is going nowhere"
   2025-11-10  intro_requests.csv   Yusuf Petrossian     R1124 raised by Yusuf Petrossian (SDR Lead): wants VP Engineering, $1,200,000, High urgency, filed "Open"

   2026-07-17  slack_threads.jsonl  Curtis Hartigan      R1084 slack: "no idea sorry"
   2026-07-16  slack_threads.jsonl  Nadia Okonkwo        R1084 slack: "is this the same as the one from last month?"
   2026-07-13  slack_threads.jsonl  Nadia Okonkwo        R1084 slack: "adding Hana Nakashima who might know"
   2026-07-13  slack_threads.jsonl  Bertrand Vandermolen R1084 slack: "need help getting to Hollowbrook Grocers. Dev Prendergast-Jarrold is the VP Engineering there, cold outbound is going nowhere"
!! 2026-07-13  intro_requests.csv   Bertrand Vandermolen R1084 raised by Bertrand Vandermolen (AE, EMEA): wants VP Engineering, $2,000,000, Critical urgency, filed "Open"  [same title as R1124, 245 days earlier]

   2026-04-11  slack_threads.jsonl  Hana Nakashima       R1065 slack: "no idea sorry"
   2026-04-08  slack_threads.jsonl  Bertrand Vandermolen R1065 slack: "Volney Industrial Systems introduced us to Halcyon Grid, but the account I actually need is Hollowbrook Grocers (Director of Software Engineering)."
   2026-04-08  intro_requests.csv   Bertrand Vandermolen R1065 raised by Bertrand Vandermolen (AE, EMEA): wants Director of Software Engineering, $80,000, High urgency, filed "Stalled"

   2025-12-13  slack_threads.jsonl  Yusuf Petrossian     R1159 slack: "did we not already lose this one?"
   2025-12-11  slack_threads.jsonl  Sloane Fairweather   R1159 slack: "I think their procurement is frozen until Q1"
   2025-12-11  slack_threads.jsonl  Bertrand Vandermolen R1159 slack: "Glasspoint Health introduced us to Pelham Beverage, but the account I actually need is Hollowbrook Grocers (VP Enterprise Architecture)."
   2025-12-11  intro_requests.csv   Bertrand Vandermolen R1159 raised by Bertrand Vandermolen (AE, EMEA): wants VP Enterprise Architecture, $1,200,000, Critical urgency, filed "Open"

!! 2026-05-16  crm_accounts.csv     Nadia Okonkwo        last CRM touch on A1024  [113 days ago, nothing since]
```

## 5. Additional Investor and Operator Network

3 people from investor_network.csv, 2 askable as investor_network paths, 0 with no warm path; a view of section 3 and the roster's exports, nothing here is scored or allocated on its own

| person | role | fund | board seat | source | warm path |
|---|---|---|---|---|---|
| Priya Raghunathan | Partner, Redtree Capital | Redtree Capital | yes | portfolio_company | on the roster |
| Arjun Fairweather-Brenneman | Growth equity investor | Redtree Capital | no | portfolio_company | investor_network path (section 3, 10% haircut) |
| Priya Dobrescu-Prendergast | Private equity investor | Thornbury Equity | no | portfolio_company | investor_network path (section 3, 10% haircut) |
