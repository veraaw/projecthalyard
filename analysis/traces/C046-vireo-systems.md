# Vireo Systems  (C046)

- stage: ? | industry: ? | owner: none | deal value: $1,200,000 (latest request with a deal value, R1055) | by request: R1055 $1,200,000, R1155 $1,200,000, R1131 $1,200,000, R1075 $750,000, R1199 $750,000, R1166 $750,000, R1017 $250,000, R1107 $750,000, R1060 $80,000
- CRM accounts: none (vireosystems.com)
- also goes by: vireosystems.com
- 9 requests from 4 people wanting 6 different titles: Chief Data Officer | Chief Digital Officer | Chief Operating Officer | Head of Developer Productivity | VP Engineering | VP Enterprise Architecture

## 2. Where the files disagree

- R1017: filed "Closed - no path" but supply_reach.csv has 4 paths into Vireo Systems
- R1107: filed "Intro sent" but intro_outcomes.csv has no intro (asked Elena Duvall, intro_sent=N)
- R1155: filed "Intro sent" but intro_outcomes.csv has no intro (asked Elena Duvall, intro_sent=N)
- R1166: filed "Closed - no path" but supply_reach.csv has 4 paths into Vireo Systems

## Currently routing to: Priya Raghunathan

- this cycle: R1055, R1075 -> Priya Raghunathan
- top askable path: Priya Raghunathan, investor via CEO / exec team, route score 0.287, 3/3 capacity used this cycle
- not asked again here: Elena Duvall agreed on 2025-11-21 (R1166), no intro - nudge

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key; investor_network rows rank below every roster path and take a 10% haircut on route score; a connector with an unresolved ask here ranks last (unanswered past the window) or is not asked again (agreed with no intro: nudge; unanswered inside the window: chase)

| route score | strength | connector | reach | contact | evidence | unresolved ask |
|---|---|---|---|---|---|---|
| 0.287 | 0.900 | Priya Raghunathan (Investor) | investor (board seat) | CEO / exec team — Redtree Capital board seat | investor_network.csv: Priya Raghunathan (Partner, Redtree Capital), portfolio_company=Vireo Systems, board_seat=True |  |
| 0.120 | 0.496 | Marcus Aldridge (Advisor) | direct | Arjun Cathcart — Head of Developer Productivity | connections_aldridge.csv: Arjun Cathcart, Head of Developer Productivity at Vireo Systems, connected 2025-10-27 |  |
| 0.172 | 0.720 | Amara Brenneman-Fairweather (investor network) | investor_network | CEO / exec team — Redtree Capital portfolio company | investor_network.csv: Amara Brenneman-Fairweather (Growth equity investor), portfolio_company=Vireo Systems, board_seat=False |  |
| 0.131 | 0.519 | Elena Duvall (Advisor) | direct | Arjun Cathcart — Head of Developer Productivity | connections_duvall.csv: Arjun Cathcart, Head of Developer Productivity at Vireo Systems, connected 2026-01-23 | Elena Duvall agreed on 2025-11-21 (R1166), no intro - nudge |

## 4. Chronology (48 events, 9 requests, newest first, as of 2026-09-06)

```
<- 2026-09-06  intro_outcomes.csv   Elena Duvall         R1199 never replied (asked 2025-12-09, 271 days ago)
   2025-12-09  intro_outcomes.csv   Elena Duvall         R1199 asked
   2025-12-09  slack_threads.jsonl  Sloane Fairweather   R1199 slack: "what's the deal size here?"
   2025-12-09  slack_threads.jsonl  Curtis Hartigan      R1199 slack: "any connections into Vireo Systems? we're up against a renewal window and I need an intro to Chief Digital Officer"
   2025-12-09  intro_requests.csv   Curtis Hartigan      R1199 raised by Curtis Hartigan (AE, Financial Services): wants Chief Digital Officer, $750,000, High urgency, filed "Open"

<- 2026-09-06  intro_outcomes.csv   Elena Duvall         R1166 said yes 289 days ago and never forwarded
++ 2025-11-21  intro_outcomes.csv   Elena Duvall         R1166 replied (8 days after the ask)
   2025-11-13  intro_outcomes.csv   Elena Duvall         R1166 asked
   2025-11-08  slack_threads.jsonl  Rafael Salcedo       R1166 slack: "need help getting to Vireo Systems. Gideon Achterberg-Thackeray is the Chief Operating Officer there, cold outbound is going nowhere"
!! 2025-11-08  intro_requests.csv   Rafael Salcedo       R1166 raised by Rafael Salcedo (AE, Transport & Logistics): wants Chief Operating Officer, $750,000, High urgency, filed "Closed - no path"  [4 paths in supply_reach.csv]

<- 2026-09-06  intro_outcomes.csv   Elena Duvall         R1155 never replied (asked 2026-07-01, 67 days ago)
   2026-07-01  intro_outcomes.csv   Elena Duvall         R1155 asked
   2026-07-01  slack_threads.jsonl  Yusuf Petrossian     R1155 slack: "what's the deal size here?"
   2026-06-30  slack_threads.jsonl  Yusuf Petrossian     R1155 slack: "is this the same as the one from last month?"
   2026-06-28  slack_threads.jsonl  Sloane Fairweather   R1155 slack: "wrong channel? this feels like a partner ask"
   2026-06-28  slack_threads.jsonl  Hana Nakashima       R1155 slack: "long shot — Vireo Systems. Niall Jarrold-Norrington (VP Engineering). Anyone?"
!! 2026-06-28  intro_requests.csv   Hana Nakashima       R1155 raised by Hana Nakashima (AE, Healthcare): wants VP Engineering, $1,200,000, Low urgency, filed "Intro sent"  [no intro in intro_outcomes.csv; same title as R1075, 123 days earlier]

<- 2026-09-06  intro_outcomes.csv   Elena Duvall         R1131 never replied (asked 2026-06-25, 73 days ago)
   2026-06-25  intro_outcomes.csv   Elena Duvall         R1131 asked
   2026-06-24  slack_threads.jsonl  Bertrand Vandermolen R1131 slack: "wrong channel? this feels like a partner ask"
   2026-06-24  slack_threads.jsonl  Nadia Okonkwo        R1131 slack: "no idea sorry"
   2026-06-21  slack_threads.jsonl  Yusuf Petrossian     R1131 slack: "adding Yusuf Petrossian who might know"
   2026-06-20  slack_threads.jsonl  Rafael Salcedo       R1131 slack: "trying to reach Chief Data Officer at Vireo Systems. I know we sell into Volney Industrial Systems and Larchmont Aerospace — could either of those relationships get us there?"
   2026-06-20  intro_requests.csv   Rafael Salcedo       R1131 raised by Rafael Salcedo (AE, Transport & Logistics): wants Chief Data Officer, $1,200,000, Low urgency, filed "Stalled"

<- 2026-09-06  intro_outcomes.csv   Elena Duvall         R1107 said yes 296 days ago and never forwarded
++ 2025-11-14  intro_outcomes.csv   Elena Duvall         R1107 replied (5 days after the ask)
   2025-11-09  intro_outcomes.csv   Elena Duvall         R1107 asked
   2025-11-07  slack_threads.jsonl  Yusuf Petrossian     R1107 slack: "no idea sorry"
   2025-11-05  slack_threads.jsonl  Rafael Salcedo       R1107 slack: "what's the deal size here?"
   2025-11-05  slack_threads.jsonl  Hana Nakashima       R1107 slack: "did we not already lose this one?"
   2025-11-05  slack_threads.jsonl  Nadia Okonkwo        R1107 slack: "long shot — Vireo Systems. Ilse Vandermolen-Grimsby (Head of Developer Productivity). Anyone?"
!! 2025-11-05  intro_requests.csv   Nadia Okonkwo        R1107 raised by Nadia Okonkwo (AE, Industrials): wants Head of Developer Productivity, $750,000, High urgency, filed "Intro sent"  [no intro in intro_outcomes.csv]

<- 2026-09-06  intro_outcomes.csv   Elena Duvall         R1060 never replied (asked 2025-08-19, 383 days ago)
   2025-08-19  intro_outcomes.csv   Elena Duvall         R1060 asked
   2025-08-15  slack_threads.jsonl  Nadia Okonkwo        R1060 slack: "does anyone know anyone at Vireo Systems? looking for VP Enterprise Architecture, ideally warm"
   2025-08-15  intro_requests.csv   Nadia Okonkwo        R1060 raised by Nadia Okonkwo (AE, Industrials): wants VP Enterprise Architecture, $80,000, Medium urgency, filed "Open"

   2026-07-12  slack_threads.jsonl  Imani Mkhize         R1055 slack: "adding Imani Mkhize who might know"
   2026-07-08  slack_threads.jsonl  Rafael Salcedo       R1055 slack: "looking for a path to Noor Isenberg-Havercamp — email domain is vireosystems.com, that's all I have"
!! 2026-07-08  intro_requests.csv   Rafael Salcedo       R1055 raised by Rafael Salcedo (AE, Transport & Logistics): wants Chief Digital Officer, $1,200,000, Critical urgency, filed "Open"  [same title as R1199, 211 days earlier]

   2026-02-27  slack_threads.jsonl  Sloane Fairweather   R1075 slack: "I think their procurement is frozen until Q1"
   2026-02-26  slack_threads.jsonl  Nadia Okonkwo        R1075 slack: "is this the same as the one from last month?"
   2026-02-25  slack_threads.jsonl  Hana Nakashima       R1075 slack: "who do we know at Vireo Systems? VP Engineering would be ideal but I'll take anyone senior"
   2026-02-25  intro_requests.csv   Hana Nakashima       R1075 raised by Hana Nakashima (AE, Healthcare): wants VP Engineering, $750,000, Medium urgency, filed "Stalled"

   2025-11-10  slack_threads.jsonl  Hana Nakashima       R1017 slack: "what's the deal size here?"
   2025-11-07  slack_threads.jsonl  Rafael Salcedo       R1017 slack: "adding Rafael Salcedo who might know"
   2025-11-07  slack_threads.jsonl  Hana Nakashima       R1017 slack: "what's the deal size here?"
   2025-11-06  slack_threads.jsonl  Nadia Okonkwo        R1017 slack: "any connections into Vireo Systems? we're up against a renewal window and I need an intro to Head of Developer Productivity"
!! 2025-11-06  intro_requests.csv   Nadia Okonkwo        R1017 raised by Nadia Okonkwo (AE, Industrials): wants Head of Developer Productivity, $250,000, Medium urgency, filed "Closed - no path"  [4 paths in supply_reach.csv; same title as R1107, 1 days earlier]
```

## 5. Additional Investor and Operator Network

2 people from investor_network.csv, 1 askable as investor_network paths, 0 with no warm path; a view of section 3 and the roster's exports, nothing here is scored or allocated on its own

| person | role | fund | board seat | source | warm path |
|---|---|---|---|---|---|
| Priya Raghunathan | Partner, Redtree Capital | Redtree Capital | yes | portfolio_company | on the roster |
| Amara Brenneman-Fairweather | Growth equity investor | Redtree Capital | no | portfolio_company | investor_network path (section 3, 10% haircut) |
