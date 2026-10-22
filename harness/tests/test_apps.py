import itertools
import random
import unittest
from collections import Counter

from qed.apps import crossbar, null_model, pulse_codes
from qed.catalog import Catalog
from qed.evidence import Tier

try:
    import numpy  # noqa: F401

    from qed.apps import maxcut
except ImportError:
    maxcut = None


class PulseCodeTest(unittest.TestCase):
    def test_barker_table(self):
        for n, seq in pulse_codes.BARKER.items():
            self.assertEqual(len(seq), n)
            self.assertEqual(pulse_codes.psl(seq), 1)

    def test_exhaustive_search_matches_brute_force(self):
        for n in range(3, 13):
            best = min(pulse_codes.psl((1,) + t) for t in itertools.product((1, -1), repeat=n - 1))
            for bound in (1, 2, 3):
                status, seq, _ = pulse_codes.exhaustive_psl(n, bound)
                self.assertEqual(status == "found", best <= bound, (n, bound))
                if seq:
                    self.assertLessEqual(pulse_codes.psl(seq), bound)

    def test_flip_energies_match_recomputation(self):
        rng = random.Random(1)
        for n in (5, 23):
            s = [rng.choice((1, -1)) for _ in range(n)]
            energies = pulse_codes._flip_energies(n, 4)(s, [0] + pulse_codes.autocorrelations(s))
            for i in range(n):
                t = list(s)
                t[i] = -t[i]
                self.assertEqual(energies[i], sum(c ** 4 for c in pulse_codes.autocorrelations(t)))

    def test_barker_length_is_optimal(self):
        result = pulse_codes.run(13, seconds=0.1, exhaustive_seconds=1)
        self.assertEqual(result.outputs["psl"], 1)
        self.assertTrue(all(c.tier == Tier.VERIFIED for c in result.conclusions))

    def test_length_20_is_proved_optimal_by_search(self):
        result = pulse_codes.run(20, seconds=2, exhaustive_seconds=10, catalog=Catalog.load())
        self.assertEqual(result.outputs["psl"], 2)
        optimal = [c for c in result.conclusions if "PSL-optimal" in c.statement]
        self.assertEqual(optimal[0].tier, Tier.VERIFIED)


class CrossbarTest(unittest.TestCase):
    def test_drawing_attains_zarankiewicz(self):
        for m in range(1, 8):
            for n in range(1, 8):
                pairs, points = crossbar.count_crossings(*crossbar.drawing(m, n))
                self.assertEqual(pairs, crossbar.zarankiewicz(m, n))
                self.assertEqual(points, pairs)

    def test_harary_hill_values(self):
        self.assertEqual([crossbar.harary_hill(n) for n in range(5, 11)], [1, 3, 9, 18, 36, 60])

    def test_optimality_rests_on_the_formal_lower_bound(self):
        result = crossbar.run(6, 7, catalog=Catalog.load())
        self.assertEqual(result.outputs["crossings"], 54)  # Z(6, 7) = 3 * 2 * 3 * 3
        self.assertEqual(result.conclusions[0].tier, Tier.FORMALIZED)
        self.assertIn("crossbar-6x7.svg", result.files)


class NullModelTest(unittest.TestCase):
    def _degrees(self, adj):
        return [len(a) for a in adj]

    def test_chains_preserve_degrees(self):
        graph = null_model.demo_graph(n=60, ring=6)
        for chain_type in (null_model.EdgeSwapChain, null_model.TheoremChain):
            walker = chain_type(graph, random.Random(0))
            before = self._degrees(graph.adjacency())
            for _ in range(5000):
                walker.step()
            adj, edges = walker.snapshot()
            self.assertEqual(self._degrees(adj), before)
            self.assertEqual(len(edges), len(graph.edges))

    def test_theorem_chain_reaches_every_realisation(self):
        cycle = null_model.Graph(6, [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (0, 5)], [str(i) for i in range(6)])
        walker = null_model.TheoremChain(cycle, random.Random(3))
        seen = Counter()
        for i in range(60000):
            walker.step()
            if i % 10 == 0:
                adj, edges = walker.snapshot()
                seen[frozenset(edges)] += 1
        self.assertEqual(len(seen), 70)  # 60 hexagons + 10 pairs of triangles

    def test_certified_steps(self):
        self.assertLess(null_model.certified_steps(8, 8, 0.25), null_model.certified_steps(8, 8, 0.01))
        with self.assertRaises(ValueError):
            null_model.certified_steps(8, 8, 1.5)

    def test_certified_mode_rests_on_the_formal_bound(self):
        graph = null_model.Graph(6, [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (0, 5)], [str(i) for i in range(6)])
        result = null_model.run(graph, chain="theorem", certify_tv=0.25, samples=3, catalog=Catalog.load())
        sampler = next(c for c in result.claims if "total variation" in c.statement)
        self.assertEqual(sampler.tier, Tier.FORMALIZED)

    def test_certify_requires_the_theorem_chain(self):
        with self.assertRaises(ValueError):
            null_model.run(null_model.demo_graph(n=40, ring=5), chain="edge", certify_tv=0.1)

    def test_demo_detects_the_planted_ring(self):
        result = null_model.run(null_model.demo_graph(), samples=80)
        self.assertGreater(result.outputs["statistics"]["triangles"]["z"], 3)
        self.assertGreaterEqual(result.outputs["demo_check"]["planted_in_top"], 8)


@unittest.skipIf(maxcut is None, "numpy not installed")
class MaxCutTest(unittest.TestCase):
    def test_certificate_bounds_the_exact_optimum(self):
        rng = random.Random(0)
        for trial in range(15):
            n = rng.randint(4, 11)
            edges = [(u, v, float(rng.choice([1, 2, 3, -1]))) for u in range(n) for v in range(u + 1, n) if rng.random() < 0.5]
            if not edges:
                continue
            optimum = maxcut.exact_max_cut(n, edges)
            brute = max(maxcut.cut_value(edges, [(mask >> i) & 1 for i in range(n)]) for mask in range(1 << n))
            self.assertAlmostEqual(optimum, brute)
            result = maxcut.run([str(i) for i in range(n)], edges, seed=trial)
            self.assertGreaterEqual(result.outputs["upper_bound"], optimum - 1e-9)
            self.assertLessEqual(result.outputs["cut_weight"], optimum + 1e-9)

    def test_demo_certified_ratio(self):
        result = maxcut.run(*maxcut.demo_graph(n=80), catalog=Catalog.load())
        self.assertGreater(result.outputs["certified_ratio"], 0.85)
        self.assertEqual(result.conclusions[0].tier, Tier.VERIFIED)
        self.assertEqual(result.conclusions[-1].tier, Tier.FORMALIZED)


if __name__ == "__main__":
    unittest.main()
