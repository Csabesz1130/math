import json
import tempfile
import unittest
from pathlib import Path

from qed.evidence import Tier
from qed.llm import ProviderError
from qed.llm.scripted import ScriptedProvider
from qed.solve import Engine, ImplementTarget, LeanTarget, Problem
from qed.solve import extract, lean, sandbox

HERE = Path(__file__).resolve().parent.parent
PROBLEMS = HERE / "problems"

GREEDY = (PROBLEMS / "replays" / "superstring.json")
BARKER_CHECKER = """
def check(seq):
    n = len(seq)
    if any(s not in (1, -1) for s in seq):
        return [False, "entries must be +-1"]
    peak = max(abs(sum(seq[i] * seq[i + k] for i in range(n - k))) for k in range(1, n))
    return {"ok": n == 13 and peak <= 1, "message": f"length {n}, peak {peak}", "score": -peak}
"""
BARKER13 = "```json\n[1,1,1,1,1,-1,-1,1,1,-1,1,-1,1]\n```"
ALL_ONES = "```json\n[1,1,1,1,1,1,1,1,1,1,1,1,1]\n```"


def engine(responses, **options):
    options.setdefault("samples", len(responses))
    options.setdefault("rounds", 1)
    options.setdefault("workers", 1)
    return Engine(ScriptedProvider(responses), **options)


class FailingProvider:
    name = "failing"

    def complete(self, system, prompt):
        raise ProviderError("declined")


class ExtractTest(unittest.TestCase):
    def test_final_answer(self):
        self.assertEqual(extract.final_answer("work\nANSWER: 42"), "42")
        self.assertEqual(extract.final_answer("so the result is ANSWER: $7$"), "7")
        self.assertEqual(extract.final_answer(r"thus \boxed{\frac{1}{2}}"), r"\frac{1}{2}")
        self.assertIsNone(extract.final_answer("the answer: 3"))

    def test_blocks(self):
        self.assertEqual(extract.json_object("x\n```json\n[1, 2]\n```"), [1, 2])
        with self.assertRaises(ValueError):
            extract.json_object("no block")
        self.assertIn("def f", extract.python_module("```python\ndef f():\n    pass\n```"))


class SandboxTest(unittest.TestCase):
    def test_call_and_failures(self):
        self.assertEqual(sandbox.call("def f(x):\n    return x * 2\n", "f", 21).value, 42)
        self.assertEqual(sandbox.call("def f():\n    return 'ok'\n", "f", None).value, "ok")
        self.assertIn("ZeroDivisionError", sandbox.call("def f(x):\n    return 1 / 0\n", "f", 1).error)
        result = sandbox.call("def f(x):\n    while True:\n        pass\n", "f", 1, timeout=1)
        self.assertFalse(result.ok)


class EngineTest(unittest.TestCase):
    def test_compute_with_reference_answer(self):
        problem = Problem(id="c", kind="compute", statement="?", expected="7")
        run = engine(["ANSWER: 8", "ANSWER: 7", "ANSWER: 7"]).solve(problem)
        self.assertTrue(run.solved)
        self.assertEqual(run.best.candidate, "7")
        self.assertEqual(run.best.tier, Tier.VERIFIED)

    def test_unchecked_answer_stays_asserted(self):
        problem = Problem(id="c", kind="compute", statement="?")
        run = engine(["ANSWER: 7", "ANSWER: 7", "ANSWER: 9"]).solve(problem)
        self.assertFalse(run.solved)
        self.assertEqual(run.best.tier, Tier.ASSERTED)
        self.assertEqual(run.best.agreement, 2)

    def test_construct_with_trusted_checker(self):
        problem = Problem(id="b", kind="construct", statement="Barker 13", checker=BARKER_CHECKER)
        run = engine([ALL_ONES, BARKER13]).solve(problem)
        self.assertTrue(run.solved)
        self.assertEqual(run.best.candidate[5], -1)
        self.assertTrue(run.attempts[0].rejected)

    def test_program_candidates_need_exec(self):
        program = "```python\ndef construct():\n    return [1,1,1,1,1,-1,-1,1,1,-1,1,-1,1]\n```"
        problem = Problem(id="b", kind="construct", statement="Barker 13", checker=BARKER_CHECKER)
        self.assertFalse(engine([program]).solve(problem).solved)
        self.assertTrue(engine([program], allow_exec=True).solve(problem).solved)

    def test_optimize_keeps_going_and_keeps_the_best_score(self):
        problem = Problem(id="b", kind="construct", statement="Barker 13", checker=BARKER_CHECKER.replace("peak <= 1", "True"), optimize=True)
        near = "```json\n[1,1,1,1,1,-1,-1,1,1,-1,1,-1,-1]\n```"
        run = engine([near, BARKER13], samples=1, rounds=2).solve(problem)
        self.assertEqual(len(run.attempts), 2)
        self.assertEqual(run.best.score, -1)

    def test_implementation_needs_exec_and_is_empirical(self):
        responses = json.loads(GREEDY.read_text())["responses"]
        problem = Problem(id="s", kind="implement", statement="SCS", implement=ImplementTarget("superstring", 15, 0))
        unrun = engine(responses).solve(problem)
        self.assertEqual(unrun.best.tier, Tier.ASSERTED)
        run = engine(responses, allow_exec=True).solve(problem)
        self.assertTrue(run.attempts[0].rejected)  # concatenation exceeds twice the optimum
        self.assertEqual(run.best.tier, Tier.EMPIRICAL)
        self.assertTrue(run.solved)

    def test_critic_never_raises_the_tier(self):
        critic = ScriptedProvider(['```json\n{"verdict": "accept", "issues": []}\n```'])
        problem = Problem(id="p", kind="prove", statement="1 + 1 = 2")
        run = engine(["Proof: arithmetic."], critic=critic).solve(problem)
        self.assertEqual(run.best.tier, Tier.ASSERTED)
        self.assertTrue(run.best.critic_accepted)

    def test_lean_is_skipped_without_exec_or_toolchain(self):
        problem = Problem(id="l", kind="prove", statement="n + 0 = n", lean=LeanTarget("theorem t (n : Nat) : n + 0 = n", "t"))
        run = engine(["```lean\nsimp\n```"], lean_project=Path("/nonexistent")).solve(problem)
        self.assertEqual(run.best.tier, Tier.ASSERTED)
        self.assertEqual(run.best.verdicts[0].status, "skipped")

    def test_provider_errors_are_recorded(self):
        problem = Problem(id="c", kind="compute", statement="?", expected="1")
        run = Engine(FailingProvider(), samples=2, rounds=1, related=0).solve(problem)
        self.assertIsNone(run.best)
        self.assertEqual(run.attempts[0].error, "declined")

    def test_run_records_are_unique_and_complete(self):
        problem = Problem(id="c", kind="compute", statement="?", expected="7")
        with tempfile.TemporaryDirectory() as runs:
            first = engine(["ANSWER: 7"], runs_dir=Path(runs)).solve(problem)
            second = engine(["ANSWER: 7"], runs_dir=Path(runs)).solve(problem)
            self.assertNotEqual(first.directory, second.directory)
            for name in ("attempts.jsonl", "training.jsonl", "report.md", "report.json"):
                self.assertTrue((first.directory / name).is_file(), name)
            row = json.loads((first.directory / "training.jsonl").read_text().splitlines()[0])
            self.assertEqual(row["reward"], 1.0)


class ProblemFileTest(unittest.TestCase):
    def test_example_problems_load(self):
        for path in sorted(PROBLEMS.glob("*.toml")):
            problem = Problem.load(path)
            self.assertTrue(problem.statement, path.name)
        self.assertEqual(Problem.load(PROBLEMS / "three-machine.toml").target, Tier.EMPIRICAL)
        checker = Problem.load(PROBLEMS / "psl2-length-28.toml").checker
        self.assertTrue(checker.rstrip().endswith("MAX_PSL = 2"))

    def test_invalid_problems(self):
        with self.assertRaises(ValueError):
            Problem(id="x", kind="guess", statement="?")
        with self.assertRaises(ValueError):
            Problem(id="x", kind="construct", statement="?", optimize=True)


class LeanTest(unittest.TestCase):
    def test_proof_body(self):
        self.assertEqual(lean.proof_body("theorem t : True := by\n  trivial"), "trivial")
        self.assertEqual(lean.proof_body("by\n  simp"), "simp")

    def test_forbidden_constructs_are_rejected_before_compiling(self):
        target = LeanTarget("theorem t : False", "t")
        for proof in ("sorry", "exact absurd\n\naxiom cheat : False", "set_option debug.skipKernelTC true in\n  trivial", "native_decide"):
            verdict = lean.check_proof(target, proof, Path("/nonexistent"))
            self.assertEqual(verdict.status, "fail", proof)
        self.assertEqual(lean.check_proof(target, "trivial", Path("/nonexistent")).status, "skipped")

    def test_axiom_parsing(self):
        permitted = ("propext", "Quot.sound", "Classical.choice")
        ok = lean._axiom_verdict("lean", "'t' depends on axioms: [propext, Classical.choice]", "t", permitted)
        self.assertEqual(ok.status, "pass")
        bad = lean._axiom_verdict("lean", "'t' depends on axioms: [propext, sorryAx]", "t", permitted)
        self.assertEqual(bad.status, "fail")
        none = lean._axiom_verdict("lean", "'t' does not depend on any axioms", "t", permitted)
        self.assertEqual(none.status, "pass")


if __name__ == "__main__":
    unittest.main()
