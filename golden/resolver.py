"""Turn any company string into one company ID.

    python3 golden/resolver.py                 # resolve every string in dataset/, write CSVs
    python3 golden/resolver.py "Apex Logistics Group" "Thornbury" ...

Every match carries a method and a confidence. Anything under REVIEW_THRESHOLD
(0.75) is not joined: it goes to the human review queue with its candidates.

Layers, tried in order; the first hit wins:

  strict   1. name-exact    full name incl. legal/holdco words   1.00
           2. domain        CRM domain, or its stem              1.00 / 0.95
  loose    3. name-loose    lowercase, no punctuation, suffixes  0.85
                            and prefixes (the, inc, group...)
           4. name-prefix   one side is a prefix of the other,   0.78
                            shared stem 8+ chars, unique target

Guards, all of which have real cases in this data:

  * Holdco vs operating company. "Apex Logistics" and "Apex Logistics Group"
    are different companies (domains, countries, headcount). Strict runs first
    so the full string is matched before any suffix is stripped, and a loose
    key that lands on two different entities is ambiguous, never joined.
  * CRM grouped by domain, not name. Accounts sharing a domain form one
    company; every row is kept, one is the survivor.
  * Bare names shared by a fund and a customer (Thornbury, Silverbrook,
    Ironvale, Cobalt Lane, Ashgrove...) resolve to both candidates and are
    flagged for a human instead of being joined to either.

Entities are CRM companies (C###, ids match golden_companies.csv) and
investor funds (F###). Strings naming a company no source knows get no id.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "dataset"
OUT = ROOT / "golden"

ENTITIES_OUT = OUT / "company_ids.csv"
RESOLUTIONS_OUT = OUT / "company_resolutions.csv"
REVIEW_OUT = OUT / "company_review_queue.csv"

REVIEW_THRESHOLD = 0.75
MIN_PREFIX_STEM = 8

CONFIDENCE = {
    "name-exact": 1.00,
    "domain": 1.00,
    "domain-stem": 0.95,
    "name-loose": 0.85,
    "name-prefix": 0.78,
    "ambiguous": 0.50,
    "fund-or-customer": 0.50,
    "unmatched": 0.00,
    "empty": 0.00,
}

_NOISE = r"\b(inc|incorporated|corp|corporation|company|co|ltd|limited|llc|lp|plc|group|holdings|holding|the|and)\b"


def normalize_strict(name: str) -> str:
    """Full name, legal and holdco words kept: only case, accents and punctuation go."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def normalize(name: str) -> str:
    """Strict, plus legal suffixes and holdco/article words removed."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(_NOISE, " ", s)
    return re.sub(r"\s+", "", s)


def domain_stem(domain: str) -> str:
    d = (domain or "").strip().lower()
    d = re.sub(r"^(https?://)?(www\.)?", "", d)
    return re.sub(r"\..*$", "", d)


def _is_domain(s: str) -> bool:
    return bool(re.fullmatch(r"(https?://)?(www\.)?[a-z0-9-]+(\.[a-z0-9-]+)+/?", (s or "").strip().lower()))


@dataclass(eq=False)
class Entity:
    entity_id: str
    kind: str                      # "company" | "fund"
    name: str
    domain: str = ""
    accounts: list[dict] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)

    @property
    def survivor(self) -> dict | None:
        if not self.accounts:
            return None
        return sorted(self.accounts, key=lambda a: (a["account_id"].startswith("A9"), a["account_id"]))[0]

    @property
    def names(self) -> list[str]:
        return [self.name, *self.aliases, *(a["account_name"] for a in self.accounts)]


@dataclass
class Resolution:
    raw: str
    entity: Entity | None
    method: str
    confidence: float
    candidates: list[Entity] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return self.confidence < REVIEW_THRESHOLD

    @property
    def entity_id(self) -> str:
        return self.entity.entity_id if self.entity and not self.needs_review else ""

    def row(self) -> dict:
        return {
            "company_string": self.raw,
            "company_id": self.entity_id,
            "company_name": self.entity.name if self.entity and not self.needs_review else "",
            "kind": self.entity.kind if self.entity and not self.needs_review else "",
            "method": self.method,
            "confidence": f"{self.confidence:.2f}",
            "needs_review": "yes" if self.needs_review else "no",
            "candidates": " | ".join(f"{c.entity_id} {c.name} ({c.kind})" for c in self.candidates),
        }


class Resolver:
    def __init__(self, accounts: list[dict], funds: list[str] = ()):
        self.entities: list[Entity] = []
        self._by_domain: dict[str, Entity] = {}
        self._strict: dict[str, set[Entity]] = defaultdict(set)   # full names + domain stems
        self._stem: dict[str, Entity] = {}
        self._loose: dict[str, set[Entity]] = defaultdict(set)

        companies: dict[str, Entity] = {}
        for a in accounts:
            dom = a["domain"].strip().lower()
            e = companies.get(dom)
            if e is None:
                e = companies[dom] = Entity("", "company", "", dom)
            e.accounts.append(a)
        for dom in sorted(companies):
            e = companies[dom]
            e.name = _display_name(e)
            self._add(e)
        for name in sorted({f.strip() for f in funds if f.strip()}):
            self._add(Entity("", "fund", name))
        for e in self.entities:
            for n in e.names:
                self._strict[normalize_strict(n)].add(e)
                self._loose[normalize(n)].add(e)
            if e.domain:
                self._by_domain[e.domain] = e
                self._stem[domain_stem(e.domain)] = e
                self._strict[domain_stem(e.domain)].add(e)

    def _add(self, e: Entity) -> None:
        n = sum(1 for x in self.entities if x.kind == e.kind) + 1
        e.entity_id = f"{'C' if e.kind == 'company' else 'F'}{n:03d}"
        self.entities.append(e)

    # -- public ---------------------------------------------------------------
    def resolve(self, raw: str, domain_hint: str = "") -> Resolution:
        raw = (raw or "").strip()
        if domain_hint or _is_domain(raw):
            r = self._by_domain_string(domain_hint or raw, raw)
            if r is not None:
                return r
            if not raw:
                return Resolution(domain_hint, None, "unmatched", CONFIDENCE["unmatched"])
        strict = normalize_strict(raw)
        if not strict:
            return Resolution(raw, None, "empty", CONFIDENCE["empty"])

        # layer 1: full name, legal and holdco words included
        hits = self._strict.get(strict, set())
        if len(hits) == 1:
            e = next(iter(hits))
            method = "domain-stem" if strict == domain_stem(e.domain) and not any(
                normalize_strict(n) == strict for n in e.names) else "name-exact"
            return Resolution(raw, e, method, CONFIDENCE[method])
        if len(hits) > 1:
            return self._refuse(raw, hits)

        # layer 3: suffixes and holdco words stripped
        loose = normalize(raw)
        hits = set(self._loose.get(loose, set()))
        if loose in self._stem:
            hits.add(self._stem[loose])
        if hits and len(loose) < MIN_PREFIX_STEM:
            # "Apex" is too little to pick Apex Holdings over Apex Logistics
            for key, ents in list(self._loose.items()) + [(k, {v}) for k, v in self._stem.items()]:
                if key.startswith(loose):
                    hits |= ents
        if len(hits) == 1:
            e = next(iter(hits))
            return Resolution(raw, e, "name-loose", CONFIDENCE["name-loose"])
        if len(hits) > 1:
            return self._refuse(raw, hits)

        # layer 4: prefix on an 8+ character shared stem
        if len(loose) >= MIN_PREFIX_STEM:
            cands: set[Entity] = set()
            for key, ents in list(self._loose.items()) + [(k, {v}) for k, v in self._stem.items()]:
                if len(key) >= MIN_PREFIX_STEM and (key.startswith(loose) or loose.startswith(key)):
                    cands |= ents
            if len(cands) == 1:
                e = next(iter(cands))
                return Resolution(raw, e, "name-prefix", CONFIDENCE["name-prefix"], [e])
            if len(cands) > 1:
                return self._refuse(raw, cands)
        return Resolution(raw, None, "unmatched", CONFIDENCE["unmatched"])

    def learn_spellings(self, strings: list[str]) -> None:
        """Adopt a readable spelling for entities the CRM only knows in caps (THORNBURYFINANCIAL)."""
        for s in strings:
            r = self.resolve(s)
            e = r.entity
            if e is None or r.method != "name-exact" or s in e.names:
                continue
            if e.name.isupper() and not s.isupper():
                e.aliases.append(e.name)
                e.name = s
            else:
                e.aliases.append(s)

    def resolve_id(self, raw: str, domain_hint: str = "") -> str:
        """One company ID, or '' when a human has to decide."""
        return self.resolve(raw, domain_hint).entity_id

    def crm_rows(self) -> list[dict]:
        rows = []
        for e in self.entities:
            s = e.survivor
            for a in sorted(e.accounts, key=lambda a: a["account_id"]):
                rows.append({**a, "company_id": e.entity_id,
                             "survivor": "yes" if a is s else "no",
                             "duplicate_of": "" if a is s else s["account_id"]})
        return rows

    def entity_rows(self) -> list[dict]:
        rows = []
        for e in self.entities:
            s = e.survivor
            rows.append({
                "company_id": e.entity_id, "kind": e.kind, "company_name": e.name,
                "domain": e.domain,
                "also_known_as": " | ".join(sorted({n for n in e.names if n != e.name})),
                "crm_account_ids": " | ".join(a["account_id"] for a in sorted(e.accounts, key=lambda a: a["account_id"])),
                "survivor_account_id": s["account_id"] if s else "",
                "duplicate_account_ids": " | ".join(a["account_id"] for a in e.accounts if a is not s),
            })
        return rows

    # -- internals ------------------------------------------------------------
    def _by_domain_string(self, dom: str, raw: str) -> Resolution | None:
        dom = re.sub(r"^(https?://)?(www\.)?", "", dom.strip().lower()).rstrip("/")
        e = self._by_domain.get(dom)
        if e:
            return Resolution(raw, e, "domain", CONFIDENCE["domain"])
        e = self._stem.get(domain_stem(dom))
        if e:
            return Resolution(raw, e, "domain-stem", CONFIDENCE["domain-stem"])
        return None

    @staticmethod
    def _refuse(raw: str, cands: set[Entity]) -> Resolution:
        cands_sorted = sorted(cands, key=lambda e: e.entity_id)
        kinds = {c.kind for c in cands_sorted}
        method = "fund-or-customer" if kinds == {"company", "fund"} else "ambiguous"
        return Resolution(raw, None, method, CONFIDENCE[method], cands_sorted)


def _display_name(e: Entity) -> str:
    s = e.survivor
    crm = s["account_name"]
    if crm.isupper():
        key = normalize_strict(crm)
        for a in e.accounts:
            if normalize_strict(a["account_name"]) == key and not a["account_name"].isupper():
                return a["account_name"]
    return crm


# ---------------------------------------------------------------------------
# dataset-wide run
# ---------------------------------------------------------------------------
def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\r\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_resolver() -> Resolver:
    funds = [r["fund"] for r in read_csv(DATASET / "investor_network.csv")]
    res = Resolver(read_csv(DATASET / "crm_accounts.csv"), funds)
    res.learn_spellings(sorted(company_strings()))
    return res


def company_strings() -> dict[str, set[str]]:
    """Every distinct company string in dataset/, with the files it appears in."""
    seen: dict[str, set[str]] = defaultdict(set)
    for r in read_csv(DATASET / "crm_accounts.csv"):
        seen[r["account_name"]].add("crm_accounts")
    for r in read_csv(DATASET / "intro_requests.csv"):
        if r["target_company_raw"].strip():
            seen[r["target_company_raw"].strip()].add("intro_requests")
    for r in read_csv(DATASET / "investor_network.csv"):
        for col in ("fund", "portfolio_company", "prior_employer"):
            if r[col].strip():
                seen[r[col].strip()].add(f"investor_network.{col}")
    for p in sorted(DATASET.glob("connections_*.csv")):
        for r in read_csv(p):
            if r["company"].strip():
                seen[r["company"].strip()].add(p.stem)
    return seen


# ---------------------------------------------------------------------------
# slack threads: the opening message names the target company (or doesn't)
# ---------------------------------------------------------------------------
_C = r"(?P<c>[A-Z][\w&'-]*(?: [A-Z&][\w&'-]*)*)"
_SLACK_PATTERNS = [re.compile(p) for p in (
    r"email domain is (?P<d>[a-z0-9.-]+\.[a-z]{2,})",
    r"account I actually need is " + _C + r"\s*\(",
    r"^" + _C + r" is the target\.",
    r"^we need " + _C + r"\.",
    r"^asking again: " + _C + r"\.",
    r"^long shot — " + _C + r"\.",
    r"^trying to reach .+? at " + _C + r"(?: —|\.)",
    r"^(?:any connections|path) into " + _C + r"\?",
    r"^(?:who do we know|does anyone know anyone|who knows someone|need an intro) at " + _C + r"(?:\?| —)",
    r"^need help getting to " + _C + r"\.",
)]


def company_from_slack(text: str) -> tuple[str, str]:
    """-> (company string, domain hint); both empty when the message names only a person."""
    for pat in _SLACK_PATTERNS:
        m = pat.search(text)
        if m:
            d = m.groupdict()
            return d.get("c") or "", d.get("d") or ""
    return "", ""


def resolve_slack_threads(res: Resolver) -> list[dict]:
    rows = []
    with open(DATASET / "slack_threads.jsonl", encoding="utf-8") as f:
        for line in f:
            t = json.loads(line)
            text = t["messages"][0]["text"]
            written, hint = company_from_slack(text)
            if not written and not hint:
                r = Resolution("", None, "no-company-named", 0.0)
            else:
                r = res.resolve(written, hint)
            rows.append({"request_id": t["request_id"], "opening_message": text,
                         "extracted": written or hint, **r.row()})
    return rows


SLACK_COLUMNS = ["request_id", "company_id", "company_name", "kind", "method", "confidence",
                 "needs_review", "candidates", "extracted", "opening_message"]
SLACK_OUT = OUT / "slack_resolutions.csv"

RESOLUTION_COLUMNS = ["company_string", "sources", "company_id", "company_name", "kind",
                      "method", "confidence", "needs_review", "candidates"]
ENTITY_COLUMNS = ["company_id", "kind", "company_name", "domain", "also_known_as",
                  "crm_account_ids", "survivor_account_id", "duplicate_account_ids"]


def main(argv: list[str]) -> None:
    res = load_resolver()
    if argv:
        for s in argv:
            print(json.dumps(res.resolve(s).row(), ensure_ascii=False))
        return

    write_csv(ENTITIES_OUT, ENTITY_COLUMNS, res.entity_rows())
    rows = []
    for s, sources in sorted(company_strings().items(), key=lambda kv: kv[0].lower()):
        rows.append({**res.resolve(s).row(), "sources": " | ".join(sorted(sources))})
    write_csv(RESOLUTIONS_OUT, RESOLUTION_COLUMNS, rows)
    review = [r for r in rows if r["needs_review"] == "yes"]
    write_csv(REVIEW_OUT, RESOLUTION_COLUMNS, review)

    dupes = [r for r in res.crm_rows() if r["survivor"] == "no"]
    by_method = defaultdict(int)
    for r in rows:
        by_method[r["method"]] += 1
    print(f"company_ids.csv            {len(res.entities)} entities "
          f"({sum(e.kind == 'company' for e in res.entities)} companies, "
          f"{sum(e.kind == 'fund' for e in res.entities)} funds); "
          f"{len(dupes)} CRM rows are non-survivor duplicates by domain")
    print(f"company_resolutions.csv    {len(rows)} distinct strings: "
          + ", ".join(f"{m} {n}" for m, n in sorted(by_method.items(), key=lambda kv: -kv[1])))
    print(f"company_review_queue.csv   {len(review)} for a human")
    for r in review:
        print(f"  {r['company_string']!r:32} {r['method']:17} {r['candidates'] or '-'}")

    slack = resolve_slack_threads(res)
    write_csv(SLACK_OUT, SLACK_COLUMNS, slack)
    exact = sum(r["method"] in ("name-exact", "domain") for r in slack)
    confident = sum(r["needs_review"] == "no" for r in slack) - exact
    escalated = [r for r in slack if r["needs_review"] == "yes"]
    print(f"slack_resolutions.csv      {len(slack)} threads: {exact} exact string/domain, "
          f"{confident} joined with confidence < 1.00, {len(escalated)} escalated")
    slack_methods = defaultdict(int)
    for r in slack:
        slack_methods[r["method"]] += 1
    for m, n in sorted(slack_methods.items(), key=lambda kv: -kv[1]):
        print(f"  {m:18} {n}")


if __name__ == "__main__":
    # under build.py (runpy) argv belongs to build.py, not to us
    main(sys.argv[1:] if Path(sys.argv[0]).name == "resolver.py" else [])
