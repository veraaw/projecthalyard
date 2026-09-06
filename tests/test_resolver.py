"""python3 -m unittest tests.test_resolver  (run from the repo root)"""
import unittest

from golden.resolve_cli import load_resolver
from golden.resolver import REVIEW_THRESHOLD


class ResolverGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = load_resolver()

    def joined(self, s):
        r = self.res.resolve(s)
        self.assertFalse(r.needs_review, f"{s!r} -> {r.method} {r.confidence}")
        return r

    def refused(self, s):
        r = self.res.resolve(s)
        self.assertTrue(r.needs_review, f"{s!r} joined to {r.entity_id} via {r.method}")
        self.assertEqual(r.entity_id, "")
        return r

    def test_holdco_stays_separate_from_operating_company(self):
        apex = self.joined("Apex Logistics")
        group = self.joined("Apex Logistics Group")
        self.assertEqual(apex.method, "name-exact")
        self.assertNotEqual(apex.entity_id, group.entity_id)
        self.assertEqual(apex.entity.domain, "apexlogistics.com")
        self.assertEqual(group.entity.domain, "apexlogisticsgroup.co.uk")
        self.assertEqual(self.joined("Apex Logistics, Inc.").entity_id, apex.entity_id)
        self.assertEqual(self.joined("apexlogisticsgroup.co.uk").entity_id, group.entity_id)

    def test_crm_grouped_by_domain_with_one_survivor(self):
        rows = self.res.crm_rows()
        dupes = [r for r in rows if r["survivor"] == "no"]
        self.assertEqual(len(dupes), 6)
        self.assertEqual(len(rows), 50, "every CRM row is kept")
        by_id = {}
        for r in rows:
            by_id.setdefault(r["company_id"], []).append(r)
        for cid, group in by_id.items():
            self.assertEqual(sum(r["survivor"] == "yes" for r in group), 1, cid)
            self.assertEqual(len({r["domain"] for r in group}), 1, cid)
        for a91, a1 in [("A91001", "A1001"), ("A91020", "A1020"), ("A91035", "A1035"),
                        ("A91024", "A1024"), ("A91032", "A1032"), ("A91006", "A1006")]:
            self.assertEqual(next(r for r in rows if r["account_id"] == a91)["duplicate_of"], a1)

    def test_bare_name_shared_by_fund_and_customer_goes_to_human(self):
        for bare in ["Thornbury", "Silverbrook", "Ironvale", "Cobalt Lane", "Ashgrove", "Meridian Peak"]:
            r = self.refused(bare)
            self.assertEqual(r.method, "fund-or-customer", bare)
            self.assertEqual(sorted(c.kind for c in r.candidates), ["company", "fund"], bare)

    def test_full_names_on_either_side_still_join(self):
        self.assertEqual(self.joined("Thornbury Financial").entity.domain, "thornburyfinancial.com")
        self.assertEqual(self.joined("THORNBURYFINANCIAL").entity.domain, "thornburyfinancial.com")
        self.assertEqual(self.joined("Thornbury Equity").entity.kind, "fund")
        self.assertEqual(self.joined("Silverbrook Paper Corp").entity.domain, "silverbrookpaper.com")
        self.assertEqual(self.joined("Cobalt Lane Ventures").entity.kind, "fund")

    def test_confidence_threshold_and_unmatched(self):
        self.assertEqual(REVIEW_THRESHOLD, 0.75)
        r = self.res.resolve("Zenner Foods")
        self.assertEqual((r.method, r.entity_id, r.candidates), ("unmatched", "", []))
        self.assertEqual(self.res.resolve("").method, "empty")
        short = self.res.resolve("Apex")  # 4-char stem: prefix layer must not fire
        self.assertTrue(short.needs_review)


if __name__ == "__main__":
    unittest.main()
