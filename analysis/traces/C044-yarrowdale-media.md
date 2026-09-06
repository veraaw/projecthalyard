# Yarrowdale Media  (C044)

- stage: Evaluation | industry: Media | owner: Rafael Salcedo | deal value: $1,400,000 (CRM ARR potential) | by request: R1169 $150,000
- CRM accounts: A1028 (yarrowdale.com)
- also goes by: nothing else
- 1 request from 1 person wanting 1 different title: VP Data & Analytics

## 2. Where the files disagree

- R1169: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 4 paths

## Currently routing to: Tomás Beckett

- the next request goes to the top askable path: Tomás Beckett, direct via Bertrand Cardoso, route score 0.164, 3/8 capacity used this cycle
- not asked again here: Bertrand Vandermolen asked on 2026-07-12 (R1169), no reply - day 56 of 60

## 3. Who can reach them

in the allocator's order: the tiers below, then route score = strength x focus fit x delivery rate within each; investor_network rows rank below every roster path and take a 10% haircut on route score

**roster - asked first** (2 paths)

| route score | strength | connector | reach | contact | evidence | unresolved ask |
|---|---|---|---|---|---|---|
| 0.164 | 0.460 | Tomás Beckett (Internal) | direct | Bertrand Cardoso — Director of IT | connections_beckett.csv: Bertrand Cardoso, Director of IT at Yarrowdale Media, connected 2024-10-15 |  |
| 0.085 | 0.415 | Priya Raghunathan (Investor) | direct | Bertrand Cardoso — Director of IT | connections_raghunathan.csv: Bertrand Cardoso, Director of IT at Yarrowdale Media, connected 2022-11-15 |  |

**investor_network - asked when no roster path is left** (1 path)

| route score | strength | connector | reach | contact | evidence | unresolved ask |
|---|---|---|---|---|---|---|
| 0.215 | 0.900 | Hugo Fairweather-Højgaard (investor network) | investor_network (board seat) | CEO / exec team — Northgate Growth board seat | investor_network.csv: Hugo Fairweather-Højgaard (Growth equity investor), portfolio_company=Yarrowdale Media, board_seat=True |  |

**not asked again here - an unresolved ask (nudge or chase) owns it** (1 path)

| route score | strength | connector | reach | contact | evidence | unresolved ask |
|---|---|---|---|---|---|---|
| 0.182 | 0.800 | Bertrand Vandermolen (not on roster) | offer | Chief Information Officer | slack_threads.jsonl R1169 2026-07-10 Bertrand Vandermolen: "I met their Chief Information Officer at a conference last spring, happy to reach out" | Bertrand Vandermolen asked on 2026-07-12 (R1169), no reply - day 56 of 60 |

## 4. Chronology (6 events, 1 request, newest first, as of 2026-09-06)

```
<- 2026-09-06  intro_outcomes.csv   Bertrand Vandermolen R1169 never replied (asked 2026-07-12, 56 days ago)
   2026-07-12  intro_outcomes.csv   Bertrand Vandermolen R1169 asked
** 2026-07-10  slack_threads.jsonl  Bertrand Vandermolen R1169 slack: "I met their Chief Information Officer at a conference last spring, happy to reach out"
   2026-07-10  slack_threads.jsonl  Curtis Hartigan      R1169 slack: "long shot — Yarrowdale Media. Tanvi Thackeray-Wolstenholme (VP Data & Analytics). Anyone?"
   2026-07-10  intro_requests.csv   Curtis Hartigan      R1169 raised by Curtis Hartigan (AE, Financial Services): wants VP Data & Analytics, $150,000, High urgency, filed "Stalled"

   2026-07-28  crm_accounts.csv     Rafael Salcedo       last CRM touch on A1028
```

## 5. Additional Investor and Operator Network

1 person from investor_network.csv, 1 askable as investor_network paths, 0 with no warm path; a view of section 3 and the roster's exports, nothing here is scored or allocated on its own

| person | role | fund | board seat | source | warm path |
|---|---|---|---|---|---|
| Hugo Fairweather-Højgaard | Growth equity investor | Northgate Growth | yes | portfolio_company | investor_network path (section 3, 10% haircut) |
