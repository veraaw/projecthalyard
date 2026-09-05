"""Target-company extraction from raw Slack text (golden/parse.py).

    python3 -m unittest tests.test_parse
"""
import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from golden.parse import extract  # noqa: E402
from golden.resolver import Resolver  # noqa: E402

DATASET = ROOT / "dataset"


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


if __name__ == "__main__":
    unittest.main()
