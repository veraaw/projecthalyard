# Redtree Foods  (C045)

- stage: ? | industry: ? | owner: none | deal value: $750,000 (latest request with a deal value, R1074) | by request: R1074 $750,000, R1003 $400,000, R1135 $750,000, R1067 $1,200,000
- CRM accounts: none (redtreefoods.com)
- also goes by: redtreefoods.com
- 4 requests from 3 people wanting 4 different titles: Chief Digital Officer | Head of Platform Engineering | VP Data & Analytics | VP Engineering

## 2. Where the files disagree

- R1003: filed "Stalled" but intro_outcomes.csv says Dana Whitfield sent the intro on 2026-03-18
- R1003: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 9 paths

## Currently routing to: Dana Whitfield

- this cycle: R1003 (retry), R1067, R1074 -> Dana Whitfield
- top askable path: Dana Whitfield, offer via ?, route score 0.240, 6/6 capacity used this cycle
- not asked again here: Priya Raghunathan agreed on 2025-12-16 (R1135), no intro - nudge

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key; investor_network rows rank below every roster path and take a 10% haircut on route score; a connector with an unresolved ask here ranks last (unanswered past the window) or is not asked again (agreed with no intro: nudge; unanswered inside the window: chase)

| route score | strength | connector | reach | contact | evidence | unresolved ask |
|---|---|---|---|---|---|---|
| 0.240 | 0.800 | Dana Whitfield (Internal) | offer | VP Enterprise Architecture | slack_threads.jsonl R1003 2026-03-03 Dana Whitfield: "I met their VP Enterprise Architecture at a conference last spring, happy to reach out" |  |
| 0.106 | 0.438 | Marcus Aldridge (Advisor) | direct | Niall Grimsby — Chief Data Officer | connections_aldridge.csv: Niall Grimsby, Chief Data Officer at Redtree Foods, connected 2020-02-25 |  |
| 0.063 | 0.357 | Owen Trask (Investor) | direct | Niall Grimsby — Chief Data Officer | connections_trask.csv: Niall Grimsby, Chief Data Officer at Redtree Foods, connected 2017-11-17 |  |
| 0.060 | 0.248 | Marcus Aldridge (Advisor) | alumni | Niall Grimsby — ex-Redtree Foods (2013-2019), now Chief Data Officer at Redtree Foods | investor_network.csv: Niall Grimsby prior_employer=Redtree Foods (2013-2019); connections_aldridge.csv: connection of Marcus Aldridge since 2020-02-25 |  |
| 0.036 | 0.202 | Owen Trask (Investor) | alumni | Niall Grimsby — ex-Redtree Foods (2013-2019), now Chief Data Officer at Redtree Foods | investor_network.csv: Niall Grimsby prior_employer=Redtree Foods (2013-2019); connections_trask.csv: connection of Owen Trask since 2017-11-17 |  |
| 0.172 | 0.720 | Renata Halloran-Quillane (investor network) | investor_network | CEO / exec team — Redtree Capital portfolio company | investor_network.csv: Renata Halloran-Quillane (Growth equity investor), portfolio_company=Redtree Foods, board_seat=False |  |
| 0.229 | 0.720 | Priya Raghunathan (Investor) | investor | CEO / exec team — Redtree Capital portfolio company | investor_network.csv: Priya Raghunathan (Partner, Redtree Capital), portfolio_company=Redtree Foods, board_seat=False | Priya Raghunathan agreed on 2025-12-16 (R1135), no intro - nudge |
| 0.098 | 0.308 | Priya Raghunathan (Investor) | direct | Coretta Bellinger — VP Data & Analytics | connections_raghunathan.csv: Coretta Bellinger, VP Data & Analytics at Redtree Foods, connected 2014-07-03 | Priya Raghunathan agreed on 2025-12-16 (R1135), no intro - nudge |
| 0.060 | 0.187 | Priya Raghunathan (Investor) | alumni | Coretta Bellinger — ex-Redtree Foods (2012-2016), now VP Data & Analytics at Redtree Foods | investor_network.csv: Coretta Bellinger prior_employer=Redtree Foods (2012-2016); connections_raghunathan.csv: connection of Priya Raghunathan since 2014-07-03 | Priya Raghunathan agreed on 2025-12-16 (R1135), no intro - nudge |

## 4. Chronology (18 events, 4 requests, newest first, as of 2026-09-06)

```
<- 2026-09-06  intro_outcomes.csv   Priya Raghunathan    R1135 said yes 264 days ago and never forwarded
++ 2025-12-16  intro_outcomes.csv   Priya Raghunathan    R1135 replied (3 days after the ask)
   2025-12-13  intro_outcomes.csv   Priya Raghunathan    R1135 asked
   2025-12-08  slack_threads.jsonl  Curtis Hartigan      R1135 slack: "looking for a path to Ilse Oldfield-Dobrescu — email domain is redtreefoods.com, that's all I have"
   2025-12-08  intro_requests.csv   Curtis Hartigan      R1135 raised by Curtis Hartigan (AE, Financial Services): wants Chief Digital Officer, $750,000, High urgency, filed "Open"

   2026-06-07  slack_threads.jsonl  Sloane Fairweather   R1074 slack: "is this the same as the one from last month?"
   2026-06-05  slack_threads.jsonl  Curtis Hartigan      R1074 slack: "did we not already lose this one?"
   2026-06-03  slack_threads.jsonl  Bertrand Vandermolen R1074 slack: "trying to reach VP Data & Analytics at Redtree Foods — anyone have a path?"
   2026-06-03  intro_requests.csv   Bertrand Vandermolen R1074 raised by Bertrand Vandermolen (AE, EMEA): wants VP Data & Analytics, $750,000, High urgency, filed "Stalled"

++ 2026-03-18  intro_outcomes.csv   Dana Whitfield       R1003 intro sent
++ 2026-03-08  intro_outcomes.csv   Dana Whitfield       R1003 replied (2 days after the ask)
   2026-03-06  intro_outcomes.csv   Dana Whitfield       R1003 asked
   2026-03-06  slack_threads.jsonl  Nadia Okonkwo        R1003 slack: "bumping this"
** 2026-03-03  slack_threads.jsonl  Dana Whitfield       R1003 slack: "I met their VP Enterprise Architecture at a conference last spring, happy to reach out"
   2026-03-03  slack_threads.jsonl  Imani Mkhize         R1003 slack: "long shot — Redtree Foods. Tomás Jarrold-Egerton (VP Engineering). Anyone?"
   2026-03-03  intro_requests.csv   Imani Mkhize         R1003 raised by Imani Mkhize (Enterprise AE, West): wants VP Engineering, $400,000, High urgency, filed "Stalled"

   2025-10-22  slack_threads.jsonl  Curtis Hartigan      R1067 slack: "does anyone know anyone at Redtree Foods? looking for Head of Platform Engineering, ideally warm"
   2025-10-22  intro_requests.csv   Curtis Hartigan      R1067 raised by Curtis Hartigan (AE, Financial Services): wants Head of Platform Engineering, $1,200,000, Medium urgency, filed "Open"
```

## 5. Additional Investor and Operator Network

4 people from investor_network.csv, 1 askable as investor_network paths, 0 with no warm path; a view of section 3 and the roster's exports, nothing here is scored or allocated on its own

| person | role | fund | board seat | source | warm path |
|---|---|---|---|---|---|
| Coretta Bellinger | Operator (work history) |  | no | prior_employer | via Raghunathan |
| Niall Grimsby | Operator (work history) |  | no | prior_employer | via Aldridge, Trask |
| Priya Raghunathan | Partner, Redtree Capital | Redtree Capital | no | portfolio_company | on the roster |
| Renata Halloran-Quillane | Growth equity investor | Redtree Capital | no | portfolio_company | investor_network path (section 3, 10% haircut) |
