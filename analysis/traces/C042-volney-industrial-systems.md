# Volney Industrial Systems  (C042)

- stage: Closed Lost | industry: Industrials | owner: Yusuf Petrossian | deal value: $2,200,000 (CRM ARR potential) | by request: R1080 $750,000, R1073 $80,000, R1191 $2,000,000, R1002 $400,000
- CRM accounts: A1049 (volney.com)
- also goes by: nothing else
- 4 requests from 4 people wanting 4 different titles: Chief Digital Officer | Chief Information Officer | VP Data & Analytics | VP Engineering

## 2. Where the files disagree

- R1073: filed "Closed - no path" but supply_reach.csv has 4 paths into Volney Industrial Systems

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key; investor_network rows rank below every roster path and take a 10% haircut on route score

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.215 | 0.900 | Curtis Sandoval-Glückstein (investor network) | investor_network (board seat) | CEO / exec team — Thornbury Equity board seat | investor_network.csv: Curtis Sandoval-Glückstein (Private equity investor), portfolio_company=Volney Industrial Systems, board_seat=True |
| 0.172 | 0.720 | Bertrand Achterberg-Quillane (investor network) | investor_network | CEO / exec team — Ashgrove Capital portfolio company | investor_network.csv: Bertrand Achterberg-Quillane (Venture capital investor), portfolio_company=Volney Industrial Systems, board_seat=False |
| 0.172 | 0.720 | Freya Oldfield-Ibarra (investor network) | investor_network | CEO / exec team — Ashgrove Capital portfolio company | investor_network.csv: Freya Oldfield-Ibarra (Venture capital investor), portfolio_company=Volney Industrial Systems, board_seat=False |
| 0.172 | 0.720 | Priya Dobrescu-Prendergast (investor network) | investor_network | CEO / exec team — Thornbury Equity portfolio company | investor_network.csv: Priya Dobrescu-Prendergast (Private equity investor), portfolio_company=Volney Industrial Systems, board_seat=False |

strongest path, not where it went: Curtis Sandoval-Glückstein, investor_network 0.900, at capacity 2/2, holds R1080, R1191; R1002 routed to Bertrand Achterberg-Quillane

## 4. Chronology (16 events, 4 requests, newest first, as of 2026-09-06)

```
   2026-01-16  slack_threads.jsonl  Nadia Okonkwo        R1080 slack: "adding Rafael Salcedo who might know"
   2026-01-14  slack_threads.jsonl  Imani Mkhize         R1080 slack: "wrong channel? this feels like a partner ask"
   2026-01-14  slack_threads.jsonl  Nadia Okonkwo        R1080 slack: "adding Bertrand Vandermolen who might know"
   2026-01-14  slack_threads.jsonl  Hana Nakashima       R1080 slack: "trying to reach VP Engineering at Volney Industrial Systems — anyone have a path?"
   2026-01-14  intro_requests.csv   Hana Nakashima       R1080 raised by Hana Nakashima (AE, Healthcare): wants VP Engineering, $750,000, High urgency, filed "Open"

   2025-12-24  slack_threads.jsonl  Sloane Fairweather   R1073 slack: "adding Nadia Okonkwo who might know"
   2025-12-23  slack_threads.jsonl  Nadia Okonkwo        R1073 slack: "what's the deal size here?"
   2025-12-20  slack_threads.jsonl  Nadia Okonkwo        R1073 slack: "need help getting to Volney Industrial Systems. Anouk Underhill-Hartigan is the Chief Information Officer there, cold outbound is going nowhere"
!! 2025-12-20  intro_requests.csv   Nadia Okonkwo        R1073 raised by Nadia Okonkwo (AE, Industrials): wants Chief Information Officer, $80,000, Low urgency, filed "Closed - no path"  [4 paths in supply_reach.csv]

   2025-12-18  slack_threads.jsonl  Yusuf Petrossian     R1191 slack: "wrong channel? this feels like a partner ask"
   2025-12-15  slack_threads.jsonl  Yusuf Petrossian     R1191 slack: "asking again: Volney Industrial Systems. Chief Digital Officer. Happy to draft the forward myself if someone can vouch."
   2025-12-15  intro_requests.csv   Yusuf Petrossian     R1191 raised by Yusuf Petrossian (SDR Lead): wants Chief Digital Officer, $2,000,000, High urgency, filed "Stalled"

   2025-09-14  slack_threads.jsonl  Nadia Okonkwo        R1002 slack: "wrong channel? this feels like a partner ask"
   2025-09-14  slack_threads.jsonl  Imani Mkhize         R1002 slack: "does anyone know anyone at Volney Industrial Systems? looking for VP Data & Analytics, ideally warm"
   2025-09-14  intro_requests.csv   Imani Mkhize         R1002 raised by Imani Mkhize (Enterprise AE, West): wants VP Data & Analytics, $400,000, High urgency, filed "Open"

!! 2026-01-13  crm_accounts.csv     Yusuf Petrossian     last CRM touch on A1049  [236 days ago, nothing since]
```

## 5. Additional Investor and Operator Network

4 people from investor_network.csv, 4 askable as investor_network paths, 0 with no warm path; a view of section 3 and the roster's exports, nothing here is scored or allocated on its own

| person | role | fund | board seat | source | warm path |
|---|---|---|---|---|---|
| Curtis Sandoval-Glückstein | Private equity investor | Thornbury Equity | yes | portfolio_company | investor_network path (section 3, 10% haircut) |
| Bertrand Achterberg-Quillane | Venture capital investor | Ashgrove Capital | no | portfolio_company | investor_network path (section 3, 10% haircut) |
| Freya Oldfield-Ibarra | Venture capital investor | Ashgrove Capital | no | portfolio_company | investor_network path (section 3, 10% haircut) |
| Priya Dobrescu-Prendergast | Private equity investor | Thornbury Equity | no | portfolio_company | investor_network path (section 3, 10% haircut) |
