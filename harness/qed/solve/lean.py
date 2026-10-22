"""Lean checks: proofs of fixed statements, and the collection's Comparator challenges.

Elaborating Lean runs code (tactics, ``#eval``, ``run_cmd``), so a model-written
proof is only compiled when the caller passed ``--exec``. A passing compile is
followed by ``#print axioms`` and must use only the permitted axioms. The proof
body is also screened for commands that can weaken checking. Comparator, which
replays a proof in a fresh environment, is the authoritative check; use it for
results the collection ships (``qed verify``).
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

from ..evidence import Tier
from .problem import LeanTarget
from .verdict import Verdict

_DENY = re.compile(
    r"(\bsorry\b|\badmit\b|\baxiom\b|\bset_option\b|\bunsafe\b|\bimplemented_by\b|@\[extern|\brun_cmd\b|"
    r"\brun_tac\b|\brun_elab\b|#eval|\belab\b|\bmacro\b|\bsyntax\b|\bopen private\b|\binitialize\b|"
    r"\bnative_decide\b|\bdebug\.)"
)
_AXIOMS = re.compile(r"depends on axioms: \[([^\]]*)\]")


def unavailable_reason(project: Path) -> str | None:
    if shutil.which("lake") is None:
        return "Lean is not installed here (no `lake` on PATH)"
    if not any((project / name).is_file() for name in ("lakefile.lean", "lakefile.toml")):
        return f"{project} is not a Lake project"
    return None


def proof_body(text: str) -> str:
    """Accept either a tactic block or a full theorem; return the tactic block."""

    body = text.strip()
    match = re.search(r":=\s*by\b", body)
    if match:
        body = body[match.end():]
    elif body.startswith("by"):
        body = body[2:]
    return textwrap.dedent(body.strip("\n"))


def check_proof(target: LeanTarget, proof: str, project: Path, timeout: float = 1200.0) -> Verdict:
    name = "lean"
    body = proof_body(proof)
    forbidden = _DENY.search(body)
    if forbidden:  # a definite failure whether or not Lean is installed
        return Verdict(name, "fail", Tier.VERIFIED, hard=True, message=f"proof uses forbidden construct `{forbidden.group(0)}`")
    reason = unavailable_reason(project)
    if reason:
        return Verdict(name, "skipped", Tier.VERIFIED, hard=True, message=reason)
    source = "\n".join(f"import {module}" for module in target.imports)
    source += f"\n\n{target.statement} := by\n{textwrap.indent(body, '  ')}\n\n#print axioms {target.theorem}\n"
    digest = hashlib.sha256(source.encode()).hexdigest()[:12]
    scratch = project / ".qed"
    scratch.mkdir(exist_ok=True)
    path = scratch / f"Attempt_{digest}.lean"
    path.write_text(source, encoding="utf-8")
    try:
        completed = subprocess.run(
            ["lake", "env", "lean", str(path)], cwd=project, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return Verdict(name, "fail", Tier.VERIFIED, hard=True, message=f"Lean timed out after {timeout:g}s")
    output = completed.stdout + completed.stderr
    errors = [line for line in output.splitlines() if ": error" in line or line.startswith("error")]
    if completed.returncode != 0 or errors:
        return Verdict(name, "fail", Tier.VERIFIED, hard=True, message="Lean rejected the proof: " + " | ".join(errors[:5])[:1500])
    return _axiom_verdict(name, output, target.theorem, target.permitted_axioms)


def _axiom_verdict(name: str, output: str, theorem: str, permitted: tuple[str, ...]) -> Verdict:
    if "does not depend on any axioms" in output:
        return Verdict(name, "pass", Tier.VERIFIED, hard=True, message=f"{theorem} compiles and uses no axioms")
    match = _AXIOMS.search(output)
    if not match:
        return Verdict(name, "fail", Tier.VERIFIED, hard=True, message="could not read the #print axioms output")
    used = [a.strip() for a in match.group(1).split(",") if a.strip()]
    extra = [a for a in used if a not in permitted]
    if extra:
        return Verdict(name, "fail", Tier.VERIFIED, hard=True, message=f"proof depends on non-permitted axioms: {', '.join(extra)}")
    return Verdict(
        name, "pass", Tier.VERIFIED, hard=True,
        message=f"{theorem} compiles; axioms: {', '.join(used)}",
        limitations=["checked by Lean elaboration and #print axioms, not by a Comparator kernel replay"],
    )


def run_comparator(project: Path, config: str, timeout: float = 7200.0) -> Verdict:
    """Run one of the collection's Comparator challenges (``lake env comparator <config>``)."""

    name = f"comparator:{Path(config).stem}"
    reason = unavailable_reason(project)
    if reason is None:
        missing = [tool for tool in ("comparator", "landrun", "lean4export") if shutil.which(tool) is None]
        if missing:
            reason = "Comparator prerequisites missing from PATH: " + ", ".join(missing)
    if reason:
        return Verdict(name, "skipped", Tier.VERIFIED, hard=True, message=reason)
    try:
        completed = subprocess.run(
            ["lake", "env", "comparator", config], cwd=project, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return Verdict(name, "error", Tier.VERIFIED, hard=True, message=f"Comparator timed out after {timeout:g}s")
    tail = " | ".join((completed.stdout + completed.stderr).strip().splitlines()[-5:])
    if completed.returncode == 0:
        return Verdict(name, "pass", Tier.VERIFIED, hard=True, message=f"Comparator accepted {config}. {tail}"[:1500])
    return Verdict(name, "fail", Tier.VERIFIED, hard=True, message=f"Comparator rejected {config}: {tail}"[:1500])
