# Cobalt Lane Capital Markets  (C009)

- stage: Discovery | industry: Financial Services | owner: Rafael Salcedo | deal value: $600,000 (CRM ARR potential) | by request: R1076 $250,000, R1078 $2,000,000
- CRM accounts: A1038 (cobaltlanecm.com)
- also goes by: nothing else
- 2 requests from 2 people wanting 2 different titles: Chief Digital Officer | VP Engineering

## 2. Where the files disagree

- R1076: filed "Open" but intro_outcomes.csv says Tomás Beckett sent the intro on 2026-02-07

## Currently routing to: Priya Raghunathan

- this cycle: R1076 (retry) -> Priya Raghunathan
- top askable path: Priya Raghunathan, direct via Greta Petrossian, route score 0.092, 3/3 capacity used this cycle

## 3. Who can reach them

in the allocator's order: the tiers below, then route score = strength x focus fit x delivery rate within each; investor_network rows rank below every roster path and take a 10% haircut on route score

**roster - asked first** (2 paths)

| route score | strength | connector | reach | contact | evidence | unresolved ask |
|---|---|---|---|---|---|---|
| 0.092 | 0.449 | Priya Raghunathan (Investor) | direct | Greta Petrossian — Head of Automation | connections_raghunathan.csv: Greta Petrossian, Head of Automation at Cobalt Lane Capital Markets, connected 2023-11-21 |  |
| 0.080 | 0.496 | Tomás Beckett (Internal) | direct | Greta Petrossian — Head of Automation | connections_beckett.csv: Greta Petrossian, Head of Automation at Cobalt Lane Capital Markets, connected 2025-07-17 |  |

**investor_network - asked when no roster path is left** (1 path)

| route score | strength | connector | reach | contact | evidence | unresolved ask |
|---|---|---|---|---|---|---|
| 0.172 | 0.720 | Malik Thackeray-Okonkwo (investor network) | investor_network | CEO / exec team — Meridian Peak Partners portfolio company | investor_network.csv: Malik Thackeray-Okonkwo (Private equity investor), portfolio_company=Cobalt Lane Capital Markets, board_seat=False |  |

why not #1: Malik Thackeray-Okonkwo investor network, roster asked first -> R1076 to Priya Raghunathan

## 4. Chronology (15 events, 2 requests, newest first, as of 2026-09-06)

```
++ 2026-02-07  intro_outcomes.csv   Tomás Beckett        R1076 intro sent
   2026-01-30  slack_threads.jsonl  Hana Nakashima       R1076 slack: "no idea sorry"
++ 2026-01-29  intro_outcomes.csv   Tomás Beckett        R1076 replied (2 days after the ask)
   2026-01-28  slack_threads.jsonl  Hana Nakashima       R1076 slack: "did we not already lose this one?"
   2026-01-27  intro_outcomes.csv   Tomás Beckett        R1076 asked
   2026-01-27  slack_threads.jsonl  Imani Mkhize         R1076 slack: "we need Cobalt Lane Capital Markets. Not Ferrowick Insurance — that's a different entity and we already have that one. Also spoke to Apex Logistics last week, unrelated."
   2026-01-27  intro_requests.csv   Imani Mkhize         R1076 raised by Imani Mkhize (Enterprise AE, West): wants Chief Digital Officer, $250,000, Critical urgency, filed "Open"

++ 2025-11-26  intro_outcomes.csv   Tomás Beckett        R1078 meeting booked
++ 2025-11-26  intro_outcomes.csv   Tomás Beckett        R1078 intro sent
++ 2025-11-18  intro_outcomes.csv   Tomás Beckett        R1078 replied (2 days after the ask)
   2025-11-16  intro_outcomes.csv   Tomás Beckett        R1078 asked
   2025-11-12  slack_threads.jsonl  Hana Nakashima       R1078 slack: "is this the same as the one from last month?"
   2025-11-11  slack_threads.jsonl  Hana Nakashima       R1078 slack: "asking again: Cobalt Lane Capital Markets. VP Engineering. Happy to draft the forward myself if someone can vouch."
   2025-11-11  intro_requests.csv   Hana Nakashima       R1078 raised by Hana Nakashima (AE, Healthcare): wants VP Engineering, $2,000,000, Medium urgency, filed "Intro sent"

!! 2025-11-27  crm_accounts.csv     Rafael Salcedo       last CRM touch on A1038  [283 days ago, nothing since]
```

## 5. Additional Investor and Operator Network

1 person from investor_network.csv, 1 askable as investor_network paths, 0 with no warm path; a view of section 3 and the roster's exports, nothing here is scored or allocated on its own

| person | role | fund | board seat | source | warm path |
|---|---|---|---|---|---|
| Malik Thackeray-Okonkwo | Private equity investor | Meridian Peak Partners | no | portfolio_company | investor_network path (section 3, 10% haircut) |
