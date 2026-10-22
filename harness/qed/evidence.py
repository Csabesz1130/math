"""Evidence tiers for claims made by the harness and its applications.

Every statement the harness reports carries a tier saying how it is known.
Tiers are ordered from strongest to weakest. A conclusion that rests on
several claims is only as strong as its weakest support, and no step of the
harness may raise a tier on a model's say-so: only a check that ran can.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Iterable


class Tier(enum.IntEnum):
    """How a claim is known, strongest first (lower value is stronger)."""

    VERIFIED = 0
    """Checked in this run by a deterministic checker: exact computation,
    a trusted checker, or a Lean/Comparator run that passed."""

    FORMALIZED = 1
    """The repository ships a Lean statement and Comparator configuration for
    it. Not re-checked in this run, and the catalogue's own review status is
    'unchecked'."""

    PUBLISHED = 2
    """Stated in a manuscript of this collection, or in the classical
    literature, without a formalization available here."""

    EMPIRICAL = 3
    """Supported by measurements in this run (sampling, tests on generated
    instances, timing, convergence diagnostics). Not a proof."""

    ASSERTED = 4
    """Claimed by a language model and not independently checked."""

    UNKNOWN = 5
    """Not established."""

    @property
    def label(self) -> str:
        return self.name.lower()

    @classmethod
    def parse(cls, value: str | "Tier") -> "Tier":
        if isinstance(value, Tier):
            return value
        try:
            return cls[value.strip().upper()]
        except KeyError as error:
            names = ", ".join(t.label for t in cls)
            raise ValueError(f"unknown evidence tier {value!r}; expected one of {names}") from error


TIER_DESCRIPTIONS = {
    Tier.VERIFIED: "checked in this run by a deterministic checker",
    Tier.FORMALIZED: "Lean statement and Comparator config in this repository; not re-checked here",
    Tier.PUBLISHED: "stated in a manuscript or the classical literature; no formalization used",
    Tier.EMPIRICAL: "supported by measurements in this run; not a proof",
    Tier.ASSERTED: "claimed by a model; not independently checked",
    Tier.UNKNOWN: "not established",
}


@dataclass(frozen=True)
class Source:
    """Where a claim comes from: a check, a result family, a file or a model."""

    kind: str  # "check", "family", "comparator", "literature", "model", "measurement"
    ref: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        out = {"kind": self.kind, "ref": self.ref}
        if self.detail:
            out["detail"] = self.detail
        return out


@dataclass
class Claim:
    """One statement with the tier at which it is known."""

    statement: str
    tier: Tier
    sources: list[Source] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "statement": self.statement,
            "tier": self.tier.label,
            "sources": [s.to_dict() for s in self.sources],
        }
        if self.limitations:
            out["limitations"] = list(self.limitations)
        if self.data:
            out["data"] = self.data
        return out


@dataclass
class Conclusion:
    """A decision-relevant statement derived from supporting claims.

    Its tier is the weakest tier among its supports, so a conclusion never
    reads stronger than the evidence beneath it.
    """

    statement: str
    support: list[Claim]

    @property
    def tier(self) -> Tier:
        if not self.support:
            return Tier.UNKNOWN
        return max(claim.tier for claim in self.support)

    @property
    def weakest(self) -> list[Claim]:
        tier = self.tier
        return [claim for claim in self.support if claim.tier == tier]

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "tier": self.tier.label,
            "weakest_support": [c.statement for c in self.weakest],
            "support": [c.to_dict() for c in self.support],
        }


def weakest(tiers: Iterable[Tier]) -> Tier:
    tiers = list(tiers)
    return max(tiers) if tiers else Tier.UNKNOWN


def claims_markdown(claims: Iterable[Claim], conclusions: Iterable[Conclusion] = ()) -> str:
    """Render claims and conclusions as a Markdown evidence table."""

    lines: list[str] = []
    conclusions = list(conclusions)
    if conclusions:
        lines.append("### Conclusions\n")
        for conclusion in conclusions:
            lines.append(f"- **{conclusion.statement}** — `{conclusion.tier.label}`")
            for claim in conclusion.weakest:
                lines.append(f"  - weakest support: {claim.statement}")
        lines.append("")
    claims = list(claims)
    if claims:
        lines.append("### Evidence\n")
        lines.append("| Tier | Claim | Source | Limitations |")
        lines.append("| --- | --- | --- | --- |")
        for claim in claims:
            sources = "; ".join(f"{s.kind}: {s.ref}" for s in claim.sources) or "—"
            limits = "; ".join(claim.limitations) or "—"
            lines.append(
                f"| `{claim.tier.label}` | {_cell(claim.statement)} | {_cell(sources)} | {_cell(limits)} |"
            )
        lines.append("")
        lines.append("Tiers: " + "; ".join(f"`{t.label}` = {d}" for t, d in TIER_DESCRIPTIONS.items()) + ".")
    return "\n".join(lines) + "\n"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
