"""Problem specifications.

A problem is a TOML file. ``kind`` fixes what the model must return and how it
can be checked:

- ``compute``: a value, given on a final ``ANSWER:`` line.
- ``construct``: an object (counterexample, certificate, configuration) as JSON,
  or a Python program whose ``construct()`` returns it (run only with ``--exec``).
- ``prove``: a proof; with a ``[lean]`` table, a Lean tactic proof of a fixed statement.
- ``implement``: a Python module, differentially tested against a kit's exact oracle.

Only the problem author's own material is trusted: ``expected``, ``checker``
and the kit. Nothing the model writes can change what is checked.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..evidence import Tier

KINDS = ("compute", "construct", "prove", "implement")
DEFAULT_AXIOMS = ("propext", "Quot.sound", "Classical.choice")


@dataclass
class LeanTarget:
    statement: str  # the theorem header without ":=", e.g. "theorem foo (n : ℕ) : n + 0 = n"
    theorem: str
    imports: tuple[str, ...] = ("Mathlib",)
    project: str | None = None  # Lake project directory; defaults to the collection's lean/
    permitted_axioms: tuple[str, ...] = DEFAULT_AXIOMS


@dataclass
class ImplementTarget:
    kit: str
    instances: int = 40
    seed: int = 0


@dataclass
class Problem:
    id: str
    kind: str
    statement: str
    context: str = ""
    expected: str | None = None
    checker: str | None = None  # Python source defining check(candidate)
    lean: LeanTarget | None = None
    implement: ImplementTarget | None = None
    families: list[str] = field(default_factory=list)
    papers: list[str] = field(default_factory=list)
    target: Tier | None = None
    optimize: bool = False  # keep improving the checker's score instead of stopping at the first pass
    program_seconds: float = 60.0
    source: Path | None = None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"problem {self.id!r}: kind must be one of {', '.join(KINDS)}, not {self.kind!r}")
        if self.target is None:
            # Differential testing can only ever show an implementation is
            # empirically right; every other kind can be checked outright.
            self.target = Tier.EMPIRICAL if self.kind == "implement" else Tier.VERIFIED
        if self.kind == "implement" and self.implement is None:
            raise ValueError(f"problem {self.id!r}: an implement problem needs an [implement] table naming a kit")
        if self.lean is not None and self.kind != "prove":
            raise ValueError(f"problem {self.id!r}: a [lean] target only applies to prove problems")
        if self.optimize and not self.checker:
            raise ValueError(f"problem {self.id!r}: optimize needs a checker that returns a score")

    @property
    def checks(self) -> list[str]:
        """The trusted checks this problem can run, strongest first."""

        names = []
        if self.lean:
            names.append("lean")
        if self.checker:
            names.append("checker")
        if self.expected is not None:
            names.append("expected")
        if self.implement:
            names.append("kit")
        return names

    @classmethod
    def load(cls, path: str | Path) -> "Problem":
        path = Path(path)
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        checker = data.get("checker")
        if isinstance(checker, dict):
            # A shared checker file, or inline Python; `settings` lines run after
            # it, so one checker can serve several problems.
            if "file" in checker:
                source = (path.parent / checker["file"]).read_text(encoding="utf-8")
            else:
                source = checker.get("python", "")
            if checker.get("settings"):
                source += "\n\n# Problem settings\n" + checker["settings"].strip() + "\n"
            checker = source or None
        lean = None
        if "lean" in data:
            table = data["lean"]
            lean = LeanTarget(
                statement=table["statement"].strip(),
                theorem=table["theorem"],
                imports=tuple(table.get("imports", ["Mathlib"])),
                project=str((path.parent / table["project"]).resolve()) if table.get("project") else None,
                permitted_axioms=tuple(table.get("permitted_axioms", DEFAULT_AXIOMS)),
            )
        implement = None
        if "implement" in data:
            table = data["implement"]
            implement = ImplementTarget(
                kit=table["kit"], instances=int(table.get("instances", 40)), seed=int(table.get("seed", 0))
            )
        expected = data.get("expected")
        return cls(
            id=data.get("id", path.stem),
            kind=data["kind"],
            statement=data["statement"].strip(),
            context=data.get("context", "").strip(),
            expected=None if expected is None else str(expected),
            checker=checker,
            lean=lean,
            implement=implement,
            families=[f"{int(f):03d}" if str(f).isdigit() else str(f) for f in data.get("families", [])],
            papers=[str(p) for p in data.get("papers", [])],
            target=Tier.parse(data["target"]) if "target" in data else None,
            optimize=bool(data.get("optimize", False)),
            program_seconds=float(data.get("program_seconds", 60.0)),
            source=path,
        )
