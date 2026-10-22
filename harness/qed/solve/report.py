"""Write a run's Markdown and JSON reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from ..evidence import claims_markdown

if TYPE_CHECKING:
    from .engine import Run


def markdown(run: "Run") -> str:
    problem = run.problem
    best = run.best
    claims, conclusions = run.claims()
    tokens = run.tokens()
    status = f"solved at `{best.tier.label}`" if run.solved and best else "not solved to the target tier"
    lines = [
        f"# Run report: `{problem.id}`",
        "",
        f"- **Status:** {status} (target `{problem.target.label}`)",
        f"- **Kind:** {problem.kind}; trusted checks: {', '.join(problem.checks) or 'none'}",
        f"- **Attempts:** {len(run.attempts)} in {max((a.round for a in run.attempts), default=0)} round(s); "
        f"{run.finished - run.started:.1f}s; tokens in/out {tokens['input']:,}/{tokens['output']:,}",
        "",
        claims_markdown(claims, conclusions),
        "## Attempts",
        "",
        "| Round | # | Strategy | Tier | Verification |",
        "| --- | --- | --- | --- | --- |",
    ]
    for attempt in run.attempts:
        summary = attempt.summary().replace("|", "\\|").replace("\n", " ")
        if len(summary) > 240:
            summary = summary[:237] + "..."
        lines.append(f"| {attempt.round} | {attempt.index} | {attempt.strategy} | `{attempt.tier.label}` | {summary} |")
    if best is not None:
        lines += ["", f"## Best attempt (round {best.round}, `{best.strategy}`)", "", best.response.strip(), ""]
    return "\n".join(lines) + "\n"


def to_json(run: "Run") -> dict:
    claims, conclusions = run.claims()
    best = run.best
    return {
        "problem": run.problem.id,
        "kind": run.problem.kind,
        "target": run.problem.target.label,
        "solved": run.solved,
        "best": best.to_dict(full=False) if best else None,
        "claims": [c.to_dict() for c in claims],
        "conclusions": [c.to_dict() for c in conclusions],
        "attempts": [a.to_dict(full=False) for a in run.attempts],
        "tokens": run.tokens(),
        "seconds": round(run.finished - run.started, 3),
    }


def write_reports(run: "Run", directory: Path) -> None:
    (directory / "report.md").write_text(markdown(run), encoding="utf-8")
    (directory / "report.json").write_text(json.dumps(to_json(run), indent=2), encoding="utf-8")
