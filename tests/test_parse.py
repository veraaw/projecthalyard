"""Target-company extraction from raw Slack text (golden/parse.py).

    python3 -m unittest tests.test_parse
"""
import csv
import json
import shutil
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from golden import build_golden as bg  # noqa: E402
from golden import parse as gp  # noqa: E402
from golden import resolver as gr  # noqa: E402
from golden.parse import extract  # noqa: E402
from golden.resolver import Resolver  # noqa: E402

DATASET = ROOT / "dataset"

# The cases ParseTargetTest runs, one message each; ExportedRulesTest runs the same
# texts through the exported cue table + resolver index under node.
CASES = {
    "distractor": "Calderon Aerospace introduced us to Kestrel Airlines, but the account I actually need is Ironvale Steel",
    "first person need": "Calderon Aerospace introduced us to Kestrel Airlines, but I need Ironvale Steel",
    "first person need, new company": "Calderon Aerospace introduced us to Kestrel Airlines, but I need Bluewater Foods",
    "bridge": "trying to reach the COO at Apex Logistics. I know we sell into Larkhall Software and Cindermill Mining",
    "negation": ("we need Cobalt Lane Capital Markets. Not Ferrowick Insurance — that's a different entity "
                 "and we already have that one. Also spoke to Apex Logistics last week, unrelated."),
    "is the account": "Quillon Pharma is the account. Not Pelham Beverage.",
    "domain": "email domain is bexleybio.com",
    "domain over person": "looking for a path to Noor Isenberg-Havercamp — email domain is vireosystems.com, that's all I have",
    "unknown company": "any connections into Kingsmere Retail Group? we're up against a renewal window",
    "fund or customer": "who do we know at Thornbury?",
    "person only": "Rafael Kirkbride-Ibarra is the person I need. Pretty sure they're a Chief Information Officer somewhere in Semiconductors.",
    "negative only": "Our champion at Yarrowdale Media used to work with their team",
    "no path": "any connections into Halcyon Grid?",
    "connect with": "Can we connect with Quillon Pharma?",
    "warm intro": "looking for a warm intro to Quillon Pharma, COO ideally",
    "reach with title": "trying to reach Head of Platform Engineering at Thistledown Energy — anyone have a path?",
    "bare lowercase name": "how about quillon pharma",
    "bare name only": "Quillon Pharma?",
    "caps-only crm spelling": "how about thornbury financial",
    "two bare names": "harrowgate health or quillon pharma, whichever is easier",
    "cue beats bare name": "can we connect with Quillon Pharma? harrowgate health is already a customer",
    "bare no-CRM name": "how about kingsmere retail group",
    "network-only company": "Looking for a warm path into Zenner Foods",
    "bare network-only name": "how about xanthe labs",
}


def read_csv(name):
    with open(DATASET / name, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


class ParseTargetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = Resolver(read_csv("crm_accounts.csv"), [r["fund"] for r in read_csv("investor_network.csv")])

    def scores(self, text):
        return {m.text: m.score for m in extract(text, self.res).mentions}

    def test_phrase_beats_position_target_last(self):
        text = "Calderon Aerospace introduced us to Kestrel Airlines, but the account I actually need is Ironvale Steel"
        ex = extract(text, self.res)
        self.assertEqual(ex.target.text, "Ironvale Steel")
        self.assertEqual(ex.target.cue, "the account I actually need is")
        self.assertEqual(ex.target.resolution.method, "name-exact")
        self.assertEqual(ex.target_id, self.res.resolve_id("Ironvale Steel"))
        s = self.scores(text)
        self.assertEqual(set(s), {"Calderon Aerospace", "Kestrel Airlines", "Ironvale Steel"})
        self.assertGreater(s["Ironvale Steel"], 0)
        self.assertLess(s["Calderon Aerospace"], 0)   # introducer
        self.assertLess(s["Kestrel Airlines"], 0)     # the intro we already got

    def test_phrase_beats_position_target_first(self):
        text = "trying to reach the COO at Apex Logistics. I know we sell into Larkhall Software and Cindermill Mining"
        ex = extract(text, self.res)
        self.assertEqual(ex.target.text, "Apex Logistics")
        self.assertEqual(ex.target.resolution.method, "name-exact")
        self.assertEqual(ex.target.resolution.entity.domain, "apexlogistics.com")   # not Apex Logistics Group
        s = self.scores(text)
        self.assertEqual(set(s), {"Apex Logistics", "Larkhall Software", "Cindermill Mining"})
        self.assertGreater(s["Apex Logistics"], 0)
        self.assertLess(s["Larkhall Software"], 0)    # we sell into: existing customers, not targets
        self.assertLess(s["Cindermill Mining"], 0)

    def test_first_person_need_outranks_the_bridge(self):
        """"X introduced us to Y, but I need Z": Z is asked for, X and Y are the
        bridge. Z is the target whether or not the CRM knows it; without the cue
        an unknown Z left the message with no target at all."""
        for z, method in [("Ironvale Steel", "name-exact"), ("Bluewater Foods", "unmatched")]:
            with self.subTest(z):
                ex = extract(f"Calderon Aerospace introduced us to Kestrel Airlines, but I need {z}", self.res)
                self.assertEqual(ex.target.text, z)
                self.assertEqual(ex.target.cue, "we need")
                self.assertEqual(ex.target.score, 2)
                self.assertEqual(ex.target.resolution.method, method)
                self.assertEqual(self.scores(ex.text), {"Calderon Aerospace": -1, "Kestrel Airlines": -1, z: 2})
        self.assertIsNone(extract("Rafael Kirkbride-Ibarra is the person I need.", self.res).target)

    def test_r1076_weak_cue_beats_explicit_negation(self):
        text = ("we need Cobalt Lane Capital Markets. Not Ferrowick Insurance — that's a different entity "
                "and we already have that one. Also spoke to Apex Logistics last week, unrelated.")
        ex = extract(text, self.res)
        self.assertEqual(ex.target.text, "Cobalt Lane Capital Markets")
        self.assertEqual(ex.target.cue, "we need")
        self.assertEqual(ex.target.resolution.method, "name-exact")
        self.assertEqual(ex.target_id, self.res.resolve_id("Cobalt Lane Capital Markets"))
        s = self.scores(text)
        self.assertEqual(set(s), {"Cobalt Lane Capital Markets", "Ferrowick Insurance", "Apex Logistics"})
        self.assertLess(s["Ferrowick Insurance"], s["Cobalt Lane Capital Markets"])
        self.assertLess(s["Apex Logistics"], s["Cobalt Lane Capital Markets"])
        self.assertLess(s["Ferrowick Insurance"], 0)   # explicit negation
        self.assertLess(s["Apex Logistics"], 0)        # already spoken to, unrelated

    def test_is_the_account_cue(self):
        ex = extract("Quillon Pharma is the account. Not Pelham Beverage.", self.res)
        self.assertEqual(ex.target.text, "Quillon Pharma")
        self.assertEqual(self.scores(ex.text)["Pelham Beverage"], -3)

    def test_plain_ask_phrasings_are_recognised(self):
        for text, cue in [
            ("Can we connect with Quillon Pharma?", "connect with"),
            ("connect me to Quillon Pharma please", "connect with"),
            ("looking for a warm intro to Quillon Pharma, COO ideally", "intro to"),
            ("any introductions at Quillon Pharma?", "intro to"),
            ("can someone introduce us to Quillon Pharma", "introduce us to"),
            ("can we get in front of Quillon Pharma?", "get in front of"),
            ("does anyone have an in at Quillon Pharma", "an in at"),
            ("anyone at Quillon Pharma?", "anyone at"),
            ("who can help us with Quillon Pharma", "help with"),
            ("want to reach Quillon Pharma", "reach"),
            ("reach out to Quillon Pharma", "reach"),
            ("can we get a meeting with Quillon Pharma", "meeting with"),
            ("any way into Quillon Pharma?", "way into"),
        ]:
            with self.subTest(text):
                ex = extract(text, self.res)
                self.assertIsNotNone(ex.target, text)
                self.assertEqual(ex.target.text, "Quillon Pharma")
                self.assertEqual(ex.target.cue, cue)
                self.assertEqual(ex.target.resolution.method, "name-exact")
                self.assertEqual(ex.target_id, self.res.resolve_id("Quillon Pharma"))

    def test_reach_does_not_take_the_title_for_the_company(self):
        for text, company in [
            ("trying to reach Head of Platform Engineering at Thistledown Energy — anyone have a path?", "Thistledown Energy"),
            ("trying to reach Chief Operating Officer at Larchmont Aerospace. I know we sell into Ellerby Semiconductor", "Larchmont Aerospace"),
            ("trying to reach SVP Digital at Gravenhurst Motors — anyone have a path?", "Gravenhurst Motors"),
        ]:
            with self.subTest(text):
                ex = extract(text, self.res)
                self.assertEqual(ex.target.text, company)
                self.assertEqual(ex.target.cue, "trying to reach ... at")
                self.assertEqual([m.text for m in ex.mentions if m.score > 0], [company])

    def test_past_tense_introduced_stays_negative(self):
        ex = extract("Quillon Pharma introduced us to Pelham Beverage", self.res)
        self.assertIsNone(ex.target)
        self.assertEqual(self.scores(ex.text), {"Quillon Pharma": -1, "Pelham Beverage": -1})

    def test_email_domain_resolves_on_domain(self):
        ex = extract("email domain is bexleybio.com", self.res)
        self.assertTrue(ex.target.is_domain)
        self.assertEqual(ex.target.text, "bexleybio.com")
        self.assertEqual(ex.target.resolution.method, "domain")
        self.assertEqual(ex.target.resolution.entity.domain, "bexleybio.com")
        self.assertEqual(ex.target.resolution.entity.name, "Bexley Bioworks")
        self.assertEqual(ex.target_id, self.res.resolve("", "bexleybio.com").entity_id)

    def test_domain_outranks_person_name(self):
        text = "looking for a path to Noor Isenberg-Havercamp — email domain is vireosystems.com, that's all I have"
        ex = extract(text, self.res)
        self.assertEqual(ex.target.text, "vireosystems.com")
        self.assertEqual(ex.target.resolution.method, "unmatched")   # not a CRM domain: human, not a join
        self.assertEqual(ex.target_id, "")

    def test_unknown_company_is_still_extracted(self):
        ex = extract("any connections into Kingsmere Retail Group? we're up against a renewal window", self.res)
        self.assertEqual(ex.target.text, "Kingsmere Retail Group")
        self.assertEqual(ex.target.resolution.method, "unmatched")
        self.assertEqual(ex.target_id, "")

    def test_bare_fund_customer_name_is_refused(self):
        ex = extract("who do we know at Thornbury?", self.res)
        self.assertEqual(ex.target.text, "Thornbury")
        self.assertEqual(ex.target.resolution.method, "fund-or-customer")
        self.assertEqual(len(ex.target.resolution.candidates), 2)
        self.assertEqual(ex.target_id, "")

    def test_no_company_means_no_target(self):
        for text in [
            "Rafael Kirkbride-Ibarra is the person I need. Pretty sure they're a Chief Information Officer somewhere in Semiconductors.",
            "anyone connected to Ilse Oyelaran-Zettergren? They run engineering at a large logistics business, I don't have the entity name handy",
            "",
        ]:
            self.assertIsNone(extract(text, self.res).target, text)

    def test_negative_only_mentions_give_no_target(self):
        ex = extract("Our champion at Yarrowdale Media used to work with their team", self.res)
        self.assertEqual(self.scores(ex.text), {"Yarrowdale Media": -1})
        self.assertIsNone(ex.target)

    def test_known_name_without_a_cue_is_the_target_in_any_case(self):
        harrowgate = self.res.resolve("Harrowgate Health").entity_id
        for text, written in [("how about harrowgate health", "harrowgate health"),
                              ("Harrowgate Health?", "Harrowgate Health"),
                              ("HARROWGATE HEALTH - any thoughts", "HARROWGATE HEALTH")]:
            ex = extract(text, self.res)
            self.assertEqual(ex.target.text, written, text)
            self.assertEqual(ex.target.cue, gp.KNOWN_CUE)
            self.assertEqual(ex.target.score, gp.KNOWN_SCORE)
            self.assertEqual(ex.target_id, harrowgate, text)

    def test_known_name_finds_crm_caps_spellings_written_as_words(self):
        ex = extract("how about thornbury financial", self.res)
        self.assertEqual(ex.target.text, "thornbury financial")
        self.assertEqual(ex.target_id, self.res.resolve("THORNBURYFINANCIAL").entity_id)
        ex = extract("apex logistics, inc. anyone?", self.res)
        self.assertEqual(ex.target_id, self.res.resolve("Apex Logistics").entity_id)

    def test_known_name_never_fires_without_a_resolver(self):
        self.assertEqual(extract("how about harrowgate health").mentions, [])

    def test_two_bare_known_names_refuse_to_guess(self):
        ex = extract("harrowgate health or quillon pharma, whichever is easier", self.res)
        self.assertIsNone(ex.target)
        self.assertEqual(self.scores(ex.text), {"harrowgate health": 0, "quillon pharma": 0})

    def test_cue_still_decides_when_a_bare_known_name_is_around(self):
        ex = extract("can we connect with Quillon Pharma? harrowgate health is already a customer", self.res)
        self.assertEqual(ex.target.text, "Quillon Pharma")
        self.assertEqual(self.scores(ex.text), {"Quillon Pharma": 2, "harrowgate health": 0})
        ex = extract("Not Harrowgate Health", self.res)   # a negative cue owns the span; no bare-name rescue
        self.assertIsNone(ex.target)
        self.assertEqual(self.scores(ex.text), {"Harrowgate Health": -3})
        ex = extract("Quillon Pharma introduced us to Pelham Beverage", self.res)
        self.assertIsNone(ex.target)

    def test_known_names_do_not_match_inside_words(self):
        self.assertEqual(extract("the apexlogisticsgroupies are in town", self.res).mentions, [])


@unittest.skipUnless(shutil.which("node"), "node is needed to run the exported rules")
class ExportedRulesTest(unittest.TestCase):
    """The dashboard payload carries parse.py's cues, the resolver's index and every
    company's paths as data; dashboard/live_priorities.js interprets them. Run the
    same messages through both and demand the same target and the same top
    connector. If the export drifts from parse.py this fails."""

    @classmethod
    def setUpClass(cls):
        from dashboard.live_priorities import Live, ROUTE_PRESETS
        from golden.resolve_cli import load_resolver
        cls.live = Live(date.today())
        cls.P = cls.live.parser()
        cls.res = load_resolver()
        cls.presets = ROUTE_PRESETS
        texts = [*CASES.values(), *(p["text"] for p in ROUTE_PRESETS)]
        cls.texts = list(dict.fromkeys(texts))
        out = subprocess.run(["node", str(ROOT / "tests" / "lp_parity.js")], cwd=ROOT, check=True,
                             input=json.dumps({"parser": cls.P, "texts": cls.texts, "threads": ""}),
                             capture_output=True, text=True)
        js = json.loads(out.stdout)
        cls.js = {t: r for t, r in zip(cls.texts, js["routed"])}
        cls.js_extract = {t: r for t, r in zip(cls.texts, js["extracted"])}

    def python_top(self, cid):
        p, _ = bg.best_route(self.live.paths.get(cid, []), self.live.roster, self.live.rates, self.live.industry(cid))
        return (p["connector"], p["reach_type"], p["contact_name"]) if p else None

    def test_cue_table_is_parse_py_verbatim(self):
        exported = [(c["label"], c["source"], c["score"]) for c in self.P["cues"]]
        expected = [(label, pat.replace("(?P<", "(?<"), score) for label, pat, score in gp.CUES]
        self.assertEqual(exported, expected)
        self.assertNotIn("(?P<", json.dumps(self.P["cues"]))
        self.assertEqual(self.P["domain_cue"], gp.DOMAIN_CUE)
        self.assertEqual(self.P["domain_score"], gp.DOMAIN_SCORE)
        self.assertEqual(self.P["domain"]["source"], gp._DOMAIN.pattern)
        self.assertEqual(self.P["title"]["source"], gp.TITLE_RE.pattern.replace("(?P<", "(?<"))
        self.assertEqual(self.P["known"]["source"], self.live.known_regex().pattern)
        self.assertIn("i", self.P["known"]["flags"])
        self.assertIsNotNone(self.live.known_regex().search("kingsmere retail group"), "companies on file with no CRM account are scanned for too")
        self.assertIsNone(self.res.names_regex().search("kingsmere retail group"))
        self.assertIsNotNone(self.live.known_regex().search("zenner foods"), "companies only the network reaches are scanned for too")
        self.assertIsNone(self.res.names_regex().search("zenner foods"))
        self.assertEqual(sorted(self.live.known_regex().findall("Xanthe Labs, Zenner Foods and Quillon Pharma"), key=str.lower),
                         ["Quillon Pharma", "Xanthe Labs", "Zenner Foods"])
        self.assertEqual(self.P["known_cue"], gp.KNOWN_CUE)
        self.assertEqual(self.P["known_score"], gp.KNOWN_SCORE)

    def test_resolver_index_covers_every_entity(self):
        R = self.P["resolver"]
        ids = {e.entity_id for e in self.res.entities}
        self.assertEqual(set(R["entities"]), ids)
        self.assertEqual(set(R["by_domain"]), {e.domain for e in self.res.entities if e.domain})
        for table in ("strict", "loose", "stem", "by_domain"):
            for key, v in R[table].items():
                for i in (v if isinstance(v, list) else [v]):
                    self.assertIn(i, ids, f"{table}[{key}]")
        coll = R["fund_or_customer"]
        self.assertIn("thornbury", coll)
        for stem, cands in coll.items():
            self.assertEqual({R["entities"][i]["kind"] for i in cands}, {"company", "fund"}, stem)
            self.assertEqual(self.res.resolve(stem).method, "fund-or-customer", stem)

    def test_company_export_carries_every_path(self):
        for cid, c in self.live.companies.items():
            e = self.P["companies"][cid]
            self.assertEqual(e["company_name"], c["company_name"])
            self.assertEqual(e["stage"], c["stage"])
            self.assertEqual(e["owner"], c["owner"])
            self.assertEqual(len(e["paths"]), len(self.live.paths.get(cid, [])))
            for p in e["paths"]:
                for k in ("connector", "contact", "title", "evidence", "strength", "fit", "rate", "score", "reason"):
                    self.assertIn(k, p)
            keys = [(p["reach_type"] == bg.INVESTOR_NETWORK, -p["score"]) for p in e["paths"]]
            self.assertEqual(keys, sorted(keys), f"{cid}: roster paths first, then by route score")

    def test_network_only_companies_are_exported(self):
        """A company the network reaches but nobody has filed is in the payload under a
        'network:' key: no company_id, no CRM account, its best paths ranked as the
        build would rank them once a request creates the company."""
        from dashboard.live_priorities import NETWORK_PATHS_SHOWN
        net = {k: v for k, v in self.P["companies"].items() if k.startswith("network:")}
        self.assertEqual(set(net), set(self.live.network_only))
        self.assertIn("network:zennerfoods", net)
        on_file = {gr.normalize_strict(n) for c in self.live.companies.values()
                   for n in [c["company_name"], *c["also_known_as"].split("|")]}
        reached = {gr.normalize_strict(n) for n in bg.network_company_names(self.live.roster)}
        for key, e in net.items():
            with self.subTest(key):
                self.assertTrue(e["network"])
                self.assertFalse(e["crm"])
                self.assertEqual((e["company_id"], e["href"], e["industry"], e["stage"]), ("", "", "", ""))
                self.assertEqual(self.res.resolve(e["company_name"]).method, "unmatched", "not a CRM account or a fund")
                self.assertNotIn(gr.normalize_strict(e["company_name"]), on_file, "not on file from an earlier ask")
                self.assertIn(gr.normalize_strict(e["company_name"]), reached, "someone in the network reaches it")
                for n in e["names"]:
                    self.assertEqual(self.P["known_network"][gr.normalize_strict(n)], key)
                    self.assertNotIn(gr.normalize_strict(n), self.P["known_no_crm"])
                paths = self.live.network_only[key]["paths"]
                self.assertEqual(e["path_count"], len(paths))
                self.assertEqual(len(e["paths"]), min(len(paths), NETWORK_PATHS_SHOWN))
                keys = [(p["reach_type"] == bg.INVESTOR_NETWORK, -p["score"]) for p in e["paths"]]
                self.assertEqual(keys, sorted(keys), f"{key}: roster paths first, then by route score")
                best, _ = bg.best_route(paths, self.live.roster, self.live.rates, "")
                self.assertEqual((e["best"]["connector"], e["best"]["reach_type"], e["best"]["contact"]),
                                 (best["connector"], best["reach_type"], best["contact_name"]))
                self.assertEqual(e["priority"]["request_priority"], 0)
                self.assertEqual(e["priority"]["components"]["stage_weight"], self.P["no_crm_weight"])
        # every network company that is neither a CRM account nor on file is exported
        for n in bg.network_company_names(self.live.roster):
            if self.res.resolve(n).method == "unmatched" and gr.normalize_strict(n) not in on_file:
                self.assertIn(gr.normalize_strict(n), self.P["known_network"], n)

    def test_network_only_company_routes_to_its_best_path(self):
        for name in ("network-only company", "bare network-only name"):
            with self.subTest(name):
                js = self.js[CASES[name]]
                self.assertEqual(js["status"], "routed")
                self.assertTrue(js["network"])
                self.assertFalse(js["crm"])
                self.assertEqual(js["company_id"], "")
                key = self.P["known_network"][gr.normalize_strict(js["company_name"])]
                best, _ = bg.best_route(self.live.network_only[key]["paths"], self.live.roster, self.live.rates, "")
                self.assertEqual((js["top"]["connector"], js["top"]["reach_type"], js["top"]["contact"]),
                                 (best["connector"], best["reach_type"], best["contact_name"]))
                self.assertGreater(js["path_count"], len(js["paths"]))
        self.assertEqual(self.js[CASES["network-only company"]]["company_name"], "Zenner Foods")
        self.assertEqual(self.js[CASES["bare network-only name"]]["company_name"], "Xanthe Labs")
        self.assertEqual(self.js_extract[CASES["bare network-only name"]]["target"], "xanthe labs")

    def test_same_target_as_the_python_parser(self):
        scan = self.live.known_regex()
        for name, text in CASES.items():
            with self.subTest(name):
                ex = extract(text, self.res, scan)
                js = self.js[text]
                self.assertEqual(js["target"], ex.target.text if ex.target else None)
                self.assertEqual(js["title"], gp.extract_title(text))
                self.assertEqual(js["others"], [m.text for m in ex.mentions if m is not ex.target])
                if ex.target is None:
                    self.assertEqual(js["status"], "no-target")
                    continue
                r = ex.target.resolution
                if r.method in ("fund-or-customer", "ambiguous"):
                    self.assertEqual(js["status"], "refused")
                    self.assertEqual(js["candidates"], sorted(c.entity_id for c in r.candidates))
                    self.assertIsNone(js["top"])
                elif r.entity_id:
                    self.assertEqual(js["company_id"], r.entity_id)
                else:   # unmatched by the resolver: a company on file with no CRM account, one only the network reaches, or new
                    name = gr.domain_stem(ex.target.text) if ex.target.is_domain else ex.target.text
                    known = self.P["known_no_crm"]
                    self.assertEqual(js["company_id"], known.get(gr.normalize_strict(name)) or known.get(gr.normalize(name), ""))
                    net = self.P["known_network"]
                    self.assertEqual(js["network"], not js["company_id"] and bool(net.get(gr.normalize_strict(name)) or net.get(gr.normalize(name))))

    def test_same_top_connector_as_the_build(self):
        for name, text in CASES.items():
            with self.subTest(name):
                js = self.js[text]
                if js["network"]:
                    continue   # test_network_only_company_routes_to_its_best_path
                if not js["company_id"]:
                    self.assertIsNone(js["top"])
                    continue
                top = self.python_top(js["company_id"])
                self.assertEqual((js["top"]["connector"], js["top"]["reach_type"], js["top"]["contact"]) if js["top"] else None, top)
                self.assertEqual(js["status"], "routed" if top else "no-path")

    def test_presets_hit_the_cases_they_are_named_for(self):
        want = {"Distractor": ("routed", "Ironvale Steel"), "Bridge": ("routed", "Apex Logistics"),
                "Domain only": ("routed", "Bexley Bioworks"), "No path": ("no-path", "Halcyon Grid"),
                "Fund or customer": ("refused", ""), "No CRM record": ("routed", "Kingsmere Retail Group"),
                "Network only": ("routed", "Zenner Foods")}
        self.assertEqual({p["label"] for p in self.presets}, set(want))
        for p in self.presets:
            js = self.js[p["text"]]
            self.assertEqual((js["status"], js["company_name"]), want[p["label"]], p["label"])
        bridge = self.js[next(p["text"] for p in self.presets if p["label"] == "Bridge")]
        self.assertEqual(bridge["title"], "COO")
        self.assertEqual(bridge["others"], ["Larkhall Software", "Cindermill Mining"])
        no_crm = self.js[next(p["text"] for p in self.presets if p["label"] == "No CRM record")]
        self.assertFalse(no_crm["crm"])
        self.assertIsNotNone(no_crm["top"])
        refused = self.js[next(p["text"] for p in self.presets if p["label"] == "Fund or customer")]
        self.assertEqual(len(refused["candidates"]), 2)
        self.assertEqual(refused["paths"], [])
        network = self.js[next(p["text"] for p in self.presets if p["label"] == "Network only")]
        self.assertTrue(network["network"])
        self.assertFalse(network["crm"])
        self.assertIsNotNone(network["top"])


if __name__ == "__main__":
    unittest.main()
