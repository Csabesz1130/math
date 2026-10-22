"""BM25 retrieval over result families, used to ground prompts in prior results."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .catalog import Catalog, Family

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an and are as at be by every for from in is it its of on or that the this to with we which "
    "our prove proves proved show shows give gives result results paper there their each all any".split()
)


def tokenize(text: str) -> list[str]:
    tokens = []
    for token in _TOKEN_RE.findall(text.lower()):
        if token in _STOP or len(token) < 2:
            continue
        tokens.append(_stem(token))
    return tokens


def _stem(token: str) -> str:
    for suffix in ("ings", "ing", "ies", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return token


@dataclass(frozen=True)
class Hit:
    family: Family
    score: float


class Index:
    def __init__(self, catalog: Catalog, k1: float = 1.4, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.families = list(catalog)
        # text() already holds the title and summary once; adding them again
        # weights them above the manuscript abstracts.
        self.docs = [
            Counter(tokenize(f"{f.title} {f.title} {f.summary}")) + Counter(tokenize(f.text()))
            for f in self.families
        ]
        self.lengths = [sum(doc.values()) for doc in self.docs]
        self.avg = sum(self.lengths) / max(1, len(self.lengths))
        df: Counter[str] = Counter()
        for doc in self.docs:
            df.update(doc.keys())
        n = len(self.docs)
        self.idf = {term: math.log(1 + (n - count + 0.5) / (count + 0.5)) for term, count in df.items()}

    def search(self, query: str, limit: int = 5, relative: float = 0.0) -> list[Hit]:
        """Top hits; ``relative`` drops hits scoring below that fraction of the best."""

        terms = tokenize(query)
        scored: list[Hit] = []
        for family, doc, length in zip(self.families, self.docs, self.lengths):
            score = 0.0
            for term in terms:
                tf = doc.get(term)
                if not tf:
                    continue
                norm = tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * length / self.avg))
                score += self.idf.get(term, 0.0) * norm
            if score > 0:
                scored.append(Hit(family, score))
        scored.sort(key=lambda hit: (-hit.score, hit.family.number))
        if scored and relative > 0:
            scored = [hit for hit in scored if hit.score >= relative * scored[0].score]
        return scored[:limit]
