# Vantage Ridge Utilities  (C041)

- stage: Discovery | industry: Utilities | owner: Rafael Salcedo | deal value: $250,000 | largest request: $1,200,000
- CRM accounts: A1007 (vantageridge.com)
- also goes by: nothing else
- 2 requests from 1 person wanting 1 different title: Chief Operating Officer

## 2. Where the files disagree

- R1111: filed "Intro sent" but intro_outcomes.csv has no row at all

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.171 | 0.492 | Marcus Aldridge (Advisor) | direct | Sabine Dellinger — Chief Data Officer | connections_aldridge.csv: Sabine Dellinger, Chief Data Officer at Vantage Ridge Utilities, connected 2022-12-23 |
| 0.088 | 0.546 | Tomás Beckett (Internal) | direct | Sabine Dellinger — Chief Data Officer | connections_beckett.csv: Sabine Dellinger, Chief Data Officer at Vantage Ridge Utilities, connected 2024-11-09 |

strongest path, not where it went: Tomás Beckett, direct 0.546, at capacity 8/8; R1001 routed to Marcus Aldridge

## 4. Chronology (9 events, 2 requests, as of 2026-09-06)

```
!! 2026-01-29  intro_requests.csv   Imani Mkhize         R1111 raised by Imani Mkhize (Enterprise AE, West): wants Chief Operating Officer, $1,200,000, Medium urgency, filed "Intro sent"  [no intro in intro_outcomes.csv]
   2026-01-29  slack_threads.jsonl  Imani Mkhize         R1111 slack: "who do we know at Vantage Ridge Utilities? Chief Operating Officer would be ideal but I'll take anyone senior"
   2026-02-01  slack_threads.jsonl  Curtis Hartigan      R1111 slack: "what's the deal size here?"

!! 2026-04-14  intro_requests.csv   Imani Mkhize         R1001 raised by Imani Mkhize (Enterprise AE, West): wants Chief Operating Officer, $400,000, High urgency, filed "Open"  [same title as R1111, 75 days earlier]
   2026-04-14  slack_threads.jsonl  Imani Mkhize         R1001 slack: "asking again: Vantage Ridge Utilities. Chief Operating Officer. Happy to draft the forward myself if someone can vouch."
   2026-04-14  slack_threads.jsonl  Nadia Okonkwo        R1001 slack: "did we not already lose this one?"
   2026-04-16  slack_threads.jsonl  Hana Nakashima       R1001 slack: "adding Curtis Hartigan who might know"
   2026-04-16  slack_threads.jsonl  Nadia Okonkwo        R1001 slack: "no idea sorry"

!! 2026-03-19  crm_accounts.csv     Rafael Salcedo       last CRM touch on A1007  [171 days ago, nothing since]
```

## 5. Next steps, by person, cheapest first

| # | who | role | action | why | requests |
|---|---|---|---|---|---|
| 1 | Marcus Aldridge | Advisor (former enterprise CIO) (advisor connector) | send the ask (batch 2026-09 Marcus Aldridge) | allocated in golden_allocation.csv via direct path to Sabine Dellinger, score 0.171 | R1001 |
| 2 | Rafael Salcedo | CRM owner (A1007) | check in on the account | last touch 2026-03-19, 171 days ago | — |
| 3 | Imani Mkhize (220 days) | 1 rep still waiting, longest first | tell them it's with Marcus Aldridge | 1 rep raised this and has heard nothing; the oldest has been waiting 220 days | R1111, R1001 |
