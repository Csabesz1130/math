from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..evidence import Tier


@dataclass
class Verdict:
    """The outcome of one verifier on one candidate.

    ``tier`` is the tier the candidate's main claim reaches when this verifier
    passes. A ``hard`` verifier's failure rejects the candidate; a soft one
    (the model critic) only ranks it and feeds the next round.
    """

    verifier: str
    status: str  # pass | fail | skipped | error
    tier: Tier
    hard: bool
    message: str = ""
    limitations: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    @property
    def failed(self) -> bool:
        return self.status in ("fail", "error")

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "verifier": self.verifier,
            "status": self.status,
            "tier_if_pass": self.tier.label,
            "hard": self.hard,
            "message": self.message,
        }
        if self.limitations:
            out["limitations"] = self.limitations
        if self.data:
            out["data"] = self.data
        return out
