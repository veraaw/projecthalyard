# Duncastle Holdings  (C010)

- stage: Prospect | industry: Hospitality | owner: Bertrand Vandermolen | deal value: $600,000 | largest request: $750,000
- CRM accounts: A1029 (duncastle.com)
- also goes by: Duncastle Hotels | duncastle.com
- 5 requests from 4 people wanting 4 different titles: Chief Digital Officer | Chief Information Officer | SVP Digital | VP Enterprise Architecture

## 2. Where the files disagree

- R1032: filed "Closed - no path" but supply_reach.csv has 5 paths into Duncastle Holdings
- R1071: filed "Closed - no path" but supply_reach.csv has 5 paths into Duncastle Holdings

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key; investor_network rows take a 10% haircut on route score

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.215 | 0.900 | Amara Brenneman-Fairweather (investor network) | investor_network (board seat) | CEO / exec team — Redtree Capital board seat | investor_network.csv: Amara Brenneman-Fairweather (Growth equity investor), portfolio_company=Duncastle Hotels, board_seat=True |
| 0.215 | 0.900 | Matteo Falkenrath-Merriweather (investor network) | investor_network (board seat) | CEO / exec team — Cobalt Lane Ventures board seat | investor_network.csv: Matteo Falkenrath-Merriweather (Venture capital investor), portfolio_company=Duncastle Hotels, board_seat=True |
| 0.215 | 0.900 | Renata Halloran-Quillane (investor network) | investor_network (board seat) | CEO / exec team — Redtree Capital board seat | investor_network.csv: Renata Halloran-Quillane (Growth equity investor), portfolio_company=Duncastle Hotels, board_seat=True |
| 0.184 | 0.900 | Priya Raghunathan (Investor) | investor (board seat) | CEO / exec team — Redtree Capital board seat | investor_network.csv: Priya Raghunathan (Partner, Redtree Capital), portfolio_company=Duncastle Hotels, board_seat=True |
| 0.172 | 0.720 | Matteo Ferreira-Yarrow (investor network) | investor_network | CEO / exec team — Ironvale Partners portfolio company | investor_network.csv: Matteo Ferreira-Yarrow (Private equity investor), portfolio_company=Duncastle Hotels, board_seat=False |

## 4. Chronology (27 events, 5 requests, newest first, as of 2026-09-06)

```
<- 2026-09-06  intro_outcomes.csv   Priya Raghunathan    R1120 never replied (asked 2025-10-30, 311 days ago)
   2025-11-01  slack_threads.jsonl  Sloane Fairweather   R1120 slack: "did we not already lose this one?"
   2025-10-30  intro_outcomes.csv   Priya Raghunathan    R1120 asked
   2025-10-28  slack_threads.jsonl  Yusuf Petrossian     R1120 slack: "asking again: Duncastle Hotels. Chief Information Officer. Happy to draft the forward myself if someone can vouch."
!! 2025-10-28  intro_requests.csv   Yusuf Petrossian     R1120 raised by Yusuf Petrossian (SDR Lead): wants Chief Information Officer, $80,000, High urgency, filed "Stalled"  [same title as R1082, 87 days earlier]

<- 2026-09-06  intro_outcomes.csv   Priya Raghunathan    R1082 said yes 385 days ago and never forwarded
++ 2025-08-17  intro_outcomes.csv   Priya Raghunathan    R1082 replied (12 days after the ask)
   2025-08-05  intro_outcomes.csv   Priya Raghunathan    R1082 asked
   2025-08-04  slack_threads.jsonl  Rafael Salcedo       R1082 slack: "bumping this"
   2025-08-04  slack_threads.jsonl  Yusuf Petrossian     R1082 slack: "is this the same as the one from last month?"
   2025-08-02  slack_threads.jsonl  Bertrand Vandermolen R1082 slack: "is this the same as the one from last month?"
   2025-08-02  slack_threads.jsonl  Sloane Fairweather   R1082 slack: "trying to reach Chief Information Officer at Duncastle Hotels. I know we sell into Wrenfield Robotics and Yarrowdale Media — could either of those relationships get us there?"
   2025-08-02  intro_requests.csv   Sloane Fairweather   R1082 raised by Sloane Fairweather (Strategic AE): wants Chief Information Officer, $400,000, Medium urgency, filed "Stalled"

   2026-05-03  slack_threads.jsonl  Rafael Salcedo       R1183 slack: "I think their procurement is frozen until Q1"
   2026-04-29  slack_threads.jsonl  Yusuf Petrossian     R1183 slack: "looking for a path to Leandro Okonkwo-Oldfield — email domain is duncastle.com, that's all I have"
   2026-04-29  intro_requests.csv   Yusuf Petrossian     R1183 raised by Yusuf Petrossian (SDR Lead): wants SVP Digital, $750,000, High urgency, filed "Open"

   2026-01-29  slack_threads.jsonl  Curtis Hartigan      R1071 slack: "trying to reach Chief Digital Officer at Duncastle Hotels. I know we sell into Blackwood Industrial and Ellerby Semiconductor — could either of those relationships get us there?"
!! 2026-01-29  intro_requests.csv   Curtis Hartigan      R1071 raised by Curtis Hartigan (AE, Financial Services): wants Chief Digital Officer, $400,000, Critical urgency, filed "Closed - no path"  [5 paths in supply_reach.csv]

++ 2025-09-30  intro_outcomes.csv   Priya Raghunathan    R1032 intro sent
++ 2025-09-27  intro_outcomes.csv   Priya Raghunathan    R1032 replied (10 days after the ask)
   2025-09-17  intro_outcomes.csv   Priya Raghunathan    R1032 asked
   2025-09-15  slack_threads.jsonl  Yusuf Petrossian     R1032 slack: "I think their procurement is frozen until Q1"
   2025-09-11  slack_threads.jsonl  Bertrand Vandermolen R1032 slack: "wrong channel? this feels like a partner ask"
   2025-09-11  slack_threads.jsonl  Curtis Hartigan      R1032 slack: "bumping this"
   2025-09-11  slack_threads.jsonl  Hana Nakashima       R1032 slack: "who do we know at Duncastle Hotels? VP Enterprise Architecture would be ideal but I'll take anyone senior"
!! 2025-09-11  intro_requests.csv   Hana Nakashima       R1032 raised by Hana Nakashima (AE, Healthcare): wants VP Enterprise Architecture, $80,000, Critical urgency, filed "Closed - no path"  [5 paths in supply_reach.csv]

!! 2025-12-07  crm_accounts.csv     Bertrand Vandermolen last CRM touch on A1029  [273 days ago, nothing since]
```

## 5. Additional Investor and Operator Network

5 people from investor_network.csv, 4 askable as investor_network paths, 0 with no warm path; a view of section 3 and the roster's exports, nothing here is scored or allocated on its own

| person | role | fund | board seat | source | warm path |
|---|---|---|---|---|---|
| Amara Brenneman-Fairweather | Growth equity investor | Redtree Capital | yes | portfolio_company | investor_network path (section 3, 10% haircut) |
| Matteo Falkenrath-Merriweather | Venture capital investor | Cobalt Lane Ventures | yes | portfolio_company | investor_network path (section 3, 10% haircut) |
| Priya Raghunathan | Partner, Redtree Capital | Redtree Capital | yes | portfolio_company | on the roster |
| Renata Halloran-Quillane | Growth equity investor | Redtree Capital | yes | portfolio_company | investor_network path (section 3, 10% haircut) |
| Matteo Ferreira-Yarrow | Private equity investor | Ironvale Partners | no | portfolio_company | investor_network path (section 3, 10% haircut) |
