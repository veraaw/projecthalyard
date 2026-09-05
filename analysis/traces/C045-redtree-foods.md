# Redtree Foods  (C045)

- stage: ? | industry: ? | owner: none | deal value: ? | largest request: $1,200,000
- CRM accounts: none (redtreefoods.com)
- also goes by: redtreefoods.com
- 4 requests from 3 people wanting 4 different titles: Chief Digital Officer | Head of Platform Engineering | VP Data & Analytics | VP Engineering

## 2. Where the files disagree

- R1003: filed "Stalled" but intro_outcomes.csv says Dana Whitfield sent the intro on 2026-03-18
- R1003: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 8 paths

## 3. Who can reach them

| strength | connector | reach | contact | evidence |
|---|---|---|---|---|
| 0.800 | Dana Whitfield (Internal) | offer | VP Enterprise Architecture | slack_threads.jsonl R1003 2026-03-03 Dana Whitfield: "I met their VP Enterprise Architecture at a conference last spring, happy to reach out" |
| 0.720 | Priya Raghunathan (Investor) | investor | CEO / exec team — Redtree Capital portfolio company | investor_network.csv: Priya Raghunathan (Partner, Redtree Capital), portfolio_company=Redtree Foods, board_seat=False |
| 0.438 | Marcus Aldridge (Advisor) | direct | Niall Grimsby — Chief Data Officer | connections_aldridge.csv: Niall Grimsby, Chief Data Officer at Redtree Foods, connected 2020-02-25 |
| 0.357 | Owen Trask (Investor) | direct | Niall Grimsby — Chief Data Officer | connections_trask.csv: Niall Grimsby, Chief Data Officer at Redtree Foods, connected 2017-11-17 |
| 0.308 | Priya Raghunathan (Investor) | direct | Coretta Bellinger — VP Data & Analytics | connections_raghunathan.csv: Coretta Bellinger, VP Data & Analytics at Redtree Foods, connected 2014-07-03 |
| 0.248 | Marcus Aldridge (Advisor) | alumni | Niall Grimsby — ex-Redtree Foods (2013-2019), now Chief Data Officer at Redtree Foods | investor_network.csv: Niall Grimsby prior_employer=Redtree Foods (2013-2019); connections_aldridge.csv: connection of Marcus Aldridge since 2020-02-25 |
| 0.202 | Owen Trask (Investor) | alumni | Niall Grimsby — ex-Redtree Foods (2013-2019), now Chief Data Officer at Redtree Foods | investor_network.csv: Niall Grimsby prior_employer=Redtree Foods (2013-2019); connections_trask.csv: connection of Owen Trask since 2017-11-17 |
| 0.187 | Priya Raghunathan (Investor) | alumni | Coretta Bellinger — ex-Redtree Foods (2012-2016), now VP Data & Analytics at Redtree Foods | investor_network.csv: Coretta Bellinger prior_employer=Redtree Foods (2012-2016); connections_raghunathan.csv: connection of Priya Raghunathan since 2014-07-03 |

## 4. Chronology (18 events, 4 requests, as of 2026-09-05)

```
   2025-10-22  intro_requests.csv   Curtis Hartigan      R1067 raised by Curtis Hartigan (AE, Financial Services): wants Head of Platform Engineering, $1,200,000, Medium urgency, filed "Open"
   2025-10-22  slack_threads.jsonl  Curtis Hartigan      R1067 slack: "does anyone know anyone at Redtree Foods? looking for Head of Platform Engineering, ideally warm"

   2025-12-08  intro_requests.csv   Curtis Hartigan      R1135 raised by Curtis Hartigan (AE, Financial Services): wants Chief Digital Officer, $750,000, High urgency, filed "Open"
   2025-12-08  slack_threads.jsonl  Curtis Hartigan      R1135 slack: "looking for a path to Ilse Oldfield-Dobrescu — email domain is redtreefoods.com, that's all I have"
   2025-12-13  intro_outcomes.csv   Priya Raghunathan    R1135 asked
++ 2025-12-16  intro_outcomes.csv   Priya Raghunathan    R1135 replied (3 days after the ask)
<- 2026-09-05  intro_outcomes.csv   Priya Raghunathan    R1135 said yes 263 days ago and never forwarded

   2026-03-03  intro_requests.csv   Imani Mkhize         R1003 raised by Imani Mkhize (Enterprise AE, West): wants VP Engineering, $400,000, High urgency, filed "Stalled"
   2026-03-03  slack_threads.jsonl  Imani Mkhize         R1003 slack: "long shot — Redtree Foods. Tomás Jarrold-Egerton (VP Engineering). Anyone?"
** 2026-03-03  slack_threads.jsonl  Dana Whitfield       R1003 slack: "I met their VP Enterprise Architecture at a conference last spring, happy to reach out"
   2026-03-06  slack_threads.jsonl  Nadia Okonkwo        R1003 slack: "bumping this"
   2026-03-06  intro_outcomes.csv   Dana Whitfield       R1003 asked
++ 2026-03-08  intro_outcomes.csv   Dana Whitfield       R1003 replied (2 days after the ask)
++ 2026-03-18  intro_outcomes.csv   Dana Whitfield       R1003 intro sent

   2026-06-03  intro_requests.csv   Bertrand Vandermolen R1074 raised by Bertrand Vandermolen (AE, EMEA): wants VP Data & Analytics, $750,000, High urgency, filed "Stalled"
   2026-06-03  slack_threads.jsonl  Bertrand Vandermolen R1074 slack: "trying to reach VP Data & Analytics at Redtree Foods — anyone have a path?"
   2026-06-05  slack_threads.jsonl  Curtis Hartigan      R1074 slack: "did we not already lose this one?"
   2026-06-07  slack_threads.jsonl  Sloane Fairweather   R1074 slack: "is this the same as the one from last month?"
```

## 5. Next steps, by person, cheapest first

| # | who | role | action | why | requests |
|---|---|---|---|---|---|
| 1 | Priya Raghunathan | Partner, Redtree Capital (investor connector) | nudge, don't re-ask | said yes on 2025-12-16 and never forwarded | R1135 |
| 2 | Dana Whitfield | Chief Revenue Officer (internal connector) | send the ask (batch 2026-09 Dana Whitfield) | allocated in golden_allocation.csv via offer path, score 0.240; allocated in golden_allocation.csv via offer path, score 0.240 | R1067, R1074 |
| 3 | Curtis Hartigan (318 days), Bertrand Vandermolen (94 days) | 2 reps still waiting, longest first | tell them it's with Priya Raghunathan | 2 reps raised this and have heard nothing; the oldest has been waiting 318 days | R1067, R1135, R1074 |
