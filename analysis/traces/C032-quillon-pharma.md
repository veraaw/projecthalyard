# Quillon Pharma  (C032)

- stage: Closed Lost | industry: Pharma | owner: Rafael Salcedo | deal value: $3,500,000 | largest request: $750,000
- CRM accounts: A1019 (quillonpharma.com)
- also goes by: nothing else
- 2 requests from 2 people wanting 2 different titles: Chief Operating Officer | SVP Digital

## 2. Where the files disagree

- R1198: filed "Closed - no path" but supply_reach.csv has 12 paths into Quillon Pharma
- R1178: filed "Closed - no path" but supply_reach.csv has 12 paths into Quillon Pharma

## 3. Who can reach them

ranked by route score = strength x focus fit x delivery rate, the allocator's sort key

| route score | strength | connector | reach | contact | evidence |
|---|---|---|---|---|---|
| 0.096 | 0.600 | Tomás Beckett (Internal) | direct | Renata Petrossian — Chief Data Officer | connections_beckett.csv: Renata Petrossian, Chief Data Officer at Quillon Pharma, connected 2026-10-13 |
| 0.089 | 0.573 | Marcus Aldridge (Advisor) | direct | Renata Petrossian — Chief Data Officer | connections_aldridge.csv: Renata Petrossian, Chief Data Officer at Quillon Pharma, connected 2025-02-05 |
| 0.062 | 0.546 | Owen Trask (Investor) | direct | Mei Ferreira — Chief Information Officer | connections_trask.csv: Mei Ferreira, Chief Information Officer at Quillon Pharma, connected 2024-08-05 |
| 0.061 | 0.300 | Priya Raghunathan (Investor) | direct | Casper Bellinger — VP Enterprise Architecture | connections_raghunathan.csv: Casper Bellinger, VP Enterprise Architecture at Quillon Pharma, connected 2015-11-21 |
| 0.047 | 0.300 | Marcus Aldridge (Advisor) | direct | Casper Bellinger — VP Enterprise Architecture | connections_aldridge.csv: Casper Bellinger, VP Enterprise Architecture at Quillon Pharma, connected 2014-02-24 |
| 0.038 | 0.187 | Priya Raghunathan (Investor) | alumni | Casper Bellinger — ex-Quillon Pharma (2012-2017), now VP Enterprise Architecture at Quillon Pharma | investor_network.csv: Casper Bellinger prior_employer=Quillon Pharma (2012-2017); connections_raghunathan.csv: connection of Priya Raghunathan since 2015-11-21 |
| 0.029 | 0.187 | Marcus Aldridge (Advisor) | alumni | Casper Bellinger — ex-Quillon Pharma (2012-2017), now VP Enterprise Architecture at Quillon Pharma | investor_network.csv: Casper Bellinger prior_employer=Quillon Pharma (2012-2017); connections_aldridge.csv: connection of Marcus Aldridge since 2014-02-24 |
| 0.028 | 0.248 | Owen Trask (Investor) | direct | Kian Merriweather — VP Engineering | connections_trask.csv: Kian Merriweather, VP Engineering at Quillon Pharma, connected 2016-12-15 |
| 0.021 | 0.187 | Owen Trask (Investor) | alumni | Kian Merriweather — ex-Quillon Pharma (2012-2018), now VP Engineering at Quillon Pharma | investor_network.csv: Kian Merriweather prior_employer=Quillon Pharma (2012-2018); connections_trask.csv: connection of Owen Trask since 2016-12-15 |
| 0.000 | 0.519 | Elena Duvall (Advisor) | direct | Mei Ferreira — Chief Information Officer | connections_duvall.csv: Mei Ferreira, Chief Information Officer at Quillon Pharma, connected 2023-05-10 |
| 0.000 | 0.269 | Elena Duvall (Advisor) | direct | Kian Merriweather — VP Engineering | connections_duvall.csv: Kian Merriweather, VP Engineering at Quillon Pharma, connected 2017-10-15 |
| 0.000 | 0.202 | Elena Duvall (Advisor) | alumni | Kian Merriweather — ex-Quillon Pharma (2012-2018), now VP Engineering at Quillon Pharma | investor_network.csv: Kian Merriweather prior_employer=Quillon Pharma (2012-2018); connections_duvall.csv: connection of Elena Duvall since 2017-10-15 |

## 4. Chronology (10 events, 2 requests, as of 2026-09-06)

```
!! 2025-10-07  intro_requests.csv   Sloane Fairweather   R1198 raised by Sloane Fairweather (Strategic AE): wants Chief Operating Officer, $750,000, Critical urgency, filed "Closed - no path"  [12 paths in supply_reach.csv]
   2025-10-07  slack_threads.jsonl  Sloane Fairweather   R1198 slack: "who do we know at Quillon Pharma? Chief Operating Officer would be ideal but I'll take anyone senior"
   2025-10-09  slack_threads.jsonl  Sloane Fairweather   R1198 slack: "no idea sorry"
   2025-10-10  slack_threads.jsonl  Curtis Hartigan      R1198 slack: "did we not already lose this one?"
   2025-10-11  slack_threads.jsonl  Yusuf Petrossian     R1198 slack: "no idea sorry"

!! 2026-05-16  intro_requests.csv   Bertrand Vandermolen R1178 raised by Bertrand Vandermolen (AE, EMEA): wants SVP Digital, $750,000, High urgency, filed "Closed - no path"  [12 paths in supply_reach.csv]
   2026-05-16  slack_threads.jsonl  Bertrand Vandermolen R1178 slack: "need help getting to Quillon Pharma. Tanvi Eastcott-Lindqvist is the SVP Digital there, cold outbound is going nowhere"
   2026-05-16  slack_threads.jsonl  Nadia Okonkwo        R1178 slack: "did we not already lose this one?"
   2026-05-17  slack_threads.jsonl  Yusuf Petrossian     R1178 slack: "what's the deal size here?"

!! 2025-07-07  crm_accounts.csv     Rafael Salcedo       last CRM touch on A1019  [426 days ago, nothing since]
```

## 5. Additional Investor and Operator Network

5 people from investor_network.csv, 0 askable as investor_network paths, 3 with no warm path; a view of section 3 and the roster's exports, nothing here is scored or allocated on its own

| person | role | fund | board seat | source | warm path |
|---|---|---|---|---|---|
| Casper Bellinger | Operator (work history) |  | no | prior_employer | via Aldridge, Raghunathan |
| Kian Merriweather | Operator (work history) |  | no | prior_employer | via Duvall, Trask |
| Matteo Ferreira-Yarrow | Private equity investor | Ironvale Partners | no | portfolio_company | no warm path |
| Otto Cathcart-Brenneman | Venture capital investor | Ashgrove Capital | no | portfolio_company | no warm path |
| Xiomara Achterberg-Norrington | Growth equity investor | Northgate Growth | no | portfolio_company | no warm path |
