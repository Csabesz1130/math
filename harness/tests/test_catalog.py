import unittest

from qed.catalog import Catalog, plain
from qed.evidence import Claim, Conclusion, Source, Tier
from qed.search import Index


class CatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load()

    def test_counts_match_the_collection(self):
        self.assertEqual(len(self.catalog), 372)
        self.assertEqual(self.catalog.manuscript_count, 722)
        self.assertEqual(len(self.catalog.subjects()), 17)
        self.assertNotIn("Unclassified", self.catalog.subjects())

    def test_comparator_challenges_are_linked(self):
        self.assertEqual(sum(len(f.challenges) for f in self.catalog), 405)
        family = self.catalog.get(165)
        self.assertEqual({c.name for c in family.challenges}, {"CompleteCrossing", "BipartiteCrossing"})
        self.assertEqual(family.formal_tier, Tier.FORMALIZED)
        bipartite = next(c for c in family.challenges if c.name == "BipartiteCrossing")
        self.assertEqual(bipartite.declaration, "OAI.Zarankiewicz.mainTarget_proof")
        self.assertIn("Classical.choice", bipartite.permitted_axioms)

    def test_review_status_is_read(self):
        self.assertEqual(self.catalog.review_status, "unchecked")

    def test_unformalized_family_is_published(self):
        self.assertEqual(self.catalog.get(109).formal_tier, Tier.PUBLISHED)

    def test_paper_sources_exclude_tex_runtime(self):
        manuscript = self.catalog.get(124).manuscripts[0]
        sources = self.catalog.paper_sources(manuscript)
        self.assertTrue(sources[0].name == "paper.tex")
        self.assertFalse(any("runtime" in p.parts for p in sources))

    def test_plain_strips_markup(self):
        self.assertEqual(plain("<i>K</i><sub><i>n</i></sub> and $`x^2`$ ([Lean](lean/docs/001.md))"), "K_n and x^2")

    def test_search_finds_the_relevant_family(self):
        index = Index(self.catalog)
        self.assertEqual(index.search("scheduling precedence identical machines", 1)[0].family.id, "124")
        self.assertEqual(index.search("binary sequence autocorrelation", 1)[0].family.id, "179")
        self.assertEqual(index.search("degree sequence switch chain", 1)[0].family.id, "131")


class EvidenceTest(unittest.TestCase):
    def test_conclusion_is_as_weak_as_its_weakest_support(self):
        strong = Claim("a", Tier.VERIFIED, [Source("check", "x")])
        weak = Claim("b", Tier.EMPIRICAL, [Source("measurement", "y")])
        self.assertEqual(Conclusion("c", [strong, weak]).tier, Tier.EMPIRICAL)
        self.assertEqual(Conclusion("c", [strong]).tier, Tier.VERIFIED)
        self.assertEqual(Conclusion("c", []).tier, Tier.UNKNOWN)

    def test_tier_parse(self):
        self.assertIs(Tier.parse("Formalized"), Tier.FORMALIZED)
        with self.assertRaises(ValueError):
            Tier.parse("proven")


if __name__ == "__main__":
    unittest.main()
