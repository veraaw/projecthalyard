# Gravenhurst Motors  (C016)

- stage: Negotiation | industry: Automotive | owner: Sloane Fairweather | deal value: $400,000 | largest request: $2,000,000
- CRM accounts: A1041 (gravenhurst.com)
- also goes by: nothing else
- 9 requests from 5 people wanting 8 different titles: Chief Data Officer | Chief Digital Officer | Chief Operating Officer | Director of Software Engineering | Head of Platform Engineering | SVP Digital | VP Engineering | VP Enterprise Architecture

## 2. Where the files disagree

- R1108: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 8 paths
- R1185: filed "Stalled" but intro_outcomes.csv says Priya Raghunathan sent the intro on 2026-02-22
- R1115: filed "Intro sent" but intro_outcomes.csv has no row at all
- R1115: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 8 paths
- R1115: Priya Raghunathan offered in slack_threads.jsonl on 2026-02-20 ("their Head of Platform reports to someone I've known for a decade, leave it with me") but intro_outcomes.csv never asked them
- R1149: filed "Routed" but intro_outcomes.csv says Priya Raghunathan sent the intro on 2026-05-23
- R1160: filed "Closed - no path" but supply_reach.csv has 8 paths into Gravenhurst Motors
- R1122: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 8 paths

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.262 | 0.800 | Curtis Hartigan (not on roster) | offer | Chief Data Officer | slack_threads.jsonl R1122 2026-07-20 Curtis Hartigan: "I met their Chief Data Officer at a conference last spring, happy to reach out" |
| 0.182 | 0.800 | Hana Nakashima (not on roster) | offer | Chief Digital Officer | slack_threads.jsonl R1108 2025-10-09 Hana Nakashima: "I met their Chief Digital Officer at a conference last spring, happy to reach out" |
| 0.164 | 0.800 | Priya Raghunathan (Investor) | offer | Head of Platform | slack_threads.jsonl R1115 2026-02-20 Priya Raghunathan: "their Head of Platform reports to someone I've known for a decade, leave it with me" |
| 0.147 | 0.720 | Priya Raghunathan (Investor) | investor | CEO / exec team — Redtree Capital portfolio company | investor_network.csv: Priya Raghunathan (Partner, Redtree Capital), portfolio_company=Gravenhurst Motors, board_seat=False |
| 0.058 | 0.285 | Priya Raghunathan (Investor) | direct | Priya Fairweather — Head of Platform Engineering | connections_raghunathan.csv: Priya Fairweather, Head of Platform Engineering at Gravenhurst Motors, connected 2016-11-20 |
| 0.038 | 0.187 | Priya Raghunathan (Investor) | alumni | Priya Fairweather — ex-Gravenhurst Motors (2014-2019), now Head of Platform Engineering at Gravenhurst Motors | investor_network.csv: Priya Fairweather prior_employer=Gravenhurst Motors (2014-2019); connections_raghunathan.csv: connection of Priya Raghunathan since 2016-11-20 |
| 0.000 | 0.332 | Elena Duvall (Advisor) | direct | Priya Fairweather — Head of Platform Engineering | connections_duvall.csv: Priya Fairweather, Head of Platform Engineering at Gravenhurst Motors, connected 2018-07-13 |
| 0.000 | 0.218 | Elena Duvall (Advisor) | alumni | Priya Fairweather — ex-Gravenhurst Motors (2014-2019), now Head of Platform Engineering at Gravenhurst Motors | investor_network.csv: Priya Fairweather prior_employer=Gravenhurst Motors (2014-2019); connections_duvall.csv: connection of Elena Duvall since 2018-07-13 |

strongest path, not where it went: Curtis Hartigan, offer 0.800, 0/2 used this cycle; R1143 unrouted (already introduced: Curtis Hartigan on 2026-08-10 (R1122, meeting booked)), R1158 unrouted (already introduced: Curtis Hartigan on 2026-08-10 (R1122, meeting booked))

## 4. Chronology (56 events, 9 requests, as of 2026-09-06)

```
   2025-10-09  intro_requests.csv   Yusuf Petrossian     R1108 raised by Yusuf Petrossian (SDR Lead): wants VP Engineering, $250,000, Critical urgency, filed "Stalled"
   2025-10-09  slack_threads.jsonl  Yusuf Petrossian     R1108 slack: "any connections into Gravenhurst Motors? we're up against a renewal window and I need an intro to VP Engineering"
   2025-10-09  slack_threads.jsonl  Curtis Hartigan      R1108 slack: "bumping this"
   2025-10-09  slack_threads.jsonl  Curtis Hartigan      R1108 slack: "I think their procurement is frozen until Q1"
** 2025-10-09  slack_threads.jsonl  Hana Nakashima       R1108 slack: "I met their Chief Digital Officer at a conference last spring, happy to reach out"
   2025-10-11  intro_outcomes.csv   Hana Nakashima       R1108 asked
   2025-10-13  slack_threads.jsonl  Curtis Hartigan      R1108 slack: "bumping this"
++ 2025-10-23  intro_outcomes.csv   Hana Nakashima       R1108 replied (12 days after the ask)
<- 2026-09-06  intro_outcomes.csv   Hana Nakashima       R1108 said yes 318 days ago and never forwarded

   2025-10-30  intro_requests.csv   Rafael Salcedo       R1158 raised by Rafael Salcedo (AE, Transport & Logistics): wants Head of Platform Engineering, $750,000, Critical urgency, filed "Open"
   2025-10-30  slack_threads.jsonl  Rafael Salcedo       R1158 slack: "any connections into Gravenhurst Motors? we're up against a renewal window and I need an intro to Head of Platform Engineering"
   2025-11-02  slack_threads.jsonl  Nadia Okonkwo        R1158 slack: "is this the same as the one from last month?"
   2025-11-03  slack_threads.jsonl  Imani Mkhize         R1158 slack: "wrong channel? this feels like a partner ask"

   2026-01-01  intro_requests.csv   Curtis Hartigan      R1058 raised by Curtis Hartigan (AE, Financial Services): wants Chief Data Officer, $80,000, Medium urgency, filed "Open"
   2026-01-01  slack_threads.jsonl  Curtis Hartigan      R1058 slack: "need help getting to Gravenhurst Motors. Imani Salcedo-Prendergast is the Chief Data Officer there, cold outbound is going nowhere"
   2026-01-02  slack_threads.jsonl  Rafael Salcedo       R1058 slack: "what's the deal size here?"
   2026-01-02  intro_outcomes.csv   Priya Raghunathan    R1058 asked
   2026-01-03  slack_threads.jsonl  Hana Nakashima       R1058 slack: "adding Curtis Hartigan who might know"
<- 2026-09-06  intro_outcomes.csv   Priya Raghunathan    R1058 never replied (asked 2026-01-02, 247 days ago)

   2026-02-04  intro_requests.csv   Yusuf Petrossian     R1185 raised by Yusuf Petrossian (SDR Lead): wants VP Enterprise Architecture, $1,200,000, High urgency, filed "Stalled"
   2026-02-04  slack_threads.jsonl  Yusuf Petrossian     R1185 slack: "need help getting to Gravenhurst Motors. Rosalind Zubkov-Isenberg is the VP Enterprise Architecture there, cold outbound is going nowhere"
   2026-02-08  intro_outcomes.csv   Priya Raghunathan    R1185 asked
++ 2026-02-14  intro_outcomes.csv   Priya Raghunathan    R1185 replied (6 days after the ask)
++ 2026-02-22  intro_outcomes.csv   Priya Raghunathan    R1185 intro sent

!! 2026-02-20  intro_requests.csv   Curtis Hartigan      R1115 raised by Curtis Hartigan (AE, Financial Services): wants SVP Digital, $2,000,000, High urgency, filed "Intro sent"  [no intro in intro_outcomes.csv]
   2026-02-20  slack_threads.jsonl  Curtis Hartigan      R1115 slack: "trying to reach SVP Digital at Gravenhurst Motors — anyone have a path?"
** 2026-02-20  slack_threads.jsonl  Priya Raghunathan    R1115 slack: "their Head of Platform reports to someone I've known for a decade, leave it with me"  [never taken up]
   2026-02-21  slack_threads.jsonl  Curtis Hartigan      R1115 slack: "I think their procurement is frozen until Q1"
   2026-02-21  slack_threads.jsonl  Curtis Hartigan      R1115 slack: "is this the same as the one from last month?"
   2026-02-22  slack_threads.jsonl  Yusuf Petrossian     R1115 slack: "did we not already lose this one?"

   2026-03-04  intro_requests.csv   Sloane Fairweather   R1143 raised by Sloane Fairweather (Strategic AE): wants Chief Operating Officer, $150,000, Low urgency, filed "Routed"
   2026-03-04  slack_threads.jsonl  Sloane Fairweather   R1143 slack: "any connections into Gravenhurst Motors? we're up against a renewal window and I need an intro to Chief Operating Officer"

   2026-05-02  intro_requests.csv   Rafael Salcedo       R1149 raised by Rafael Salcedo (AE, Transport & Logistics): wants Chief Digital Officer, $80,000, Critical urgency, filed "Routed"
   2026-05-02  slack_threads.jsonl  Rafael Salcedo       R1149 slack: "trying to reach Chief Digital Officer at Gravenhurst Motors — anyone have a path?"
   2026-05-02  slack_threads.jsonl  Bertrand Vandermolen R1149 slack: "is this the same as the one from last month?"
   2026-05-04  slack_threads.jsonl  Rafael Salcedo       R1149 slack: "did we not already lose this one?"
   2026-05-05  intro_outcomes.csv   Priya Raghunathan    R1149 asked
++ 2026-05-15  intro_outcomes.csv   Priya Raghunathan    R1149 replied (10 days after the ask)
++ 2026-05-23  intro_outcomes.csv   Priya Raghunathan    R1149 intro sent
++ 2026-05-23  intro_outcomes.csv   Priya Raghunathan    R1149 meeting booked
++ 2026-05-23  intro_outcomes.csv   Priya Raghunathan    R1149 opportunity created, $80,000

!! 2026-05-22  intro_requests.csv   Bertrand Vandermolen R1160 raised by Bertrand Vandermolen (AE, EMEA): wants Director of Software Engineering, $150,000, High urgency, filed "Closed - no path"  [8 paths in supply_reach.csv]
   2026-05-22  slack_threads.jsonl  Bertrand Vandermolen R1160 slack: "any connections into Gravenhurst Motors? we're up against a renewal window and I need an intro to Director of Software Engineering"
   2026-05-26  slack_threads.jsonl  Bertrand Vandermolen R1160 slack: "no idea sorry"
   2026-05-26  slack_threads.jsonl  Imani Mkhize         R1160 slack: "adding Bertrand Vandermolen who might know"
   2026-05-26  intro_outcomes.csv   Priya Raghunathan    R1160 asked
++ 2026-06-06  intro_outcomes.csv   Priya Raghunathan    R1160 replied (11 days after the ask)
++ 2026-06-14  intro_outcomes.csv   Priya Raghunathan    R1160 intro sent

!! 2026-07-19  intro_requests.csv   Rafael Salcedo       R1122 raised by Rafael Salcedo (AE, Transport & Logistics): wants SVP Digital, $1,200,000, Low urgency, filed "Intro sent"  [same title as R1115, 149 days earlier]
   2026-07-19  slack_threads.jsonl  Rafael Salcedo       R1122 slack: "need help getting to Gravenhurst Motors. Greta Bellinger-Fairweather is the SVP Digital there, cold outbound is going nowhere"
** 2026-07-20  slack_threads.jsonl  Curtis Hartigan      R1122 slack: "I met their Chief Data Officer at a conference last spring, happy to reach out"
   2026-07-25  intro_outcomes.csv   Curtis Hartigan      R1122 asked
++ 2026-08-05  intro_outcomes.csv   Curtis Hartigan      R1122 replied (11 days after the ask)
++ 2026-08-10  intro_outcomes.csv   Curtis Hartigan      R1122 intro sent
++ 2026-08-10  intro_outcomes.csv   Curtis Hartigan      R1122 meeting booked

!! 2026-01-07  crm_accounts.csv     Sloane Fairweather   last CRM touch on A1041  [242 days ago, nothing since]
```

## 5. Next steps, by person, cheapest first

| # | who | role | action | why | requests |
|---|---|---|---|---|---|
| 1 | Rafael Salcedo | AE, Transport & Logistics, holds the intro | extend the intro, no connector is asked | Curtis Hartigan introduced SVP Digital on 2026-08-10 (R1122, meeting booked); the allocator parks every live request here, so Rafael asks that contact for Chief Operating Officer, Head of Platform Engineering | R1143, R1158 |
| 2 | Priya Raghunathan | Partner, Redtree Capital (investor connector) | take them up on it | offered on 2026-02-20 ("their Head of Platform reports to someone I've known for a decade, leave it with me") and was never asked — free, they already said yes | R1115 |
| 3 | Hana Nakashima | off-roster connector | nudge, don't re-ask | said yes on 2025-10-23 and never forwarded | R1108 |
| 4 | Sloane Fairweather | CRM owner (A1041) | check in on the account | last touch 2026-01-07, 242 days ago | — |
| 5 | Yusuf Petrossian (332 days), Rafael Salcedo (311 days), Curtis Hartigan (248 days), Sloane Fairweather (186 days) | 4 reps still waiting, longest first | tell them it's with Hana Nakashima / Priya Raghunathan | 4 reps raised this and have heard nothing; the oldest has been waiting 332 days | R1108, R1158, R1058, R1115, R1143 |
