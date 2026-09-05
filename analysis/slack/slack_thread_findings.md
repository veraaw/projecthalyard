# `dataset/slack_threads.jsonl` findings

200 threads, 523 messages, 323 replies (messages after the opening request).

## 1. Distinct reply texts after name masking

- Distinct masked reply texts: **18**
- Replies that repeat a text seen more than once: **316 / 323 (97.8%)**
- The top 7 masked texts alone account for 274 replies (84.8%).

| Masked reply text | Count |
| --- | ---: |
| no idea sorry | 44 |
| did we not already lose this one? | 43 |
| what's the deal size here? | 40 |
| wrong channel? this feels like a partner ask | 38 |
| I think their procurement is frozen until Q1 | 38 |
| is this the same as the one from last month? | 37 |
| adding <NAME> who might know | 34 |
| bumping this | 32 |
| their Head of Platform reports to someone I've known for a decade, leave it with me | 5 |
| I'll take this one — I've got a direct line to their exec team | 3 |
| I met their Chief Data Officer at a conference last spring, happy to reach out | 2 |
| I met their VP Enterprise Architecture at a conference last spring, happy to reach out | 1 |
| careful — Redtree Capital (fund) and Redtree Foods (operating co) are completely different companies | 1 |
| careful — Ironvale Partners (fund) and Ironvale Steel (operating co) are completely different companies | 1 |
| I met their Chief Digital Officer at a conference last spring, happy to reach out | 1 |
| I met their Chief Operating Officer at a conference last spring, happy to reach out | 1 |
| I met their Chief Information Officer at a conference last spring, happy to reach out | 1 |
| I know <NAME>-Drummond there well, happy to intro | 1 |

## 2. Replies offering to help

15 replies across 15 threads.

| request_id | Person | Reply |
| --- | --- | --- |
| R1003 | Dana Whitfield | I met their VP Enterprise Architecture at a conference last spring, happy to reach out |
| R1034 | Nadia Okonkwo | their Head of Platform reports to someone I've known for a decade, leave it with me |
| R1066 | Yusuf Petrossian | I'll take this one — I've got a direct line to their exec team |
| R1108 | Hana Nakashima | I met their Chief Digital Officer at a conference last spring, happy to reach out |
| R1109 | Owen Trask | their Head of Platform reports to someone I've known for a decade, leave it with me |
| R1115 | Priya Raghunathan | their Head of Platform reports to someone I've known for a decade, leave it with me |
| R1122 | Curtis Hartigan | I met their Chief Data Officer at a conference last spring, happy to reach out |
| R1124 | Priya Raghunathan | I met their Chief Operating Officer at a conference last spring, happy to reach out |
| R1130 | Tomás Beckett | I'll take this one — I've got a direct line to their exec team |
| R1136 | Elena Duvall | their Head of Platform reports to someone I've known for a decade, leave it with me |
| R1163 | Elena Duvall | I met their Chief Data Officer at a conference last spring, happy to reach out |
| R1167 | Priya Raghunathan | I'll take this one — I've got a direct line to their exec team |
| R1169 | Bertrand Vandermolen | I met their Chief Information Officer at a conference last spring, happy to reach out |
| R1176 | Imani Mkhize | their Head of Platform reports to someone I've known for a decade, leave it with me |
| R1187 | Priya Raghunathan | I know Kwame Marchetti-Drummond there well, happy to intro |

## 3. Offers never logged as asked in `intro_outcomes.csv`

**4 of 15** offers have no matching `connector_asked` row for that request.

| request_id | Offered by | deal_value_usd | request status | Reply |
| --- | --- | ---: | --- | --- |
| R1034 | Nadia Okonkwo | 400000 | Open | their Head of Platform reports to someone I've known for a decade, leave it with me |
| R1109 | Owen Trask | 150000 | Closed - no path | their Head of Platform reports to someone I've known for a decade, leave it with me |
| R1115 | Priya Raghunathan | 2000000 | Intro sent | their Head of Platform reports to someone I've known for a decade, leave it with me |
| R1136 | Elena Duvall | 1200000 | Open | their Head of Platform reports to someone I've known for a decade, leave it with me |

Total deal value attached to those requests: $3,750,000

## 4. "adding X who might know"

34 such replies naming 8 distinct people; the named person was subsequently logged as asked on that request in **0** case(s).
- Distinct people added who are on `connector_roster.csv`: **0 / 8**
- Replies whose X is a roster connector: **0 / 34**

| Person added | Times added | On roster? | Later asked (on that request) |
| --- | ---: | --- | ---: |
| Rafael Salcedo | 7 | no | 0 |
| Curtis Hartigan | 5 | no | 0 |
| Yusuf Petrossian | 5 | no | 0 |
| Nadia Okonkwo | 5 | no | 0 |
| Sloane Fairweather | 4 | no | 0 |
| Bertrand Vandermolen | 4 | no | 0 |
| Imani Mkhize | 2 | no | 0 |
| Hana Nakashima | 2 | no | 0 |

| request_id | Person added | Later asked? |
| --- | --- | --- |
| R1001 | Curtis Hartigan | no |
| R1017 | Rafael Salcedo | no |
| R1024 | Rafael Salcedo | no |
| R1025 | Bertrand Vandermolen | no |
| R1025 | Sloane Fairweather | no |
| R1027 | Yusuf Petrossian | no |
| R1033 | Nadia Okonkwo | no |
| R1034 | Nadia Okonkwo | no |
| R1040 | Sloane Fairweather | no |
| R1048 | Curtis Hartigan | no |
| R1049 | Imani Mkhize | no |
| R1055 | Imani Mkhize | no |
| R1058 | Curtis Hartigan | no |
| R1061 | Nadia Okonkwo | no |
| R1061 | Rafael Salcedo | no |
| R1062 | Rafael Salcedo | no |
| R1072 | Sloane Fairweather | no |
| R1073 | Nadia Okonkwo | no |
| R1080 | Bertrand Vandermolen | no |
| R1080 | Rafael Salcedo | no |
| R1084 | Hana Nakashima | no |
| R1086 | Hana Nakashima | no |
| R1093 | Bertrand Vandermolen | no |
| R1098 | Sloane Fairweather | no |
| R1113 | Nadia Okonkwo | no |
| R1116 | Curtis Hartigan | no |
| R1131 | Yusuf Petrossian | no |
| R1148 | Rafael Salcedo | no |
| R1148 | Yusuf Petrossian | no |
| R1160 | Bertrand Vandermolen | no |
| R1161 | Yusuf Petrossian | no |
| R1190 | Curtis Hartigan | no |
| R1193 | Yusuf Petrossian | no |
| R1197 | Rafael Salcedo | no |

## 5. Threads with no reply

- Threads with zero replies: **43** of 200
- Of those, requests that were asked anyway (appear in `intro_outcomes.csv`): **18**

| request_id | Connector(s) asked | deal_value_usd | status |
| --- | --- | ---: | --- |
| R1020 | Tomás Beckett | 750000 | Intro sent |
| R1029 | Elena Duvall | 150000 | Stalled |
| R1045 | Marcus Aldridge | 750000 | Closed - no path |
| R1046 | Priya Raghunathan | 80000 | Open |
| R1053 | Marcus Aldridge | 400000 | Stalled |
| R1060 | Elena Duvall | 80000 | Open |
| R1068 | Priya Raghunathan | 150000 | Closed - no path |
| R1069 | Marcus Aldridge | 1200000 | Closed - no path |
| R1077 | Marcus Aldridge | 750000 | Open |
| R1094 | Marcus Aldridge | 750000 | Open |
| R1095 | Marcus Aldridge | 750000 | Open |
| R1135 | Priya Raghunathan | 750000 | Open |
| R1147 | Dana Whitfield | 1200000 | Closed - no path |
| R1156 | Priya Raghunathan | 1200000 | Routed |
| R1166 | Elena Duvall | 750000 | Closed - no path |
| R1172 | Priya Raghunathan | 150000 | Intro sent |
| R1185 | Priya Raghunathan | 1200000 | Stalled |
| R1196 | Tomás Beckett | 1200000 | Stalled |

## 6. Time to first reply

- Threads with at least one reply: 157
- Median: **27.2 hours**
- Mean 35.7 h, min 1.2 h, max 105.3 h

## Caveats

- `intro_outcomes.csv` has 85 rows, one per request_id, so "asked" is single-connector per request: a second person offering on a thread can never appear.
- The 6 roster connectors account for 80 of those rows; the other 5 are non-roster people (Bertrand Vandermolen, Curtis Hartigan, Hana Nakashima, Imani Mkhize, Yusuf Petrossian) — each appears exactly once, and each is someone who offered on a thread.
- Everyone named in "adding X who might know" is a CRM account owner / AE, not a roster connector, which is why the follow-through rate is 0.
