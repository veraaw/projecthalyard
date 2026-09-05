"""Companies targeted by 2+ intro requests: same person or different people?

Groups requests by the resolved `company_id` from golden/golden_requests.csv
(43 requests leave `target_company_raw` blank, and aliases like "Apex
Logistics, Inc." collapse there). Person/title come from intro_requests.csv;
154/200 requests name no person, so each request's target identity is
`target_person_raw` when present, otherwise `target_title_raw`.

Regenerates analysis/profile/repeat_companies.md.

    python3 -m analysis.profile.repeat_companies      # from the repo root
"""
import csv
from collections import defaultdict
from itertools import combinations

from paths import DATASET, GOLDEN, PROFILE


def rows(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


requests = rows(DATASET / "intro_requests.csv")
golden = {r["request_id"]: r for r in rows(GOLDEN / "golden_requests.csv")}
company_name = {r["company_id"]: r["company_name"] for r in rows(GOLDEN / "golden_companies.csv")}

for r in requests:
    r["_cid"] = golden[r["request_id"]]["company_id"]
    r["_person"] = r["target_person_raw"].strip()
    r["_title"] = r["target_title_raw"].strip()
    r["_target"] = r["_person"] or r["_title"]

unresolved = [r for r in requests if not r["_cid"]]
by_company = defaultdict(list)
for r in requests:
    if r["_cid"]:
        by_company[r["_cid"]].append(r)
multi = {c: v for c, v in by_company.items() if len(v) >= 2}


def classify(v, key):
    n = len({r[key] for r in v})
    return "same" if n == 1 else "different" if n == len(v) else "mixed"


def summary(key, label):
    out = []
    w = out.append
    per = defaultdict(list)
    for c, v in multi.items():
        per[classify(v, key)].append(v)
    w(f"Per company, comparing **{label}**:\n")
    w("| Pattern | Companies | Requests |")
    w("| --- | ---: | ---: |")
    for pat, desc in [("same", "Every request wants the **same** target"),
                      ("different", "Every request wants a **different** target"),
                      ("mixed", "Mixed (some repeats, some new)")]:
        w(f"| {desc} | {len(per[pat])} | {sum(len(v) for v in per[pat])} |")
    w("")
    ps = pd = 0
    for v in multi.values():
        for a, b in combinations(v, 2):
            if a[key] == b[key]:
                ps += 1
            else:
                pd += 1
    w(f"Per request pair within a company ({ps + pd} pairs): **{ps}** pairs want the same target, "
      f"**{pd}** want different targets.\n")
    return out


out = []
w = out.append
w("# Repeat target companies in `dataset/intro_requests.csv`\n")
w(f"{len(requests) - len(unresolved)} of {len(requests)} requests resolve (via `golden/golden_requests.csv`) to "
  f"{len(by_company)} companies; **{len(multi)}** companies appear in 2+ requests "
  f"({sum(len(v) for v in multi.values())} requests). The other {len(unresolved)} requests name a person "
  f"but no identifiable company ({', '.join(r['request_id'] for r in unresolved)}) and are excluded.\n")
blank_person = sum(1 for r in requests if not r["_person"])
w(f"Only {len(requests) - blank_person} of {len(requests)} requests name a `target_person_raw`; the other "
  f"{blank_person} give a title only. \"Target\" below therefore means the named person when there is one, "
  "otherwise the title. The strict named-person view (blank counts as its own value) is shown second.\n")

w("## Same person or different people?\n")
out += summary("_target", "person if named, else title")
w("<details><summary>Strict view: <code>target_person_raw</code> only (blank treated as one value)</summary>\n")
out += summary("_person", "`target_person_raw` verbatim")
w("</details>\n")

w("| Company | Requests | Distinct targets | Named people | Distinct titles | Pattern |")
w("| --- | ---: | ---: | ---: | ---: | --- |")
for c, v in sorted(multi.items(), key=lambda kv: (-len(kv[1]), company_name[kv[0]])):
    w(f"| {company_name[c]} | {len(v)} | {len({r['_target'] for r in v})} | "
      f"{len({r['_person'] for r in v if r['_person']})} | {len({r['_title'] for r in v})} | "
      f"{classify(v, '_target')} |")
w("")

w("## Top five companies by request count\n")
top = sorted(multi.items(), key=lambda kv: (-len(kv[1]), company_name[kv[0]]))[:5]
for c, v in top:
    titles = sorted({r["_title"] for r in v})
    named = sorted({r["_person"] for r in v if r["_person"]})
    w(f"### {company_name[c]} ({c}) — {len(v)} requests, {len(titles)} distinct titles, "
      f"{len(named)} named people\n")
    w("Distinct titles: " + "; ".join(titles) + "\n")
    w("| Title | Person | Requests |")
    w("| --- | --- | --- |")
    per = defaultdict(list)
    for r in v:
        per[(r["_title"], r["_person"])].append(r["request_id"])
    for (t, p), ids in sorted(per.items()):
        w(f"| {t} | {p or '—'} | {', '.join(sorted(ids))} |")
    w("")

path = PROFILE / "repeat_companies.md"
path.write_text("\n".join(out), encoding="utf-8")
print(path)
print(f"companies={len(by_company)} multi={len(multi)} "
      + " ".join(f"{p}={sum(1 for v in multi.values() if classify(v, '_target') == p)}"
                 for p in ("same", "different", "mixed")))
