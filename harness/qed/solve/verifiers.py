"""Verifiers: the only way a candidate's evidence tier can rise above ``asserted``."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path
from typing import Any

from .. import kits
from ..evidence import Tier
from ..llm import Provider, ProviderError
from . import extract, lean, sandbox
from .problem import Problem
from .verdict import Verdict

EXEC_REQUIRED = "running model-written code was not authorized (pass --exec)"


def expected_answer(problem: Problem, answer: str) -> Verdict:
    ok = _same_value(answer, problem.expected or "")
    message = "matches the reference answer" if ok else f"{answer!r} differs from the reference answer"
    return Verdict("expected", "pass" if ok else "fail", Tier.VERIFIED, hard=True, message=message)


def _same_value(left: str, right: str) -> bool:
    a, b = normalize(left), normalize(right)
    if a == b:
        return True
    try:
        return Fraction(a) == Fraction(b)
    except (ValueError, ZeroDivisionError):
        return False


def normalize(value: str) -> str:
    return value.strip().strip("$").replace(" ", "").replace("\\,", "").rstrip(".").lower()


def trusted_checker(problem: Problem, candidate: Any, timeout: float = 120.0) -> Verdict:
    """Run the problem author's ``check(candidate)`` on the extracted candidate.

    The checker is trusted code; the candidate crosses into it only as JSON data.
    """

    result = sandbox.call(problem.checker or "", "check", candidate, timeout=timeout, memory_mb=2048)
    if not result.ok:
        return Verdict("checker", "error", Tier.VERIFIED, hard=True, message=f"checker failed to run: {result.error}")
    ok, message, score = _checker_result(result.value)
    data = {"score": score} if score is not None else {}
    return Verdict("checker", "pass" if ok else "fail", Tier.VERIFIED, hard=True, message=message, data=data)


def _checker_result(value: Any) -> tuple[bool, str, float | None]:
    """Accept a bool, [bool, message] or {"ok": bool, "message": str, "score": number}."""

    if isinstance(value, bool):
        return value, "accepted by the checker" if value else "rejected by the checker", None
    if isinstance(value, (list, tuple)) and value and isinstance(value[0], bool):
        return value[0], str(value[1]) if len(value) > 1 else "", None
    if isinstance(value, dict) and isinstance(value.get("ok"), bool):
        score = value.get("score")
        return value["ok"], str(value.get("message", "")), float(score) if isinstance(score, (int, float)) else None
    return False, f"checker returned {value!r}; expected a bool, [bool, message] or {{'ok': bool}}", None


def kit_differential(problem: Problem, source: str, allow_exec: bool, timeout: float = 20.0) -> Verdict:
    """Run a model-written implementation against a kit's exact oracle."""

    assert problem.implement is not None
    kit = kits.get(problem.implement.kit)
    name = f"kit:{kit.NAME}"
    if not allow_exec:
        return Verdict(name, "skipped", Tier.EMPIRICAL, hard=True, message=EXEC_REQUIRED)
    cases = kit.instances(problem.implement.seed, problem.implement.instances)
    seconds = 0.0
    for number, instance in enumerate(cases, 1):
        reference = kit.oracle(instance)
        result = sandbox.call(source, kit.ENTRYPOINT, instance, timeout=timeout)
        if not result.ok:
            return Verdict(
                name, "fail", Tier.EMPIRICAL, hard=True,
                message=f"instance {number}/{len(cases)} raised or timed out: {result.error}",
                data={"instance": instance},
            )
        seconds += result.seconds
        ok, why = kit.check(instance, result.value, reference)
        if not ok:
            return Verdict(
                name, "fail", Tier.EMPIRICAL, hard=True,
                message=f"instance {number}/{len(cases)}: {why}",
                data={"instance": instance, "output": result.value},
            )
    return Verdict(
        name, "pass", Tier.EMPIRICAL, hard=True,
        message=f"matched the exact oracle on all {len(cases)} generated instances ({seconds:.2f}s total)",
        limitations=[
            "agreement on generated instances is evidence, not a proof of correctness",
            "does not check that the code follows the paper's algorithm, or meets its running-time bound",
        ],
        data={"instances": len(cases), "seed": problem.implement.seed, "seconds": seconds},
    )


def lean_target(problem: Problem, text: str, allow_exec: bool, default_project: Path) -> Verdict:
    assert problem.lean is not None
    if not allow_exec:
        return Verdict("lean", "skipped", Tier.VERIFIED, hard=True, message="compiling model-written Lean was not authorized (pass --exec)")
    try:
        proof = extract.lean_proof(text)
    except ValueError as error:
        return Verdict("lean", "fail", Tier.VERIFIED, hard=True, message=str(error))
    project = Path(problem.lean.project) if problem.lean.project else default_project
    return lean.check_proof(problem.lean, proof, project)


CRITIC_SYSTEM = """You are a meticulous referee checking a proposed solution to a mathematics problem.
Find the first step that is wrong, unjustified or circular. Do not repair the solution and do not
reward length or confidence; a correct solution may be short. Reply with your reasoning, then end
with a ```json block of the form {"verdict": "accept" | "reject", "issues": ["..."]}."""


def critic_review(critic: Provider, problem: Problem, response: str) -> tuple[Verdict, Any]:
    prompt = f"## Problem\n\n{problem.statement}\n\n"
    if problem.context:
        prompt += f"## Context\n\n{problem.context}\n\n"
    prompt += f"## Proposed solution\n\n{response}\n"
    try:
        completion = critic.complete(CRITIC_SYSTEM, prompt)
    except ProviderError as error:
        return Verdict("critic", "error", Tier.ASSERTED, hard=False, message=str(error)), None
    try:
        decision = extract.json_object(completion.text)
        verdict = str(decision.get("verdict", "")).lower()
        issues = [str(issue) for issue in decision.get("issues", [])][:5]
    except (ValueError, AttributeError):
        return Verdict("critic", "error", Tier.ASSERTED, hard=False, message="critic reply had no verdict block"), completion
    status = "pass" if verdict == "accept" else "fail"
    message = "critic accepted" if status == "pass" else "critic: " + "; ".join(issues or ["rejected without detail"])
    return Verdict("critic", status, Tier.ASSERTED, hard=False, message=message[:1500], data={"issues": issues}), completion


def describe(candidate: Any) -> str:
    text = candidate if isinstance(candidate, str) else json.dumps(candidate)
    return text if len(text) <= 300 else text[:297] + "..."
