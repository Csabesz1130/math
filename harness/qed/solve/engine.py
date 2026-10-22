"""Generate, verify, refine.

Each round samples several attempts in parallel, each steered toward a
different strategy, and runs every applicable verifier on each. The run stops
as soon as an attempt reaches the problem's target tier; otherwise the
verifiers' messages (counterexamples, failing instances, referee objections)
seed the next round. More rounds and samples buy more test-time compute; the
verifiers decide what the compute bought.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import kits
from ..catalog import Catalog, plain
from ..evidence import Claim, Conclusion, Source, Tier
from ..llm import Provider, ProviderError
from ..search import Index
from . import extract, sandbox, verifiers
from .problem import Problem
from .verdict import Verdict

STRATEGIES = {
    "default": (
        ("direct", "Work directly toward a complete solution."),
        ("small-cases", "Begin by working out small cases or examples explicitly, find the pattern, then generalise and justify it."),
        ("counterexample", "Before trying to prove anything, search seriously for a counterexample; if the search fails, let the obstruction you found guide the argument."),
        ("reformulate", "Reformulate the problem in a different but equivalent language (algebraic, combinatorial, probabilistic or computational) and solve the reformulation."),
    ),
    "implement": (
        ("faithful", "Transcribe the algorithm from the source faithfully, keeping its structure and invariants recognisable."),
        ("invariants", "Identify the invariants the correctness proof relies on, implement them explicitly, and assert them in the code."),
        ("reference-first", "Reason through a brute-force reference on tiny inputs first, then write the efficient algorithm so that it provably agrees with it."),
        ("simplest", "Write the simplest implementation that meets the stated guarantee exactly; avoid optimisations that complicate correctness."),
    ),
}

CONTRACTS = {
    "compute": "Finish with one final line of the form `ANSWER: <value>`, giving the exact value.",
    "construct": (
        "Give the object as one ```json block at the end of your reply; a program will check it exactly. "
        "Alternatively, give a Python 3 program in one ```python block defining `construct()` that returns the "
        "object as JSON-compatible data; it runs with a {seconds:g}-second limit, standard library only, and only if "
        "the operator allows execution."
    ),
    "prove": "Write a complete, rigorous proof. Say explicitly which steps rely on cited results.",
    "lean": (
        "Give a Lean 4 proof of exactly the stated theorem in one ```lean block: the tactic block after `:= by`. "
        "The given statement is always used, so changing it has no effect. `sorry`, `axiom`, `set_option`, "
        "`native_decide` and metaprogramming commands are rejected; only the axioms propext, Quot.sound and "
        "Classical.choice are permitted."
    ),
    "implement": (
        "Give one complete Python 3 module in a ```python block that defines `{entry}`. Use the standard library "
        "only. It will be run on generated instances and compared with an exact oracle.\n\nInterface:\n{interface}"
    ),
}

SYSTEM = """You are working on a mathematics problem posed by a verification harness.
Independent checks will run on your answer: {checks}. Only checked claims count: a clearly
labelled partial result is worth more than an unjustified complete one, and saying that you could
not finish is acceptable. Related results are listed with how established they are; do not rely
on a `published` or `asserted` result without saying so.

{contract}"""


@dataclass
class Attempt:
    round: int
    index: int
    strategy: str
    provider: str
    prompt: str = ""
    response: str = ""
    candidate: Any = None
    error: str = ""
    verdicts: list[Verdict] = field(default_factory=list)
    agreement: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0

    @property
    def rejected(self) -> bool:
        return bool(self.error) or any(v.hard and v.failed for v in self.verdicts)

    @property
    def tier(self) -> Tier:
        if self.rejected:
            return Tier.UNKNOWN
        passed = [v.tier for v in self.verdicts if v.hard and v.passed]
        return min(passed) if passed else Tier.ASSERTED

    @property
    def critic_accepted(self) -> bool | None:
        for verdict in self.verdicts:
            if verdict.verifier == "critic" and verdict.status in ("pass", "fail"):
                return verdict.passed
        return None

    @property
    def score(self) -> float | None:
        scores = [v.data["score"] for v in self.verdicts if v.passed and "score" in v.data]
        return max(scores) if scores else None

    def rank(self) -> tuple:
        critic = {True: 0, None: 1, False: 2}[self.critic_accepted]
        score = -self.score if self.score is not None else 0.0
        return (self.rejected, self.tier, score, critic, -self.agreement, self.round, self.index)

    def summary(self) -> str:
        if self.error:
            return f"error: {self.error}"
        parts = [f"{v.verifier} {v.status}" + (f" ({v.message})" if v.message and not v.passed else "") for v in self.verdicts]
        return "; ".join(parts) or "no verifier applied"

    def to_dict(self, *, full: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {
            "round": self.round,
            "index": self.index,
            "strategy": self.strategy,
            "provider": self.provider,
            "tier": self.tier.label,
            "rejected": self.rejected,
            "agreement": self.agreement,
            "error": self.error,
            "candidate": self.candidate,
            "score": self.score,
            "verdicts": [v.to_dict() for v in self.verdicts],
            "tokens": {"input": self.input_tokens, "output": self.output_tokens},
            "seconds": round(self.seconds, 3),
        }
        if full:
            out["prompt"] = self.prompt
            out["response"] = self.response
        return out


class ContextTooLarge(ValueError):
    pass


@dataclass
class Run:
    problem: Problem
    attempts: list[Attempt]
    started: float
    finished: float
    directory: Path | None = None

    @property
    def best(self) -> Attempt | None:
        usable = [a for a in self.attempts if not a.error]
        return min(usable, key=Attempt.rank) if usable else None

    @property
    def solved(self) -> bool:
        best = self.best
        return best is not None and not best.rejected and best.tier <= self.problem.target

    def tokens(self) -> dict[str, int]:
        return {
            "input": sum(a.input_tokens for a in self.attempts),
            "output": sum(a.output_tokens for a in self.attempts),
        }

    def claims(self) -> tuple[list[Claim], list[Conclusion]]:
        best = self.best
        if best is None or best.rejected:
            claim = Claim(
                f"No attempt at {self.problem.id} survived verification",
                Tier.UNKNOWN,
                [Source("check", v.verifier, v.message) for a in self.attempts[-3:] for v in a.verdicts if v.failed][:5],
            )
            return [claim], [Conclusion(f"{self.problem.id} is unsolved by this run", [claim])]
        checks = [v for v in best.verdicts if v.hard and v.passed]
        skipped = [v for v in best.verdicts if v.status == "skipped"]
        limitations = [lim for v in checks for lim in v.limitations]
        limitations += [f"{v.verifier} not run: {v.message}" for v in skipped]
        if best.critic_accepted is not None:
            limitations.append("model referee " + ("accepted" if best.critic_accepted else "raised objections"))
        claims: list[Claim] = []
        if self.problem.kind == "implement" and checks:
            data = checks[0].data
            claims.append(Claim(
                f"The implementation matches the exact oracle on {data.get('instances')} generated instances (seed {data.get('seed')})",
                Tier.VERIFIED, [Source("check", checks[0].verifier, checks[0].message)],
            ))
        sources = [Source("check", v.verifier, v.message) for v in checks] or [Source("model", best.provider, best.strategy)]
        data = {"agreement": f"{best.agreement} of {len([a for a in self.attempts if not a.error])} attempts"} if best.agreement else {}
        if best.score is not None:
            data["score"] = best.score
        claims.append(Claim(
            _main_statement(self.problem, best), best.tier, sources, limitations, data,
        ))
        verdict = "solved" if self.solved else "not solved to the target tier"
        return claims, [Conclusion(f"{self.problem.id} is {verdict} (target: {self.problem.target.label})", claims[-1:])]


def _main_statement(problem: Problem, attempt: Attempt) -> str:
    if problem.kind == "compute":
        return f"The answer to {problem.id} is {attempt.candidate}"
    if problem.kind == "construct":
        return f"The constructed object satisfies {problem.id}: {verifiers.describe(attempt.candidate)}"
    if problem.kind == "implement":
        return f"The implementation meets the {problem.implement.kit} kit's guarantee for {problem.id}"
    return f"The proof of {problem.id} is correct"


class Engine:
    def __init__(
        self,
        solver: Provider,
        *,
        critic: Provider | None = None,
        catalog: Catalog | None = None,
        samples: int = 4,
        rounds: int = 3,
        workers: int = 4,
        allow_exec: bool = False,
        related: int = 5,
        max_context_chars: int = 400_000,
        runs_dir: Path | None = None,
        lean_project: Path | None = None,
    ):
        self.solver = solver
        self.critic = critic
        self.catalog = catalog
        self.index = Index(catalog) if catalog is not None else None
        self.samples = samples
        self.rounds = rounds
        self.workers = workers
        self.allow_exec = allow_exec
        self.related = related
        self.max_context_chars = max_context_chars
        self.runs_dir = runs_dir
        self.lean_project = lean_project or (catalog.root / "lean" if catalog is not None else Path("lean"))

    # -- prompt -----------------------------------------------------------------

    def system_prompt(self, problem: Problem) -> str:
        checks = ", ".join(problem.checks) or "none beyond a model referee, so your argument must stand on its own"
        if problem.kind == "implement":
            kit = kits.get(problem.implement.kit)
            contract = CONTRACTS["implement"].format(entry=kit.ENTRYPOINT, interface=kit.INTERFACE.strip())
        elif problem.lean is not None:
            contract = CONTRACTS["prove"] + "\n\n" + CONTRACTS["lean"]
        else:
            contract = CONTRACTS[problem.kind].format(seconds=problem.program_seconds)
        if problem.optimize:
            contract += "\n\nThe checker scores valid answers (higher is better). Aim for the best score you can reach."
        return SYSTEM.format(checks=checks, contract=contract)

    def context(self, problem: Problem) -> str:
        sections: list[str] = []
        if self.catalog is not None and self.related > 0:
            families = [self.catalog.get(fid) for fid in problem.families]
            for hit in self.index.search(f"{problem.statement} {problem.context}", self.related, relative=0.4):
                if hit.family not in families:
                    families.append(hit.family)
            lines = [
                f"- [{f.id}] {plain(f.title)} ({f.subject}; `{f.formal_tier.label}`): {plain(f.summary)}"
                for f in families[: max(self.related, len(problem.families))]
            ]
            sections.append("## Related results in the collection\n\n" + "\n".join(lines))
        if problem.papers:
            sections.append("## Source papers\n\n" + self._papers(problem))
        return "\n\n".join(sections)

    def _papers(self, problem: Problem) -> str:
        if self.catalog is None:
            raise ContextTooLarge("source papers need the catalogue (run inside the collection or pass --repo)")
        chunks: list[str] = []
        for ref in problem.papers:
            if ref.isdigit():
                manuscripts = self.catalog.get(ref).manuscripts
            else:
                manuscripts = [m for f in self.catalog for m in f.manuscripts if m.path == ref or m.directory == ref.rstrip("/")]
                if not manuscripts:
                    raise ContextTooLarge(f"paper {ref!r} is not a manuscript path or family id in the catalogue")
            for manuscript in manuscripts:
                sources = self.catalog.paper_sources(manuscript)
                if not sources:
                    chunks.append(f"### {plain(manuscript.title)}\n\n(no LaTeX source; abstract only)\n\n{plain(manuscript.abstract)}")
                    continue
                for source in sources:
                    rel = source.relative_to(self.catalog.root)
                    chunks.append(f"### {rel}\n\n```latex\n{source.read_text(errors='replace')}\n```")
        text = "\n\n".join(chunks)
        if len(text) > self.max_context_chars:
            raise ContextTooLarge(
                f"the source papers are {len(text):,} characters, above --max-context-chars {self.max_context_chars:,}; "
                "raise the limit or name a single manuscript directory instead of a family"
            )
        return text

    def prompt(self, problem: Problem, context: str, strategy: str, feedback: str) -> str:
        parts = [f"# Problem `{problem.id}`\n\n{problem.statement}"]
        if problem.lean is not None:
            parts.append(f"## Formal statement (Lean 4)\n\n```lean\n{problem.lean.statement} := by\n  sorry\n```")
        if problem.context:
            parts.append(f"## Context\n\n{problem.context}")
        if context:
            parts.append(context)
        parts.append(f"## Approach for this attempt\n\n{strategy}")
        if feedback:
            parts.append(feedback)
        return "\n\n".join(parts)

    # -- loop -------------------------------------------------------------------

    def solve(self, problem: Problem) -> Run:
        started = time.time()
        system = self.system_prompt(problem)
        context = self.context(problem)
        strategies = STRATEGIES["implement" if problem.kind == "implement" else "default"]
        directory = self._run_directory(problem, started)
        attempts: list[Attempt] = []
        feedback = ""
        for round_number in range(1, self.rounds + 1):
            jobs = []
            for index in range(self.samples):
                name, text = strategies[(index + round_number - 1) % len(strategies)]
                jobs.append((round_number, index, name, self.prompt(problem, context, text, feedback)))
            with ThreadPoolExecutor(max_workers=max(1, self.workers)) as pool:
                batch = list(pool.map(lambda job: self._attempt(problem, system, *job), jobs))
            attempts.extend(batch)
            if problem.kind == "compute":
                _vote(attempts)
            self._log(directory, batch)
            best = min((a for a in attempts if not a.error), key=Attempt.rank, default=None)
            if best is not None and not best.rejected and best.tier <= problem.target and not problem.optimize:
                break
            feedback = _feedback(batch, best if problem.optimize else None)
        run = Run(problem, attempts, started, time.time(), directory)
        if directory is not None:
            from .report import write_reports

            write_reports(run, directory)
        return run

    def _attempt(self, problem: Problem, system: str, round_number: int, index: int, strategy: str, prompt: str) -> Attempt:
        attempt = Attempt(round_number, index, strategy, self.solver.name, prompt=prompt)
        start = time.perf_counter()
        try:
            completion = self.solver.complete(system, prompt)
        except ProviderError as error:
            attempt.error = str(error)
            attempt.seconds = time.perf_counter() - start
            return attempt
        attempt.response = completion.text
        attempt.input_tokens = completion.input_tokens
        attempt.output_tokens = completion.output_tokens
        try:
            attempt.candidate = self._candidate(problem, completion.text)
        except ValueError as error:
            attempt.verdicts.append(Verdict("format", "fail", Tier.UNKNOWN, hard=True, message=str(error)))
            attempt.seconds = time.perf_counter() - start
            return attempt
        attempt.verdicts.extend(self._verify(problem, attempt))
        attempt.seconds = time.perf_counter() - start
        return attempt

    def _candidate(self, problem: Problem, text: str) -> Any:
        if problem.kind == "compute":
            answer = extract.final_answer(text)
            if answer is None:
                raise ValueError("the response has no `ANSWER:` line")
            return answer
        if problem.kind == "construct":
            if extract.fenced(text, "json") is not None or extract.fenced(text, "python", "py") is None:
                return extract.json_object(text)
            # A search program in the AlphaEvolve / FunSearch style: run it, check what it returns.
            if not self.allow_exec:
                raise ValueError("the candidate is a construct() program; running it was not authorized (pass --exec)")
            result = sandbox.call(extract.python_module(text), "construct", None, timeout=problem.program_seconds, memory_mb=2048)
            if not result.ok:
                raise ValueError(f"construct() failed: {result.error}")
            return result.value
        if problem.kind == "implement":
            return extract.python_module(text)
        return text

    def _verify(self, problem: Problem, attempt: Attempt) -> list[Verdict]:
        verdicts: list[Verdict] = []
        if problem.lean is not None:
            verdicts.append(verifiers.lean_target(problem, attempt.response, self.allow_exec, self.lean_project))
        if problem.checker:
            verdicts.append(verifiers.trusted_checker(problem, attempt.candidate))
        if problem.expected is not None and problem.kind == "compute":
            verdicts.append(verifiers.expected_answer(problem, attempt.candidate))
        if problem.implement is not None:
            verdicts.append(verifiers.kit_differential(problem, attempt.candidate, self.allow_exec))
        hard_failure = any(v.hard and v.failed for v in verdicts)
        hard_pass = any(v.hard and v.passed for v in verdicts)
        if self.critic is not None and not hard_failure and (problem.kind == "prove" or not hard_pass):
            verdict, completion = verifiers.critic_review(self.critic, problem, attempt.response)
            if completion is not None:
                attempt.input_tokens += completion.input_tokens
                attempt.output_tokens += completion.output_tokens
            verdicts.append(verdict)
        return verdicts

    # -- records ----------------------------------------------------------------

    def _run_directory(self, problem: Problem, started: float) -> Path | None:
        if self.runs_dir is None:
            return None
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(started))
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        for suffix in range(1000):
            # Runs started within the same second must never share a record.
            directory = self.runs_dir / f"{stamp}-{_slug(problem.id)}" if suffix == 0 else self.runs_dir / f"{stamp}-{_slug(problem.id)}-{suffix}"
            try:
                directory.mkdir()
                return directory
            except FileExistsError:
                continue
        raise RuntimeError(f"could not create a unique run directory under {self.runs_dir}")

    def _log(self, directory: Path | None, batch: list[Attempt]) -> None:
        if directory is None:
            return
        with (directory / "attempts.jsonl").open("a", encoding="utf-8") as attempts, \
                (directory / "training.jsonl").open("a", encoding="utf-8") as training:
            for attempt in batch:
                attempts.write(json.dumps(attempt.to_dict()) + "\n")
                if attempt.error:
                    continue
                # Verifier outcomes as rewards: a dataset for rejection-sampling
                # fine-tuning or RL with verifiable rewards.
                training.write(json.dumps({
                    "prompt_sha256": hashlib.sha256(attempt.prompt.encode()).hexdigest(),
                    "prompt": attempt.prompt,
                    "response": attempt.response,
                    "tier": attempt.tier.label,
                    "reward": 0.0 if attempt.rejected else {Tier.VERIFIED: 1.0, Tier.EMPIRICAL: 0.5}.get(attempt.tier, 0.0),
                    "verdicts": [v.to_dict() for v in attempt.verdicts],
                }) + "\n")


def _vote(attempts: list[Attempt]) -> None:
    """Self-consistency for computed answers: count agreeing, unrejected attempts."""

    answers = Counter(
        verifiers.normalize(str(a.candidate)) for a in attempts if not a.rejected and a.candidate is not None
    )
    for attempt in attempts:
        if attempt.candidate is not None and not attempt.rejected:
            attempt.agreement = answers[verifiers.normalize(str(attempt.candidate))]


def _feedback(batch: list[Attempt], best: Attempt | None = None) -> str:
    """Verifier messages from this round; in optimize mode, also the best scored attempt so far."""

    notes = []
    for attempt in batch:
        failures = [v for v in attempt.verdicts if v.failed]
        if attempt.error or not failures:
            continue
        for verdict in failures[:2]:
            note = f"- `{attempt.strategy}` attempt rejected by **{verdict.verifier}**: {verdict.message}"
            if "instance" in verdict.data:
                note += f"\n  Failing input: `{json.dumps(verdict.data['instance'])[:1500]}`"
            notes.append(note)
    if best is not None and best.score is not None and not best.rejected:
        detail = "; ".join(v.message for v in best.verdicts if v.passed and v.message) or best.summary()
        text = f"## Best verified result so far\n\nScore {best.score:g} ({detail}). Improve on it.\n"
        if notes:
            text += "\nRejected attempts:\n\n" + "\n".join(notes[:6])
        return text + f"\n\nThe best attempt so far:\n\n<previous_attempt>\n{best.response[-16000:]}\n</previous_attempt>"
    if not notes:
        return ""
    shown = next((a for a in batch if not a.error and a.response), None)
    text = "## Feedback from the previous round\n\nThe checks rejected these attempts. Address every objection.\n\n" + "\n".join(notes[:8])
    if shown is not None:
        text += f"\n\nOne previous attempt (`{shown.strategy}`), for reference:\n\n<previous_attempt>\n{shown.response[-16000:]}\n</previous_attempt>"
    return text


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in text)[:60]
