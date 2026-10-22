"""Shared structure for applications that put a result family to work."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..catalog import Catalog
from ..evidence import Claim, Conclusion, Source, Tier, claims_markdown


@dataclass
class AppResult:
    app: str
    title: str
    headline: list[str]
    outputs: dict[str, Any]
    claims: list[Claim]
    conclusions: list[Conclusion]
    files: dict[str, str] = field(default_factory=dict)

    @property
    def decision_tier(self) -> Tier:
        return max((c.tier for c in self.conclusions), default=Tier.UNKNOWN)

    def to_dict(self) -> dict[str, Any]:
        return {
            "app": self.app,
            "title": self.title,
            "headline": self.headline,
            "outputs": self.outputs,
            "conclusions": [c.to_dict() for c in self.conclusions],
            "claims": [c.to_dict() for c in self.claims],
            "files": sorted(self.files),
        }

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", ""]
        lines += [f"- {line}" for line in self.headline]
        lines += ["", claims_markdown(self.claims, self.conclusions)]
        lines += ["## Outputs", "", "```json", json.dumps(self.outputs, indent=2), "```", ""]
        return "\n".join(lines)


def family_claim(
    catalog: Catalog | None,
    family_id: str,
    statement: str,
    *,
    challenges: Iterable[str] = (),
    limitations: Iterable[str] = (),
) -> Claim:
    """A claim resting on a result family, at the tier the collection supports.

    It is ``formalized`` only when the named Comparator challenges exist in the
    repository; otherwise ``published``.
    """

    limitations = list(limitations)
    if catalog is None:
        return Claim(
            statement, Tier.PUBLISHED, [Source("family", family_id)],
            limitations + ["catalogue not loaded; formalization status unknown"],
        )
    family = catalog.get(family_id)
    wanted = set(challenges)
    chosen = [c for c in family.challenges if not wanted or c.name in wanted]
    if chosen:
        sources = [Source("comparator", f"lean/{c.config}", c.declaration or ", ".join(c.theorem_names)) for c in chosen]
        limitations.append(
            f"formalization review status: {catalog.review_status or 'unknown'}; not re-checked in this run "
            f"(`qed verify {family.id}` runs Comparator where Lean is installed)"
        )
        return Claim(statement, Tier.FORMALIZED, [family.source(), *sources], limitations)
    paths = [Source("family", family.id, family.manuscripts[0].path)] if family.manuscripts else [family.source()]
    return Claim(statement, Tier.PUBLISHED, paths, limitations + ["no Lean formalization of this statement in the collection"])


def literature_claim(statement: str, reference: str, limitations: Iterable[str] = ()) -> Claim:
    return Claim(statement, Tier.PUBLISHED, [Source("literature", reference)], list(limitations))


def computed(statement: str, check: str, data: dict[str, Any] | None = None, limitations: Iterable[str] = ()) -> Claim:
    return Claim(statement, Tier.VERIFIED, [Source("check", check)], list(limitations), data or {})
