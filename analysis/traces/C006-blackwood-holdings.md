# Blackwood Holdings  (C006)

- stage: Negotiation | industry: Industrials | owner: Imani Mkhize | deal value: $400,000 (CRM ARR potential) | by request: R1022 $1,200,000, R1091 $150,000, R1130 $80,000, R1179 $250,000
- CRM accounts: A1010 (blackwoodindustrial.com)
- also goes by: Blackwood Industrial
- 4 requests from 3 people wanting 3 different titles: Chief Digital Officer | Director of Software Engineering | SVP Digital

## 2. Where the files disagree

- R1022: filed "Open" but intro_outcomes.csv says Elena Duvall sent the intro on 2026-06-20
- R1091: filed "Stalled" but intro_outcomes.csv says Elena Duvall sent the intro on 2026-05-02
- R1130: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 9 paths

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key; investor_network rows rank below every roster path and take a 10% haircut on route score

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.187 | 0.519 | Elena Duvall (Advisor) | direct | Bram Quillane — Head of Developer Productivity | connections_duvall.csv: Bram Quillane, Head of Developer Productivity at Blackwood Industrial, connected 2028-06-16 |
| 0.180 | 0.519 | Marcus Aldridge (Advisor) | direct | Bram Quillane — Head of Developer Productivity | connections_aldridge.csv: Bram Quillane, Head of Developer Productivity at Blackwood Industrial, connected 2026-11-10 |
| 0.128 | 0.800 | Tomás Beckett (Internal) | offer | exec team | slack_threads.jsonl R1130 2026-02-06 Tomás Beckett: "I'll take this one — I've got a direct line to their exec team" |
| 0.128 | 0.356 | Elena Duvall (Advisor) | direct | Saoirse Yarrow — Head of Innovation | connections_duvall.csv: Saoirse Yarrow, Head of Innovation at Blackwood Industrial, connected 2019-02-04 |
| 0.053 | 0.330 | Tomás Beckett (Internal) | direct | Marcus Højgaard — Chief Technology Officer | connections_beckett.csv: Marcus Højgaard, Chief Technology Officer at Blackwood Industrial, connected 2015-01-02 |
| 0.041 | 0.357 | Owen Trask (Investor) | direct | Marcus Højgaard — Chief Technology Officer | connections_trask.csv: Marcus Højgaard, Chief Technology Officer at Blackwood Industrial, connected 2017-04-20 |
| 0.030 | 0.187 | Tomás Beckett (Internal) | alumni | Marcus Højgaard — ex-Blackwood Industrial (2014-2017), now Chief Technology Officer at Blackwood Industrial | investor_network.csv: Marcus Højgaard prior_employer=Blackwood Industrial (2014-2017); connections_beckett.csv: connection of Tomás Beckett since 2015-01-02 |
| 0.023 | 0.202 | Owen Trask (Investor) | alumni | Marcus Højgaard — ex-Blackwood Industrial (2014-2017), now Chief Technology Officer at Blackwood Industrial | investor_network.csv: Marcus Højgaard prior_employer=Blackwood Industrial (2014-2017); connections_trask.csv: connection of Owen Trask since 2017-04-20 |
| 0.215 | 0.900 | Otto Cathcart-Brenneman (investor network) | investor_network (board seat) | CEO / exec team — Ashgrove Capital board seat | investor_network.csv: Otto Cathcart-Brenneman (Venture capital investor), portfolio_company=Blackwood Industrial, board_seat=True |

why not #1: Otto Cathcart-Brenneman investor network, roster asked first -> R1022, R1091, R1179 to Elena Duvall

## 4. Chronology (25 events, 4 requests, newest first, as of 2026-09-06)

```
<- 2026-09-06  intro_outcomes.csv   Tomás Beckett        R1130 said yes 199 days ago and never forwarded
++ 2026-02-19  intro_outcomes.csv   Tomás Beckett        R1130 replied (9 days after the ask)
   2026-02-10  intro_outcomes.csv   Tomás Beckett        R1130 asked
** 2026-02-06  slack_threads.jsonl  Tomás Beckett        R1130 slack: "I'll take this one — I've got a direct line to their exec team"
   2026-02-04  slack_threads.jsonl  Sloane Fairweather   R1130 slack: "trying to reach Director of Software Engineering at Blackwood Industrial — anyone have a path?"
   2026-02-04  intro_requests.csv   Sloane Fairweather   R1130 raised by Sloane Fairweather (Strategic AE): wants Director of Software Engineering, $80,000, Low urgency, filed "Stalled"

++ 2026-06-20  intro_outcomes.csv   Elena Duvall         R1022 intro sent
++ 2026-06-18  intro_outcomes.csv   Elena Duvall         R1022 replied (2 days after the ask)
   2026-06-16  intro_outcomes.csv   Elena Duvall         R1022 asked
   2026-06-14  slack_threads.jsonl  Curtis Hartigan      R1022 slack: "did we not already lose this one?"
   2026-06-11  slack_threads.jsonl  Nadia Okonkwo        R1022 slack: "asking again: Blackwood Industrial. Director of Software Engineering. Happy to draft the forward myself if someone can vouch."
!! 2026-06-11  intro_requests.csv   Nadia Okonkwo        R1022 raised by Nadia Okonkwo (AE, Industrials): wants Director of Software Engineering, $1,200,000, High urgency, filed "Open"  [same title as R1130, 127 days earlier]

++ 2026-05-02  intro_outcomes.csv   Elena Duvall         R1091 intro sent
++ 2026-04-24  intro_outcomes.csv   Elena Duvall         R1091 replied (7 days after the ask)
   2026-04-17  intro_outcomes.csv   Elena Duvall         R1091 asked
   2026-04-17  slack_threads.jsonl  Imani Mkhize         R1091 slack: "did we not already lose this one?"
   2026-04-16  slack_threads.jsonl  Hana Nakashima       R1091 slack: "I think their procurement is frozen until Q1"
   2026-04-16  slack_threads.jsonl  Bertrand Vandermolen R1091 slack: "is this the same as the one from last month?"
   2026-04-14  slack_threads.jsonl  Yusuf Petrossian     R1091 slack: "who do we know at Blackwood Industrial? Chief Digital Officer would be ideal but I'll take anyone senior"
   2026-04-14  intro_requests.csv   Yusuf Petrossian     R1091 raised by Yusuf Petrossian (SDR Lead): wants Chief Digital Officer, $150,000, High urgency, filed "Stalled"

   2025-12-12  slack_threads.jsonl  Bertrand Vandermolen R1179 slack: "I think their procurement is frozen until Q1"
   2025-12-12  slack_threads.jsonl  Imani Mkhize         R1179 slack: "is this the same as the one from last month?"
   2025-12-10  slack_threads.jsonl  Nadia Okonkwo        R1179 slack: "need help getting to Blackwood Industrial. Rhys Balogun-Kirkbride is the SVP Digital there, cold outbound is going nowhere"
   2025-12-10  intro_requests.csv   Nadia Okonkwo        R1179 raised by Nadia Okonkwo (AE, Industrials): wants SVP Digital, $250,000, High urgency, filed "Open"

!! 2025-09-26  crm_accounts.csv     Imani Mkhize         last CRM touch on A1010  [345 days ago, nothing since]
```

## 5. Additional Investor and Operator Network

2 people from investor_network.csv, 1 askable as investor_network paths, 0 with no warm path; a view of section 3 and the roster's exports, nothing here is scored or allocated on its own

| person | role | fund | board seat | source | warm path |
|---|---|---|---|---|---|
| Otto Cathcart-Brenneman | Venture capital investor | Ashgrove Capital | yes | portfolio_company | investor_network path (section 3, 10% haircut) |
| Marcus Højgaard | Operator (work history) |  | no | prior_employer | via Beckett, Trask |
