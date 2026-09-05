# Repeat target companies in `dataset/intro_requests.csv`

180 of 200 requests resolve (via `golden/golden_requests.csv`) to 48 companies; **39** companies appear in 2+ requests (171 requests). The other 20 requests name a person but no identifiable company (R1011, R1012, R1020, R1044, R1046, R1051, R1056, R1079, R1085, R1087, R1088, R1095, R1096, R1106, R1110, R1112, R1119, R1126, R1145, R1181) and are excluded.

Only 46 of 200 requests name a `target_person_raw`; the other 154 give a title only. "Target" below therefore means the named person when there is one, otherwise the title. The strict named-person view (blank counts as its own value) is shown second.

## Same person or different people?

Per company, comparing **person if named, else title**:

| Pattern | Companies | Requests |
| --- | ---: | ---: |
| Every request wants the **same** target | 0 | 0 |
| Every request wants a **different** target | 28 | 104 |
| Mixed (some repeats, some new) | 11 | 67 |

Per request pair within a company (374 pairs): **14** pairs want the same target, **360** want different targets.

<details><summary>Strict view: <code>target_person_raw</code> only (blank treated as one value)</summary>

Per company, comparing **`target_person_raw` verbatim**:

| Pattern | Companies | Requests |
| --- | ---: | ---: |
| Every request wants the **same** target | 15 | 55 |
| Every request wants a **different** target | 5 | 11 |
| Mixed (some repeats, some new) | 19 | 105 |

Per request pair within a company (374 pairs): **248** pairs want the same target, **126** want different targets.

</details>

| Company | Requests | Distinct targets | Named people | Distinct titles | Pattern |
| --- | ---: | ---: | ---: | ---: | --- |
| Gravenhurst Motors | 9 | 8 | 3 | 8 | mixed |
| Harrowgate Health | 9 | 7 | 1 | 6 | mixed |
| Priorwood Chemicals | 9 | 8 | 1 | 7 | mixed |
| Vireo Systems | 9 | 9 | 3 | 6 | different |
| Kingsmere Retail Group | 8 | 6 | 1 | 5 | mixed |
| Strathmore Holdings | 7 | 5 | 0 | 5 | mixed |
| Marchford Clinics | 6 | 6 | 1 | 6 | different |
| Thistledown Energy | 6 | 6 | 2 | 6 | different |
| Brightmoor Energy | 5 | 4 | 0 | 4 | mixed |
| Duncastle Holdings | 5 | 4 | 1 | 4 | mixed |
| Ironvale Steel | 5 | 4 | 1 | 3 | mixed |
| Marrow Point Airways | 5 | 5 | 0 | 5 | different |
| Northwind Freight | 5 | 5 | 2 | 5 | different |
| Sablefield Motors | 5 | 5 | 1 | 4 | different |
| Apex Logistics | 4 | 4 | 0 | 4 | different |
| Blackwood Holdings | 4 | 4 | 1 | 3 | different |
| Cindermill Holdings | 4 | 4 | 0 | 4 | different |
| Hollowbrook Grocers | 4 | 3 | 0 | 3 | mixed |
| Larchmont Aerospace | 4 | 4 | 0 | 4 | different |
| Osric Networks | 4 | 4 | 1 | 4 | different |
| Pemberton Retail | 4 | 4 | 1 | 3 | different |
| Ravensmoor Defense | 4 | 4 | 0 | 4 | different |
| Redtree Foods | 4 | 4 | 1 | 4 | different |
| Volney Industrial Systems | 4 | 4 | 1 | 4 | different |
| Apex Holdings | 3 | 3 | 1 | 3 | different |
| Copperline Water | 3 | 3 | 1 | 3 | different |
| Halcyon Grid | 3 | 3 | 0 | 3 | different |
| Marlowe Freight Systems | 3 | 3 | 1 | 3 | different |
| Nortonbury Logistics | 3 | 2 | 0 | 2 | mixed |
| Pelham Beverage | 3 | 2 | 0 | 2 | mixed |
| Thornbury Financial | 3 | 3 | 2 | 2 | different |
| Wrenfield Robotics | 3 | 3 | 0 | 3 | different |
| Calderon Aerospace | 2 | 2 | 0 | 2 | different |
| Cobalt Lane Capital Markets | 2 | 2 | 0 | 2 | different |
| Larkhall Software | 2 | 2 | 1 | 2 | different |
| Meridian Holdings | 2 | 2 | 1 | 1 | different |
| Quillon Pharma | 2 | 2 | 0 | 2 | different |
| Silverbrook Paper | 2 | 2 | 1 | 2 | different |
| Vantage Ridge Utilities | 2 | 2 | 1 | 1 | different |

## Top five companies by request count

### Gravenhurst Motors (C016) — 9 requests, 8 distinct titles, 3 named people

Distinct titles: Chief Data Officer; Chief Digital Officer; Chief Operating Officer; Director of Software Engineering; Head of Platform Engineering; SVP Digital; VP Engineering; VP Enterprise Architecture

| Title | Person | Requests |
| --- | --- | --- |
| Chief Data Officer | Imani Salcedo-Prendergast | R1058 |
| Chief Digital Officer | — | R1149 |
| Chief Operating Officer | — | R1143 |
| Director of Software Engineering | Gideon Fontaine-Crowther | R1160 |
| Head of Platform Engineering | — | R1158 |
| SVP Digital | — | R1115, R1122 |
| VP Engineering | Mei Sandoval-Kettleborough | R1108 |
| VP Enterprise Architecture | — | R1185 |

### Harrowgate Health (C018) — 9 requests, 6 distinct titles, 1 named people

Distinct titles: Chief Digital Officer; Chief Information Officer; Chief Operating Officer; SVP Digital; VP Engineering; VP Enterprise Architecture

| Title | Person | Requests |
| --- | --- | --- |
| Chief Digital Officer | — | R1140 |
| Chief Digital Officer | Emeka Underhill-Zubkov | R1137 |
| Chief Information Officer | — | R1057 |
| Chief Operating Officer | — | R1153 |
| SVP Digital | — | R1072, R1136 |
| VP Engineering | — | R1090, R1173 |
| VP Enterprise Architecture | — | R1157 |

### Priorwood Chemicals (C031) — 9 requests, 7 distinct titles, 1 named people

Distinct titles: Chief Data Officer; Chief Information Officer; Chief Operating Officer; Chief Technology Officer; Head of Developer Productivity; Head of Platform Engineering; VP Enterprise Architecture

| Title | Person | Requests |
| --- | --- | --- |
| Chief Data Officer | — | R1098 |
| Chief Information Officer | — | R1150 |
| Chief Operating Officer | — | R1118, R1192 |
| Chief Technology Officer | — | R1196 |
| Head of Developer Productivity | — | R1033 |
| Head of Platform Engineering | — | R1052 |
| Head of Platform Engineering | Amara Kettleborough-Højgaard | R1174 |
| VP Enterprise Architecture | — | R1092 |

### Vireo Systems (C046) — 9 requests, 6 distinct titles, 3 named people

Distinct titles: Chief Data Officer; Chief Digital Officer; Chief Operating Officer; Head of Developer Productivity; VP Engineering; VP Enterprise Architecture

| Title | Person | Requests |
| --- | --- | --- |
| Chief Data Officer | — | R1131 |
| Chief Digital Officer | — | R1199 |
| Chief Digital Officer | Noor Isenberg-Havercamp | R1055 |
| Chief Operating Officer | — | R1166 |
| Head of Developer Productivity | — | R1107 |
| Head of Developer Productivity | Otto Ashdown-Fairweather | R1017 |
| VP Engineering | — | R1075 |
| VP Engineering | Niall Jarrold-Norrington | R1155 |
| VP Enterprise Architecture | — | R1060 |

### Kingsmere Retail Group (C058) — 8 requests, 5 distinct titles, 1 named people

Distinct titles: Chief Digital Officer; Chief Operating Officer; SVP Digital; VP Engineering; VP Enterprise Architecture

| Title | Person | Requests |
| --- | --- | --- |
| Chief Digital Officer | — | R1066, R1113 |
| Chief Operating Officer | — | R1193 |
| SVP Digital | — | R1070 |
| VP Engineering | — | R1006 |
| VP Enterprise Architecture | — | R1128, R1147 |
| VP Enterprise Architecture | Tanvi Prendergast-Falkenrath | R1171 |
