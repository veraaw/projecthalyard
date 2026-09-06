# Osric Networks  (C028)

- stage: Discovery | industry: Telecom | owner: Nadia Okonkwo | deal value: $250,000 (CRM ARR potential) | by request: R1028 $2,000,000, R1163 $400,000, R1167 $250,000, R1170 $1,200,000
- CRM accounts: A1044 (osricnetworks.com)
- also goes by: nothing else
- 4 requests from 4 people wanting 4 different titles: Chief Data Officer | Chief Digital Officer | Director of Software Engineering | SVP Digital

## 2. Where the files disagree

- R1163: filed "Open" but intro_outcomes.csv says Elena Duvall sent the intro on 2026-04-02
- R1163: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 5 paths
- R1167: filed "Stalled" but intro_outcomes.csv says Priya Raghunathan sent the intro on 2026-01-31
- R1167: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 5 paths
- R1170: intro_requests.csv path_found_flag="No path found" but supply_reach.csv has 5 paths

## Currently routing to: nobody (parked on live intro: R1163, Elena Duvall, 2026-04-02, meeting booked)

- this cycle: R1028, R1170 unrouted (already introduced)
- nothing goes out this cycle; the top askable path is: Priya Raghunathan, offer via ?, route score 0.164, 3/3 capacity used this cycle

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key; investor_network rows rank below every roster path and take a 10% haircut on route score

| route score | strength | connector | reach | contact | evidence | unresolved ask |
|---|---|---|---|---|---|---|
| 0.164 | 0.800 | Priya Raghunathan (Investor) | offer | exec team | slack_threads.jsonl R1167 2026-01-16 Priya Raghunathan: "I'll take this one — I've got a direct line to their exec team" |  |
| 0.000 | 0.800 | Elena Duvall (Advisor) | offer | Chief Data Officer | slack_threads.jsonl R1163 2026-03-27 Elena Duvall: "I met their Chief Data Officer at a conference last spring, happy to reach out" |  |
| 0.215 | 0.900 | Malik Thackeray-Okonkwo (investor network) | investor_network (board seat) | CEO / exec team — Meridian Peak Partners board seat | investor_network.csv: Malik Thackeray-Okonkwo (Private equity investor), portfolio_company=Osric Networks, board_seat=True |  |
| 0.172 | 0.720 | Freya Oldfield-Ibarra (investor network) | investor_network | CEO / exec team — Ashgrove Capital portfolio company | investor_network.csv: Freya Oldfield-Ibarra (Venture capital investor), portfolio_company=Osric Networks, board_seat=False |  |
| 0.172 | 0.720 | Perrine Brenneman-Wexford (investor network) | investor_network | CEO / exec team — Meridian Peak Partners portfolio company | investor_network.csv: Perrine Brenneman-Wexford (Private equity investor), portfolio_company=Osric Networks, board_seat=False |  |

why not #1: parked on live intro (R1163, Elena Duvall, 2026-04-02, meeting booked): R1028, R1170

## 4. Chronology (24 events, 4 requests, newest first, as of 2026-09-06)

```
   2026-07-18  slack_threads.jsonl  Yusuf Petrossian     R1028 slack: "Duncastle Hotels introduced us to Calderon Aerospace, but the account I actually need is Osric Networks (Chief Digital Officer)."
   2026-07-18  intro_requests.csv   Yusuf Petrossian     R1028 raised by Yusuf Petrossian (SDR Lead): wants Chief Digital Officer, $2,000,000, Critical urgency, filed "Open"

++ 2026-04-02  intro_outcomes.csv   Elena Duvall         R1163 opportunity created, $400,000
++ 2026-04-02  intro_outcomes.csv   Elena Duvall         R1163 meeting booked
++ 2026-04-02  intro_outcomes.csv   Elena Duvall         R1163 intro sent
++ 2026-04-01  intro_outcomes.csv   Elena Duvall         R1163 replied (5 days after the ask)
   2026-03-27  intro_outcomes.csv   Elena Duvall         R1163 asked
   2026-03-27  slack_threads.jsonl  Yusuf Petrossian     R1163 slack: "no idea sorry"
** 2026-03-27  slack_threads.jsonl  Elena Duvall         R1163 slack: "I met their Chief Data Officer at a conference last spring, happy to reach out"
   2026-03-25  slack_threads.jsonl  Curtis Hartigan      R1163 slack: "did we not already lose this one?"
   2026-03-25  slack_threads.jsonl  Curtis Hartigan      R1163 slack: "need help getting to Osric Networks. Hana Salcedo-Balogun is the Chief Data Officer there, cold outbound is going nowhere"
   2026-03-25  intro_requests.csv   Curtis Hartigan      R1163 raised by Curtis Hartigan (AE, Financial Services): wants Chief Data Officer, $400,000, High urgency, filed "Open"

++ 2026-01-31  intro_outcomes.csv   Priya Raghunathan    R1167 meeting booked
++ 2026-01-31  intro_outcomes.csv   Priya Raghunathan    R1167 intro sent
++ 2026-01-21  intro_outcomes.csv   Priya Raghunathan    R1167 replied (4 days after the ask)
   2026-01-17  intro_outcomes.csv   Priya Raghunathan    R1167 asked
   2026-01-17  slack_threads.jsonl  Imani Mkhize         R1167 slack: "what's the deal size here?"
** 2026-01-16  slack_threads.jsonl  Priya Raghunathan    R1167 slack: "I'll take this one — I've got a direct line to their exec team"
   2026-01-15  slack_threads.jsonl  Sloane Fairweather   R1167 slack: "bumping this"
   2026-01-15  slack_threads.jsonl  Nadia Okonkwo        R1167 slack: "who do we know at Osric Networks? Director of Software Engineering would be ideal but I'll take anyone senior"
   2026-01-15  intro_requests.csv   Nadia Okonkwo        R1167 raised by Nadia Okonkwo (AE, Industrials): wants Director of Software Engineering, $250,000, Critical urgency, filed "Stalled"

   2025-09-10  slack_threads.jsonl  Hana Nakashima       R1170 slack: "any connections into Osric Networks? we're up against a renewal window and I need an intro to SVP Digital"
   2025-09-10  intro_requests.csv   Hana Nakashima       R1170 raised by Hana Nakashima (AE, Healthcare): wants SVP Digital, $1,200,000, High urgency, filed "Open"

!! 2026-04-19  crm_accounts.csv     Nadia Okonkwo        last CRM touch on A1044  [140 days ago, nothing since]
```

## 5. Additional Investor and Operator Network

3 people from investor_network.csv, 3 askable as investor_network paths, 0 with no warm path; a view of section 3 and the roster's exports, nothing here is scored or allocated on its own

| person | role | fund | board seat | source | warm path |
|---|---|---|---|---|---|
| Malik Thackeray-Okonkwo | Private equity investor | Meridian Peak Partners | yes | portfolio_company | investor_network path (section 3, 10% haircut) |
| Freya Oldfield-Ibarra | Venture capital investor | Ashgrove Capital | no | portfolio_company | investor_network path (section 3, 10% haircut) |
| Perrine Brenneman-Wexford | Private equity investor | Meridian Peak Partners | no | portfolio_company | investor_network path (section 3, 10% haircut) |
