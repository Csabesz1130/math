"""Structured index of the manuscript collection and its Lean formalizations.

Sources, all read-only:

- ``CONTENTS.md``: families (``**NNN. Title.** summary``) and their manuscripts.
- ``overview.tex``: the subject each family is filed under.
- ``lean/docs/NNN.md``: the Comparator challenges a family's formalization exposes.
- ``lean/ComparatorChallenges/*.json``: the theorem names and permitted axioms.
- ``lean/formalization.yaml``: the declaration and file proving each challenge,
  and the catalogue's review status.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

from .evidence import Source, Tier
from .repo import find_repo

_FAMILY_RE = re.compile(r"^\*\*(\d{3})\. (.+?)\*\*\s*(.*)$", re.S)
_MANUSCRIPT_RE = re.compile(r"^&emsp;\[(.+?)\]\((preprints/[^)]+)\)\s*(.*)$", re.S)
_LEAN_LINK_RE = re.compile(r"\(\[Lean\]\((lean/docs/\d{3}\.md)\)\)")
_CHALLENGE_LINK_RE = re.compile(r"\]\(\.\./ComparatorChallenges/([A-Za-z0-9_]+)\.lean\)")
_SUBJECT_RE = re.compile(r"^\\cataloguesection\{([^}]*)\}\{\d+\}")
_ENTRY_RE = re.compile(r"^\\resultentry\{(\d{3})\}")
_CELL_RE = re.compile(r"<td>\s*(.*?)\s*</td>", re.S)


@dataclass(frozen=True)
class ComparatorChallenge:
    """One Comparator configuration: a Lean statement and the theorem proving it."""

    name: str
    config: str  # path relative to lean/
    challenge_module: str
    solution_module: str
    theorem_names: tuple[str, ...]
    permitted_axioms: tuple[str, ...]
    declaration: str | None = None
    file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "config": self.config,
            "challenge_module": self.challenge_module,
            "solution_module": self.solution_module,
            "theorem_names": list(self.theorem_names),
            "permitted_axioms": list(self.permitted_axioms),
            "declaration": self.declaration,
            "file": self.file,
        }


@dataclass(frozen=True)
class Manuscript:
    title: str
    path: str  # PDF path relative to the repository root
    abstract: str

    @property
    def directory(self) -> str:
        return str(Path(self.path).parent)

    def to_dict(self) -> dict[str, Any]:
        return {"title": plain(self.title), "path": self.path, "abstract": plain(self.abstract)}


@dataclass
class Family:
    """A result family: a principal result with its companion manuscripts."""

    id: str
    title: str
    summary: str
    subject: str = "Unclassified"
    manuscripts: list[Manuscript] = field(default_factory=list)
    lean_doc: str | None = None
    challenges: list[ComparatorChallenge] = field(default_factory=list)

    @property
    def number(self) -> int:
        return int(self.id)

    @property
    def formal_tier(self) -> Tier:
        """The strongest tier this repository offers for the family's results."""

        return Tier.FORMALIZED if self.challenges else Tier.PUBLISHED

    def source(self) -> Source:
        detail = plain(self.title)
        if self.challenges:
            detail += " (Comparator: " + ", ".join(c.name for c in self.challenges) + ")"
        return Source("family", self.id, detail)

    def text(self) -> str:
        parts = [self.title, self.summary]
        for manuscript in self.manuscripts:
            parts.extend([manuscript.title, manuscript.abstract])
        return plain(" ".join(parts))

    def to_dict(self, *, abstracts: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "title": plain(self.title),
            "subject": self.subject,
            "summary": plain(self.summary),
            "formal_tier": self.formal_tier.label,
            "lean_doc": self.lean_doc,
            "challenges": [c.to_dict() for c in self.challenges],
        }
        if abstracts:
            out["manuscripts"] = [m.to_dict() for m in self.manuscripts]
        else:
            out["manuscripts"] = [{"title": plain(m.title), "path": m.path} for m in self.manuscripts]
        return out


class Catalog:
    """All families of the collection, keyed by their three-digit id."""

    def __init__(self, root: Path, families: list[Family], review_status: str | None):
        self.root = root
        self.families = {family.id: family for family in families}
        self.review_status = review_status

    @classmethod
    def load(cls, root: str | Path | None = None) -> "Catalog":
        root = find_repo(root)
        families = _parse_contents(root / "CONTENTS.md")
        subjects = _parse_subjects(root / "overview.tex")
        declarations, review_status = _parse_formalization(root / "lean" / "formalization.yaml")
        for family in families:
            family.subject = subjects.get(family.id, "Unclassified")
            if family.lean_doc:
                family.challenges = _parse_challenges(root, family.lean_doc, declarations)
        return cls(root, families, review_status)

    def __len__(self) -> int:
        return len(self.families)

    def __iter__(self):
        return iter(sorted(self.families.values(), key=lambda f: f.number))

    def get(self, family_id: str | int) -> Family:
        key = f"{int(family_id):03d}" if str(family_id).isdigit() else str(family_id)
        try:
            return self.families[key]
        except KeyError as error:
            raise KeyError(f"no result family {family_id!r} in the catalogue") from error

    @cached_property
    def manuscript_count(self) -> int:
        return sum(len(f.manuscripts) for f in self.families.values())

    def subjects(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for family in self.families.values():
            counts[family.subject] = counts.get(family.subject, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    def paper_sources(self, manuscript: Manuscript) -> list[Path]:
        """The LaTeX sources of a manuscript, main file first, excluding the TeX runtime."""

        build = self.root / manuscript.directory / "build"
        if not build.is_dir():
            return []
        files = [
            p for p in sorted(build.rglob("*.tex"))
            if "runtime" not in p.relative_to(build).parts and "sources" not in p.relative_to(build).parts
        ]
        main = [p for p in files if "\\documentclass" in p.read_text(errors="replace")[:4000]]
        rest = [p for p in files if p not in main]
        return main + rest


def plain(text: str) -> str:
    """Strip the Markdown/HTML/LaTeX decoration used in CONTENTS.md."""

    text = re.sub(r"<sup>(.*?)</sup>", r"^\1", text)
    text = re.sub(r"<sub>(.*?)</sub>", r"_\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("$`", "").replace("`$", "")
    text = re.sub(r"\(\[Lean\]\([^)]*\)\)", "", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_contents(path: Path) -> list[Family]:
    text = path.read_text(encoding="utf-8")
    families: list[Family] = []
    current: Family | None = None
    for cell in _CELL_RE.findall(text):
        family = _FAMILY_RE.match(cell)
        if family:
            number, title, summary = family.groups()
            lean = _LEAN_LINK_RE.search(summary)
            current = Family(
                id=number,
                title=title.rstrip(". "),
                summary=_LEAN_LINK_RE.sub("", summary).strip(),
                lean_doc=lean.group(1) if lean else None,
            )
            families.append(current)
            continue
        manuscript = _MANUSCRIPT_RE.match(cell)
        if manuscript and current is not None:
            title, link, abstract = manuscript.groups()
            current.manuscripts.append(Manuscript(title.strip(), link.strip(), abstract.strip()))
    return families


def _parse_subjects(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    subjects: dict[str, str] = {}
    subject = "Unclassified"
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = _SUBJECT_RE.match(line)
        if heading:
            subject = heading.group(1)
            continue
        entry = _ENTRY_RE.match(line)
        if entry:
            subjects[entry.group(1)] = subject
    return subjects


def _parse_formalization(path: Path) -> tuple[dict[str, tuple[str, str]], str | None]:
    """Map Comparator config paths to (declaration, file), and read the review status.

    The file is a flat, regular YAML document; a line scanner keeps the harness
    free of third-party dependencies.
    """

    declarations: dict[str, tuple[str, str]] = {}
    review_status: str | None = None
    if not path.is_file():
        return declarations, review_status
    config = declaration = None
    in_review = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if raw.startswith("review:"):
            in_review = True
            continue
        if in_review and line.startswith("status:"):
            review_status = line.split(":", 1)[1].strip().strip("\"'")
            in_review = False
            continue
        if line.startswith("- comparator_config:"):
            config = line.split(":", 1)[1].strip()
            declaration = None
        elif line.startswith("declaration:") and config:
            declaration = line.split(":", 1)[1].strip()
        elif line.startswith("file:") and config and declaration:
            declarations[config] = (declaration, line.split(":", 1)[1].strip())
            config = declaration = None
    return declarations, review_status


def _parse_challenges(
    root: Path, lean_doc: str, declarations: dict[str, tuple[str, str]]
) -> list[ComparatorChallenge]:
    doc = root / lean_doc
    if not doc.is_file():
        return []
    challenges: list[ComparatorChallenge] = []
    seen: set[str] = set()
    for name in _CHALLENGE_LINK_RE.findall(doc.read_text(encoding="utf-8")):
        if name in seen:
            continue
        seen.add(name)
        config = f"ComparatorChallenges/{name}.json"
        config_path = root / "lean" / config
        if not config_path.is_file():
            continue
        data = json.loads(config_path.read_text(encoding="utf-8"))
        declaration, file = declarations.get(config, (None, None))
        challenges.append(
            ComparatorChallenge(
                name=name,
                config=config,
                challenge_module=data.get("challenge_module", ""),
                solution_module=data.get("solution_module", ""),
                theorem_names=tuple(data.get("theorem_names", [])),
                permitted_axioms=tuple(data.get("permitted_axioms", [])),
                declaration=declaration,
                file=file,
            )
        )
    return challenges
