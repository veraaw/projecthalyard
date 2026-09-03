# Join rates across `dataset/`

Every link is measured in both directions under three cumulative normalization tiers:

1. **exact** — byte-for-byte equality of the trimmed value
2. **+ lowercase, no punctuation** — lowercased, all non-alphanumeric characters (including spaces) removed
3. **+ legal suffixes stripped** — tier 2, then trailing `ag`, `bv`, `co`, `company`, `corp`, `corporation`, `gmbh`, `group`, `holding`, `holdings`, `inc`, `incorporated`, `limited`, `llc`, `llp`, `lp`, `ltd`, `nv`, `plc`, `sa` removed

`domain` values are pre-reduced to the host minus `www.` and the TLD before the tiers apply (`ellerbysemi.com` -> `ellerbysemi`), otherwise a name-to-domain join is 0% by construction.

**Match rate (distinct)** = share of distinct values on that side that find at least one counterpart on the other side. **(rows)** = the same measured over every row, so it reflects how much of the actual data joins.

Normalization is not strictly monotonic — suffix stripping loses these matches:

- `intro_requests.target_company_raw -> crm_accounts.domain` (right side): 40.9% -> 38.6% — stripping a suffix on one side removes the token the other side still carries inside a single unsegmented string (e.g. `Apex Holdings` -> `apex` no longer meets `apexlogisticsgroup.co.uk`)

## Summary

| Link | Direction | Exact | +lower/punct | +legal suffix |
| --- | --- | ---: | ---: | ---: |
| intro_requests.target_company_raw -> crm_accounts.account_name | -> (left side matched) | 65.4% | 69.2% | 71.2% |
| | <- (right side matched) | 68.0% | 72.0% | 84.0% |
| intro_requests.target_company_raw -> crm_accounts.domain | -> (left side matched) | 0.0% | 34.6% | 34.6% |
| | <- (right side matched) | 0.0% | 40.9% | 38.6% |
| investor_network.portfolio_company -> crm_accounts.account_name | -> (left side matched) | 65.4% | 69.2% | 73.1% |
| | <- (right side matched) | 34.0% | 36.0% | 44.0% |
| investor_network.prior_employer -> crm_accounts.account_name | -> (left side matched) | 57.1% | 64.3% | 64.3% |
| | <- (right side matched) | 16.0% | 18.0% | 22.0% |
| connections_*.company -> crm_accounts.account_name | -> (left side matched) | 40.0% | 42.0% | 44.0% |
| | <- (right side matched) | 40.0% | 42.0% | 52.0% |
| intro_outcomes.request_id -> intro_requests.request_id | -> (left side matched) | 100.0% | 100.0% | 100.0% |
| | <- (right side matched) | 42.5% | 42.5% | 42.5% |
| intro_outcomes.connector_asked -> connector_roster.name | -> (left side matched) | 54.5% | 54.5% | 54.5% |
| | <- (right side matched) | 100.0% | 100.0% | 100.0% |
| connections_*.company -> intro_requests.target_company_raw | -> (left side matched) | 58.0% | 58.0% | 58.0% |
| | <- (right side matched) | 55.8% | 55.8% | 55.8% |
| investor_network.portfolio_company -> connections_*.company | -> (left side matched) | 84.6% | 84.6% | 84.6% |
| | <- (right side matched) | 44.0% | 44.0% | 46.0% |
| investor_network.person -> connector_roster.name | -> (left side matched) | 2.4% | 2.4% | 2.4% |
| | <- (right side matched) | 16.7% | 16.7% | 16.7% |
| intro_requests.requested_by -> crm_accounts.owner | -> (left side matched) | 100.0% | 100.0% | 100.0% |
| | <- (right side matched) | 100.0% | 100.0% | 100.0% |
| intro_requests.target_person_raw -> connections_*.name | -> (left side matched) | 0.0% | 0.0% | 0.0% |
| | <- (right side matched) | 0.0% | 0.0% | 0.0% |
| connector_roster.connections_file -> connections files on disk | -> (left side matched) | 100.0% | 100.0% | 100.0% |
| | <- (right side matched) | 100.0% | 100.0% | 100.0% |

## intro_requests.target_company_raw -> crm_accounts.account_name

- left `intro_requests.target_company_raw`: 157 rows, 52 distinct
- right `crm_accounts.account_name`: 50 rows, 50 distinct

| Tier | Left matched (distinct) | Left matched (rows) | Right matched (distinct) | Right matched (rows) |
| --- | ---: | ---: | ---: | ---: |
| exact | 65.4% | 63.7% | 68.0% | 68.0% |
| + lowercase, no punctuation | 69.2% | 66.2% | 72.0% | 72.0% |
| + legal suffixes stripped | 71.2% | 67.5% | 84.0% | 84.0% |

Top 15 unmatched on the left by row count (`intro_requests.target_company_raw`, after all three tiers) — 15 unmatched distinct value(s):

- `Kingsmere Retail Group` (7 rows)
- `Strathmore Rail` (7 rows)
- `Vireo Systems` (7 rows)
- `Blackwood Industrial` (4 rows)
- `Marrow Point Airways` (4 rows)
- `Cindermill Mining` (3 rows)
- `Copperline Water` (3 rows)
- `Redtree Foods` (3 rows)
- `Calderon Aerospace` (2 rows)
- `Cobalt Lane` (2 rows)
- `Duncastle Hotels` (2 rows)
- `Meridian Peak Foods` (2 rows)
- `Silverbrook` (2 rows)
- `Thornbury` (2 rows)
- `Meridian Peak` (1 row)

Top 8 unmatched on the right by row count (`crm_accounts.account_name`, after all three tiers) — 8 unmatched distinct value(s):

- `Apex Holdings` (1 row)
- `Blackwood Holdings` (1 row)
- `Cindermill Holdings` (1 row)
- `Duncastle Holdings` (1 row)
- `Falkirk Shipping` (1 row)
- `Ferrowick Insurance` (1 row)
- `Meridian Holdings` (1 row)
- `Strathmore Holdings` (1 row)

## intro_requests.target_company_raw -> crm_accounts.domain

- left `intro_requests.target_company_raw`: 157 rows, 52 distinct
- right `crm_accounts.domain`: 50 rows, 44 distinct (pre-reduced: host minus www/TLD)

| Tier | Left matched (distinct) | Left matched (rows) | Right matched (distinct) | Right matched (rows) |
| --- | ---: | ---: | ---: | ---: |
| exact | 0.0% | 0.0% | 0.0% | 0.0% |
| + lowercase, no punctuation | 34.6% | 41.4% | 40.9% | 42.0% |
| + legal suffixes stripped | 34.6% | 41.4% | 38.6% | 40.0% |

Top 20 unmatched on the left by row count (`intro_requests.target_company_raw`, after all three tiers) — 34 unmatched distinct value(s):

- `Gravenhurst Motors` (9 rows)
- `Priorwood Chemicals` (9 rows)
- `Kingsmere Retail Group` (7 rows)
- `Vireo Systems` (7 rows)
- `Marrow Point Airways` (4 rows)
- `Ravensmoor Defense` (4 rows)
- `Sablefield Motors` (4 rows)
- `Volney Industrial Systems` (4 rows)
- `Cindermill Mining` (3 rows)
- `Copperline Water` (3 rows)
- `Nortonbury Logistics` (3 rows)
- `Redtree Foods` (3 rows)
- `Calderon Aerospace` (2 rows)
- `Cobalt Lane` (2 rows)
- `Duncastle Hotels` (2 rows)
- `Hollowbrook Grocers` (2 rows)
- `Larchmont Aerospace` (2 rows)
- `Larkhall Software` (2 rows)
- `Silverbrook` (2 rows)
- `Thornbury` (2 rows)

Top 20 unmatched on the right by row count (`crm_accounts.domain`, after all three tiers) — 27 unmatched distinct value(s):

- `ashgroveag.com` (2 rows)
- `ellerbysemi.com` (2 rows)
- `hollowbrook.com` (2 rows)
- `aldergate.com` (1 row)
- `apexlogisticsgroup.co.uk` (1 row)
- `bexleybio.com` (1 row)
- `cindermill.com` (1 row)
- `cobaltlanecm.com` (1 row)
- `duncastle.com` (1 row)
- `falkirkshipping.com` (1 row)
- `ferrowick.com` (1 row)
- `flykestrel.com` (1 row)
- `gravenhurst.com` (1 row)
- `larchmontaero.com` (1 row)
- `larkhall.io` (1 row)
- `marlowefreight.com` (1 row)
- `nortonbury.com` (1 row)
- `pelhambev.com` (1 row)
- `priorwood.com` (1 row)
- `ravensmoor.com` (1 row)

## investor_network.portfolio_company -> crm_accounts.account_name

- left `investor_network.portfolio_company`: 53 rows, 26 distinct
- right `crm_accounts.account_name`: 50 rows, 50 distinct

| Tier | Left matched (distinct) | Left matched (rows) | Right matched (distinct) | Right matched (rows) |
| --- | ---: | ---: | ---: | ---: |
| exact | 65.4% | 71.7% | 34.0% | 34.0% |
| + lowercase, no punctuation | 69.2% | 73.6% | 36.0% | 36.0% |
| + legal suffixes stripped | 73.1% | 75.5% | 44.0% | 44.0% |

Top 7 unmatched on the left by row count (`investor_network.portfolio_company`, after all three tiers) — 7 unmatched distinct value(s):

- `Duncastle Hotels` (5 rows)
- `Redtree Foods` (2 rows)
- `Vireo Systems` (2 rows)
- `Blackwood Industrial` (1 row)
- `Cindermill Mining` (1 row)
- `Meridian Peak Foods` (1 row)
- `Strathmore Rail` (1 row)

Top 20 unmatched on the right by row count (`crm_accounts.account_name`, after all three tiers) — 28 unmatched distinct value(s):

- `Aldergate Telecom` (1 row)
- `Apex Holdings` (1 row)
- `Ashgrove Agriculture` (1 row)
- `Ashgrove Agriculture Inc` (1 row)
- `Blackwood Holdings` (1 row)
- `Brightmoor Energy` (1 row)
- `Brightmoor Energy Inc` (1 row)
- `Cindermill Holdings` (1 row)
- `Duncastle Holdings` (1 row)
- `Ferrowick Insurance` (1 row)
- `Halcyon Grid` (1 row)
- `Harrowgate Health` (1 row)
- `Larchmont Aerospace` (1 row)
- `Larkhall Software` (1 row)
- `Marchford Clinics` (1 row)
- `Meridian Holdings` (1 row)
- `Northwind Freight` (1 row)
- `Pelham Beverage` (1 row)
- `Pemberton Retail` (1 row)
- `Ravensmoor Defense` (1 row)

## investor_network.prior_employer -> crm_accounts.account_name

- left `investor_network.prior_employer`: 20 rows, 14 distinct
- right `crm_accounts.account_name`: 50 rows, 50 distinct

| Tier | Left matched (distinct) | Left matched (rows) | Right matched (distinct) | Right matched (rows) |
| --- | ---: | ---: | ---: | ---: |
| exact | 57.1% | 55.0% | 16.0% | 16.0% |
| + lowercase, no punctuation | 64.3% | 60.0% | 18.0% | 18.0% |
| + legal suffixes stripped | 64.3% | 60.0% | 22.0% | 22.0% |

Top 5 unmatched on the left by row count (`investor_network.prior_employer`, after all three tiers) — 5 unmatched distinct value(s):

- `Strathmore Rail` (3 rows)
- `Redtree Foods` (2 rows)
- `Blackwood Industrial` (1 row)
- `Cindermill Mining` (1 row)
- `Kingsmere Retail Group` (1 row)

Top 20 unmatched on the right by row count (`crm_accounts.account_name`, after all three tiers) — 39 unmatched distinct value(s):

- `Aldergate Telecom` (1 row)
- `Apex Holdings` (1 row)
- `Apex Logistics` (1 row)
- `Apex Logistics, Inc.` (1 row)
- `Ashgrove Agriculture` (1 row)
- `Ashgrove Agriculture Inc` (1 row)
- `Bexley Bioworks` (1 row)
- `Blackwood Holdings` (1 row)
- `Cindermill Holdings` (1 row)
- `Cobalt Lane Capital Markets` (1 row)
- `Duncastle Holdings` (1 row)
- `Falkirk Shipping` (1 row)
- `Ferrowick Insurance` (1 row)
- `Glasspoint Health` (1 row)
- `Halcyon Grid` (1 row)
- `Hollowbrook Grocers` (1 row)
- `Hollowbrook Grocers Inc.` (1 row)
- `Kestrel Airlines` (1 row)
- `Larchmont Aerospace` (1 row)
- `Larkhall Software` (1 row)

## connections_*.company -> crm_accounts.account_name

- left `connections_*.company`: 5075 rows, 50 distinct
- right `crm_accounts.account_name`: 50 rows, 50 distinct

| Tier | Left matched (distinct) | Left matched (rows) | Right matched (distinct) | Right matched (rows) |
| --- | ---: | ---: | ---: | ---: |
| exact | 40.0% | 1.3% | 40.0% | 40.0% |
| + lowercase, no punctuation | 42.0% | 1.3% | 42.0% | 42.0% |
| + legal suffixes stripped | 44.0% | 1.3% | 52.0% | 52.0% |

Top 20 unmatched on the left by row count (`connections_*.company`, after all three tiers) — 28 unmatched distinct value(s):

- `Tannerly Design` (291 rows)
- `Inglenook Bakery` (279 rows)
- `Corbridge Realty` (271 rows)
- `Whitlock Staffing` (261 rows)
- `Bellchamber Media` (253 rows)
- `Elmsworth Tutors` (253 rows)
- `Dunmowe Travel` (252 rows)
- `Fairbourne Fitness` (251 rows)
- `Vespermill Analytics` (250 rows)
- `Ambrose Trading` (248 rows)
- `Rooksby Legal` (244 rows)
- `Underwood & Vale` (244 rows)
- `Zenner Foods` (244 rows)
- `Yardley Print` (242 rows)
- `Highmoor Cycles` (238 rows)
- `Ondermark Consulting` (238 rows)
- `Quintrell Advisory` (238 rows)
- `Pale Harbour Studio` (232 rows)
- `Xanthe Labs` (229 rows)
- `Garrowby Books` (217 rows)

Top 20 unmatched on the right by row count (`crm_accounts.account_name`, after all three tiers) — 24 unmatched distinct value(s):

- `Aldergate Telecom` (1 row)
- `Apex Holdings` (1 row)
- `Ashgrove Agriculture` (1 row)
- `Ashgrove Agriculture Inc` (1 row)
- `Blackwood Holdings` (1 row)
- `Cindermill Holdings` (1 row)
- `Duncastle Holdings` (1 row)
- `Ferrowick Insurance` (1 row)
- `Halcyon Grid` (1 row)
- `Kestrel Airlines` (1 row)
- `Larchmont Aerospace` (1 row)
- `Larkhall Software` (1 row)
- `Meridian Holdings` (1 row)
- `Northwind Freight` (1 row)
- `Osric Networks` (1 row)
- `Pelham Beverage` (1 row)
- `Pemberton Retail` (1 row)
- `Ravensmoor Defense` (1 row)
- `Sablefield Motors` (1 row)
- `Strathmore Holdings` (1 row)

## intro_outcomes.request_id -> intro_requests.request_id

- left `intro_outcomes.request_id`: 85 rows, 85 distinct
- right `intro_requests.request_id`: 200 rows, 200 distinct

| Tier | Left matched (distinct) | Left matched (rows) | Right matched (distinct) | Right matched (rows) |
| --- | ---: | ---: | ---: | ---: |
| exact | 100.0% | 100.0% | 42.5% | 42.5% |
| + lowercase, no punctuation | 100.0% | 100.0% | 42.5% | 42.5% |
| + legal suffixes stripped | 100.0% | 100.0% | 42.5% | 42.5% |

Top 0 unmatched on the left by row count (`intro_outcomes.request_id`, after all three tiers) — 0 unmatched distinct value(s):

_none_

Top 20 unmatched on the right by row count (`intro_requests.request_id`, after all three tiers) — 115 unmatched distinct value(s):

- `R1001` (1 row)
- `R1002` (1 row)
- `R1004` (1 row)
- `R1005` (1 row)
- `R1006` (1 row)
- `R1007` (1 row)
- `R1009` (1 row)
- `R1010` (1 row)
- `R1011` (1 row)
- `R1013` (1 row)
- `R1014` (1 row)
- `R1016` (1 row)
- `R1017` (1 row)
- `R1018` (1 row)
- `R1019` (1 row)
- `R1021` (1 row)
- `R1023` (1 row)
- `R1024` (1 row)
- `R1027` (1 row)
- `R1028` (1 row)

## intro_outcomes.connector_asked -> connector_roster.name

- left `intro_outcomes.connector_asked`: 85 rows, 11 distinct
- right `connector_roster.name`: 6 rows, 6 distinct

| Tier | Left matched (distinct) | Left matched (rows) | Right matched (distinct) | Right matched (rows) |
| --- | ---: | ---: | ---: | ---: |
| exact | 54.5% | 94.1% | 100.0% | 100.0% |
| + lowercase, no punctuation | 54.5% | 94.1% | 100.0% | 100.0% |
| + legal suffixes stripped | 54.5% | 94.1% | 100.0% | 100.0% |

Top 5 unmatched on the left by row count (`intro_outcomes.connector_asked`, after all three tiers) — 5 unmatched distinct value(s):

- `Bertrand Vandermolen` (1 row)
- `Curtis Hartigan` (1 row)
- `Hana Nakashima` (1 row)
- `Imani Mkhize` (1 row)
- `Yusuf Petrossian` (1 row)

Top 0 unmatched on the right by row count (`connector_roster.name`, after all three tiers) — 0 unmatched distinct value(s):

_none_

## connections_*.company -> intro_requests.target_company_raw

- left `connections_*.company`: 5075 rows, 50 distinct
- right `intro_requests.target_company_raw`: 157 rows, 52 distinct

| Tier | Left matched (distinct) | Left matched (rows) | Right matched (distinct) | Right matched (rows) |
| --- | ---: | ---: | ---: | ---: |
| exact | 58.0% | 1.9% | 55.8% | 63.1% |
| + lowercase, no punctuation | 58.0% | 1.9% | 55.8% | 63.1% |
| + legal suffixes stripped | 58.0% | 1.9% | 55.8% | 63.1% |

Top 20 unmatched on the left by row count (`connections_*.company`, after all three tiers) — 21 unmatched distinct value(s):

- `Tannerly Design` (291 rows)
- `Inglenook Bakery` (279 rows)
- `Corbridge Realty` (271 rows)
- `Whitlock Staffing` (261 rows)
- `Bellchamber Media` (253 rows)
- `Elmsworth Tutors` (253 rows)
- `Dunmowe Travel` (252 rows)
- `Fairbourne Fitness` (251 rows)
- `Vespermill Analytics` (250 rows)
- `Ambrose Trading` (248 rows)
- `Rooksby Legal` (244 rows)
- `Underwood & Vale` (244 rows)
- `Zenner Foods` (244 rows)
- `Yardley Print` (242 rows)
- `Highmoor Cycles` (238 rows)
- `Ondermark Consulting` (238 rows)
- `Quintrell Advisory` (238 rows)
- `Pale Harbour Studio` (232 rows)
- `Xanthe Labs` (229 rows)
- `Garrowby Books` (217 rows)

Top 20 unmatched on the right by row count (`intro_requests.target_company_raw`, after all three tiers) — 23 unmatched distinct value(s):

- `Northwind Freight` (5 rows)
- `Thistledown Energy` (5 rows)
- `Marrow Point Airways` (4 rows)
- `Pemberton Retail` (4 rows)
- `Ravensmoor Defense` (4 rows)
- `Sablefield Motors` (4 rows)
- `Volney Industrial Systems` (4 rows)
- `Copperline Water` (3 rows)
- `Osric Networks` (3 rows)
- `Cobalt Lane` (2 rows)
- `Duncastle Hotels` (2 rows)
- `Halcyon Grid` (2 rows)
- `Larchmont Aerospace` (2 rows)
- `Larkhall Software` (2 rows)
- `Silverbrook` (2 rows)
- `Thornbury` (2 rows)
- `Thornbury Financial` (2 rows)
- `Aldergate Telecom` (1 row)
- `Ashgrove Agriculture` (1 row)
- `Kestrel Airlines` (1 row)

## investor_network.portfolio_company -> connections_*.company

- left `investor_network.portfolio_company`: 53 rows, 26 distinct
- right `connections_*.company`: 5075 rows, 50 distinct

| Tier | Left matched (distinct) | Left matched (rows) | Right matched (distinct) | Right matched (rows) |
| --- | ---: | ---: | ---: | ---: |
| exact | 84.6% | 73.6% | 44.0% | 1.5% |
| + lowercase, no punctuation | 84.6% | 73.6% | 44.0% | 1.5% |
| + legal suffixes stripped | 84.6% | 73.6% | 46.0% | 1.5% |

Top 4 unmatched on the left by row count (`investor_network.portfolio_company`, after all three tiers) — 4 unmatched distinct value(s):

- `Duncastle Hotels` (5 rows)
- `Volney Industrial Systems` (4 rows)
- `Osric Networks` (3 rows)
- `Kestrel Airlines` (2 rows)

Top 20 unmatched on the right by row count (`connections_*.company`, after all three tiers) — 27 unmatched distinct value(s):

- `Tannerly Design` (291 rows)
- `Inglenook Bakery` (279 rows)
- `Corbridge Realty` (271 rows)
- `Whitlock Staffing` (261 rows)
- `Bellchamber Media` (253 rows)
- `Elmsworth Tutors` (253 rows)
- `Dunmowe Travel` (252 rows)
- `Fairbourne Fitness` (251 rows)
- `Vespermill Analytics` (250 rows)
- `Ambrose Trading` (248 rows)
- `Rooksby Legal` (244 rows)
- `Underwood & Vale` (244 rows)
- `Zenner Foods` (244 rows)
- `Yardley Print` (242 rows)
- `Highmoor Cycles` (238 rows)
- `Ondermark Consulting` (238 rows)
- `Quintrell Advisory` (238 rows)
- `Pale Harbour Studio` (232 rows)
- `Xanthe Labs` (229 rows)
- `Garrowby Books` (217 rows)

## investor_network.person -> connector_roster.name

- left `investor_network.person`: 73 rows, 42 distinct
- right `connector_roster.name`: 6 rows, 6 distinct

| Tier | Left matched (distinct) | Left matched (rows) | Right matched (distinct) | Right matched (rows) |
| --- | ---: | ---: | ---: | ---: |
| exact | 2.4% | 11.0% | 16.7% | 16.7% |
| + lowercase, no punctuation | 2.4% | 11.0% | 16.7% | 16.7% |
| + legal suffixes stripped | 2.4% | 11.0% | 16.7% | 16.7% |

Top 20 unmatched on the left by row count (`investor_network.person`, after all three tiers) — 41 unmatched distinct value(s):

- `Amara Brenneman-Fairweather` (4 rows)
- `Freya Oldfield-Ibarra` (4 rows)
- `Matteo Ferreira-Yarrow` (4 rows)
- `Espen Rushworth-Oyelaran` (3 rows)
- `Matteo Falkenrath-Merriweather` (3 rows)
- `Otto Cathcart-Brenneman` (3 rows)
- `Perrine Brenneman-Wexford` (3 rows)
- `Renata Halloran-Quillane` (3 rows)
- `Arjun Fairweather-Brenneman` (2 rows)
- `Bertrand Achterberg-Quillane` (2 rows)
- `Malik Thackeray-Okonkwo` (2 rows)
- `Otto Højgaard-Ferreira` (2 rows)
- `Priya Dobrescu-Prendergast` (2 rows)
- `Amara Thackeray` (1 row)
- `Bertrand Glückstein` (1 row)
- `Bertrand Lomsadze` (1 row)
- `Callum Oldfield-Fairweather` (1 row)
- `Camille Merriweather-Balogun` (1 row)
- `Casper Bellinger` (1 row)
- `Coretta Bellinger` (1 row)

Top 5 unmatched on the right by row count (`connector_roster.name`, after all three tiers) — 5 unmatched distinct value(s):

- `Dana Whitfield` (1 row)
- `Elena Duvall` (1 row)
- `Marcus Aldridge` (1 row)
- `Owen Trask` (1 row)
- `Tomás Beckett` (1 row)

## intro_requests.requested_by -> crm_accounts.owner

- left `intro_requests.requested_by`: 200 rows, 8 distinct
- right `crm_accounts.owner`: 50 rows, 8 distinct

| Tier | Left matched (distinct) | Left matched (rows) | Right matched (distinct) | Right matched (rows) |
| --- | ---: | ---: | ---: | ---: |
| exact | 100.0% | 100.0% | 100.0% | 100.0% |
| + lowercase, no punctuation | 100.0% | 100.0% | 100.0% | 100.0% |
| + legal suffixes stripped | 100.0% | 100.0% | 100.0% | 100.0% |

Top 0 unmatched on the left by row count (`intro_requests.requested_by`, after all three tiers) — 0 unmatched distinct value(s):

_none_

Top 0 unmatched on the right by row count (`crm_accounts.owner`, after all three tiers) — 0 unmatched distinct value(s):

_none_

## intro_requests.target_person_raw -> connections_*.name

- left `intro_requests.target_person_raw`: 46 rows, 46 distinct
- right `connections_*.name`: 5075 rows, 5030 distinct

| Tier | Left matched (distinct) | Left matched (rows) | Right matched (distinct) | Right matched (rows) |
| --- | ---: | ---: | ---: | ---: |
| exact | 0.0% | 0.0% | 0.0% | 0.0% |
| + lowercase, no punctuation | 0.0% | 0.0% | 0.0% | 0.0% |
| + legal suffixes stripped | 0.0% | 0.0% | 0.0% | 0.0% |

Top 20 unmatched on the left by row count (`intro_requests.target_person_raw`, after all three tiers) — 46 unmatched distinct value(s):

- `Amara Kettleborough-Højgaard` (1 row)
- `Anouk Norrington-Brenneman` (1 row)
- `Arjun Lindqvist-Lomsadze` (1 row)
- `Astrid Kirkbride-Norrington` (1 row)
- `Astrid Quillane-Brenneman` (1 row)
- `Desmond Wexford-Norrington` (1 row)
- `Elena Bellinger-Havercamp` (1 row)
- `Emeka Underhill-Zubkov` (1 row)
- `Espen Wolstenholme-Vandermolen` (1 row)
- `Freya Havercamp-Drummond` (1 row)
- `Freya Thackeray-Underhill` (1 row)
- `Gideon Fontaine-Crowther` (1 row)
- `Hugo Norrington-Isenberg` (1 row)
- `Ilse Oldfield-Dobrescu` (1 row)
- `Ilse Oyelaran-Zettergren` (1 row)
- `Ilse Wolstenholme-Oyelaran` (1 row)
- `Imani Kettleborough-Ibarra` (1 row)
- `Imani Salcedo-Prendergast` (1 row)
- `Leandro Okonkwo-Oldfield` (1 row)
- `Malik Højgaard-Ferreira` (1 row)

Top 20 unmatched on the right by row count (`connections_*.name`, after all three tiers) — 5030 unmatched distinct value(s):

- `Amara Thackeray` (2 rows)
- `Anouk Kirkbride` (2 rows)
- `Arjun Cathcart` (2 rows)
- `Bertrand Cardoso` (2 rows)
- `Bertrand Glückstein` (2 rows)
- `Bertrand Lomsadze` (2 rows)
- `Bo Marchetti` (2 rows)
- `Bram Quillane` (2 rows)
- `Camille Fairweather` (2 rows)
- `Casper Bellinger` (2 rows)
- `Curtis Marchetti` (2 rows)
- `Curtis Prendergast` (2 rows)
- `Desmond Cardoso` (2 rows)
- `Espen Zettergren` (2 rows)
- `Freya Havercamp` (2 rows)
- `Greta Petrossian` (2 rows)
- `Ilse Mkhize` (2 rows)
- `Ingrid Marchetti` (2 rows)
- `Kian Merriweather` (2 rows)
- `Kofi Mkhize` (2 rows)

## connector_roster.connections_file -> connections files on disk

- left `connector_roster.connections_file`: 6 rows, 6 distinct
- right `dataset/*.csv filenames`: 6 rows, 6 distinct

| Tier | Left matched (distinct) | Left matched (rows) | Right matched (distinct) | Right matched (rows) |
| --- | ---: | ---: | ---: | ---: |
| exact | 100.0% | 100.0% | 100.0% | 100.0% |
| + lowercase, no punctuation | 100.0% | 100.0% | 100.0% | 100.0% |
| + legal suffixes stripped | 100.0% | 100.0% | 100.0% | 100.0% |

Top 0 unmatched on the left by row count (`connector_roster.connections_file`, after all three tiers) — 0 unmatched distinct value(s):

_none_

Top 0 unmatched on the right by row count (`dataset/*.csv filenames`, after all three tiers) — 0 unmatched distinct value(s):

_none_
