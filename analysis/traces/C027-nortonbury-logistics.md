# Nortonbury Logistics  (C027)

- stage: Evaluation | industry: Logistics | owner: Bertrand Vandermolen | deal value: $600,000 (CRM ARR potential) | by request: R1013 $80,000, R1016 $1,200,000, R1077 $750,000
- CRM accounts: A1039 (nortonbury.com)
- also goes by: nothing else
- 3 requests from 3 people wanting 2 different titles: Chief Operating Officer | Head of Developer Productivity

## 2. Where the files disagree

- R1016: filed "Intro sent" but intro_outcomes.csv has no row at all

## Currently routing to: Perrine Brenneman-Wexford

- this cycle: R1013 -> Perrine Brenneman-Wexford
- top askable path: Priya Raghunathan, investor via CEO / exec team, route score 0.147, 3/3 capacity used this cycle

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key; investor_network rows rank below every roster path and take a 10% haircut on route score; a connector with an unresolved ask here ranks last (unanswered past the window) or is not asked again (agreed with no intro: nudge; unanswered inside the window: chase)

| route score | strength | connector | reach | contact | evidence | unresolved ask |
|---|---|---|---|---|---|---|
| 0.147 | 0.720 | Priya Raghunathan (Investor) | investor | CEO / exec team — Redtree Capital portfolio company | investor_network.csv: Priya Raghunathan (Partner, Redtree Capital), portfolio_company=Nortonbury Logistics, board_seat=False |  |
| 0.116 | 0.600 | Dana Whitfield (Internal) | direct | Zaid Fontaine — Chief Operating Officer | connections_whitfield.csv: Zaid Fontaine, Chief Operating Officer at Nortonbury Logistics, connected 2026-10-19 |  |
| 0.112 | 0.546 | Priya Raghunathan (Investor) | direct | Zaid Fontaine — Chief Operating Officer | connections_raghunathan.csv: Zaid Fontaine, Chief Operating Officer at Nortonbury Logistics, connected 2024-11-24 |  |
| 0.059 | 0.519 | Owen Trask (Investor) | direct | Anouk Kirkbride — Head of Developer Productivity | connections_trask.csv: Anouk Kirkbride, Head of Developer Productivity at Nortonbury Logistics, connected 2026-09-17 |  |
| 0.044 | 0.386 | Owen Trask (Investor) | direct | Nadia Ferreira — Program Manager | connections_trask.csv: Nadia Ferreira, Program Manager at Nortonbury Logistics, connected 2024-03-25 |  |
| 0.000 | 0.405 | Elena Duvall (Advisor) | direct | Nadia Ferreira — Program Manager | connections_duvall.csv: Nadia Ferreira, Program Manager at Nortonbury Logistics, connected 2025-07-30 |  |
| 0.215 | 0.900 | Amara Brenneman-Fairweather (investor network) | investor_network (board seat) | CEO / exec team — Redtree Capital board seat | investor_network.csv: Amara Brenneman-Fairweather (Growth equity investor), portfolio_company=Nortonbury Logistics, board_seat=True |  |
| 0.172 | 0.720 | Perrine Brenneman-Wexford (investor network) | investor_network | CEO / exec team — Meridian Peak Partners portfolio company | investor_network.csv: Perrine Brenneman-Wexford (Private equity investor), portfolio_company=Nortonbury Logistics, board_seat=False |  |
| 0.172 | 0.720 | Renata Halloran-Quillane (investor network) | investor_network | CEO / exec team — Redtree Capital portfolio company | investor_network.csv: Renata Halloran-Quillane (Growth equity investor), portfolio_company=Nortonbury Logistics, board_seat=False |  |
| 0.180 | 0.519 | Marcus Aldridge (Advisor) | direct | Anouk Kirkbride — Head of Developer Productivity | connections_aldridge.csv: Anouk Kirkbride, Head of Developer Productivity at Nortonbury Logistics, connected 2026-07-07 | Marcus Aldridge asked on 2026-03-04 (R1077), no reply for 186 days - askable, ranked last |

why not #1: Amara Brenneman-Fairweather at capacity 2/2 -> R1013 to Perrine Brenneman-Wexford

## 4. Chronology (13 events, 3 requests, newest first, as of 2026-09-06)

```
<- 2026-09-06  intro_outcomes.csv   Marcus Aldridge      R1077 never replied (asked 2026-03-04, 186 days ago)
   2026-03-04  intro_outcomes.csv   Marcus Aldridge      R1077 asked
   2026-02-26  slack_threads.jsonl  Rafael Salcedo       R1077 slack: "trying to reach Head of Developer Productivity at Nortonbury Logistics — anyone have a path?"
   2026-02-26  intro_requests.csv   Rafael Salcedo       R1077 raised by Rafael Salcedo (AE, Transport & Logistics): wants Head of Developer Productivity, $750,000, Low urgency, filed "Open"

   2026-05-13  slack_threads.jsonl  Hana Nakashima       R1013 slack: "no idea sorry"
   2026-05-12  slack_threads.jsonl  Sloane Fairweather   R1013 slack: "did we not already lose this one?"
   2026-05-10  slack_threads.jsonl  Nadia Okonkwo        R1013 slack: "does anyone know anyone at Nortonbury Logistics? looking for Chief Operating Officer, ideally warm"
!! 2026-05-10  intro_requests.csv   Nadia Okonkwo        R1013 raised by Nadia Okonkwo (AE, Industrials): wants Chief Operating Officer, $80,000, Low urgency, filed "Open"  [same title as R1016, 41 days earlier]

   2026-03-30  slack_threads.jsonl  Rafael Salcedo       R1016 slack: "what's the deal size here?"
   2026-03-30  slack_threads.jsonl  Imani Mkhize         R1016 slack: "did we not already lose this one?"
   2026-03-30  slack_threads.jsonl  Curtis Hartigan      R1016 slack: "does anyone know anyone at Nortonbury Logistics? looking for Chief Operating Officer, ideally warm"
!! 2026-03-30  intro_requests.csv   Curtis Hartigan      R1016 raised by Curtis Hartigan (AE, Financial Services): wants Chief Operating Officer, $1,200,000, High urgency, filed "Intro sent"  [no intro in intro_outcomes.csv]

!! 2026-01-22  crm_accounts.csv     Bertrand Vandermolen last CRM touch on A1039  [227 days ago, nothing since]
```

## 5. Additional Investor and Operator Network

4 people from investor_network.csv, 3 askable as investor_network paths, 0 with no warm path; a view of section 3 and the roster's exports, nothing here is scored or allocated on its own

| person | role | fund | board seat | source | warm path |
|---|---|---|---|---|---|
| Amara Brenneman-Fairweather | Growth equity investor | Redtree Capital | yes | portfolio_company | investor_network path (section 3, 10% haircut) |
| Perrine Brenneman-Wexford | Private equity investor | Meridian Peak Partners | no | portfolio_company | investor_network path (section 3, 10% haircut) |
| Priya Raghunathan | Partner, Redtree Capital | Redtree Capital | no | portfolio_company | on the roster |
| Renata Halloran-Quillane | Growth equity investor | Redtree Capital | no | portfolio_company | investor_network path (section 3, 10% haircut) |
