import itertools
import random
import unittest

from qed import kits
from qed.kits import scheduling, superstring


def brute_makespan(instance):
    n = instance["jobs"]
    for horizon in range(1, n + 1):
        for slots in itertools.product(range(horizon), repeat=n):
            if all(slots.count(t) <= 3 for t in range(horizon)) and all(slots[u] < slots[v] for u, v in instance["edges"]):
                return horizon


def brute_superstring(strings):
    alphabet = sorted(set("".join(strings)))
    for length in range(1, 30):
        for letters in itertools.product(alphabet, repeat=length):
            text = "".join(letters)
            if all(s in text for s in strings):
                return length


class SchedulingKitTest(unittest.TestCase):
    def test_oracle_matches_brute_force(self):
        rng = random.Random(5)
        for _ in range(40):
            n = rng.randint(3, 7)
            shape = rng.choice(["random", "layered", "chains", "intree", "outtree"])
            instance = {"jobs": n, "edges": scheduling._edges(rng, n, shape)}
            self.assertEqual(scheduling.oracle(instance), brute_makespan(instance), instance)

    def test_adversarial_instances_defeat_list_scheduling(self):
        # The kit must reject a transcription that silently degrades to a greedy rule.
        for seed in range(5):
            cases = scheduling.instances(seed, 40)
            failures = sum(not scheduling.check(c, scheduling.baseline(c), scheduling.oracle(c))[0] for c in cases)
            self.assertGreater(failures, 0, f"seed {seed}")

    def test_check_rejects_infeasible_schedules(self):
        instance = {"jobs": 4, "edges": [[0, 1]]}
        self.assertFalse(scheduling.check(instance, [0, 0, 0, 0], 2)[0])  # four jobs in one step
        self.assertFalse(scheduling.check(instance, [1, 0, 0, 0], 2)[0])  # precedence violated
        self.assertFalse(scheduling.check(instance, [0, 2, 0, 1], 2)[0])  # not optimal
        self.assertTrue(scheduling.check(instance, [0, 1, 0, 1], 2)[0])


class SuperstringKitTest(unittest.TestCase):
    def test_oracle_matches_brute_force(self):
        rng = random.Random(3)
        for _ in range(30):
            strings = ["".join(rng.choice("ab") for _ in range(rng.randint(1, 4))) for _ in range(rng.randint(1, 4))]
            self.assertEqual(superstring.oracle({"strings": strings}), brute_superstring(strings), strings)

    def test_concatenation_is_rejected_and_greedy_passes(self):
        cases = superstring.instances(0, 40)
        self.assertTrue(any(not superstring.check(c, "".join(c["strings"]), superstring.oracle(c))[0] for c in cases))
        self.assertTrue(all(superstring.check(c, superstring.baseline(c), superstring.oracle(c))[0] for c in cases))

    def test_registry(self):
        self.assertEqual(kits.names(), ["superstring", "three-machine"])
        with self.assertRaises(KeyError):
            kits.get("nope")


if __name__ == "__main__":
    unittest.main()
