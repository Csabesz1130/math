"""Kit for family 128: a polynomial-time 2-approximation for shortest common superstring.

Family 128 constructs a deterministic algorithm whose output is at most twice
the optimum on every input; the paper stresses that the guarantee is for its
own algorithm, not for the classical maximum-overlap greedy merge. This kit
checks a transcription against the exact optimum on small families.

Industrial reading: genome and read assembly, and dictionary compression, build
short superstrings; a guaranteed factor bounds the worst case that greedy
assembly heuristics leave open.
"""

from __future__ import annotations

import random

NAME = "superstring"
FAMILY = "128"
ENTRYPOINT = "superstring"
INTERFACE = """
def superstring(instance: dict) -> str

instance = {"strings": ["...", ...]}
    Non-empty strings over a small alphabet. The family may contain duplicates and strings that are
    substrings of others.

Return a string that contains every input string as a contiguous substring and whose length is at
most twice the length of a shortest such string.
"""


def instances(seed: int, count: int) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for index in range(count):
        alphabet = ("ab", "abc", "acgt")[index % 3]
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(8, 22)))
        strings = []
        for _ in range(rng.randint(2, 8)):
            length = rng.randint(2, 8)
            start = rng.randrange(0, max(1, len(text) - length + 1))
            strings.append(text[start : start + length])
        if index % 5 == 4:  # some families with no shared hidden text
            strings = ["".join(rng.choice(alphabet) for _ in range(rng.randint(2, 6))) for _ in range(rng.randint(2, 6))]
        out.append({"strings": strings})
    return out


def _reduce(strings: list[str]) -> list[str]:
    unique = sorted(set(strings), key=lambda s: (-len(s), s))
    kept: list[str] = []
    for s in unique:
        if not any(s in other for other in kept):
            kept.append(s)
    return kept


def _overlap(a: str, b: str) -> int:
    for k in range(min(len(a), len(b)) - 1, 0, -1):
        if a.endswith(b[:k]):
            return k
    return 0


def oracle(instance: dict) -> int:
    """Exact shortest-superstring length (Held–Karp over the substring-free reduction)."""

    strings = _reduce(instance["strings"])
    n = len(strings)
    if n == 0:
        return 0
    overlap = [[_overlap(a, b) if i != j else 0 for j, b in enumerate(strings)] for i, a in enumerate(strings)]
    # best[mask][last]: maximum total overlap of an ordering of mask ending at last.
    best = [[-1] * n for _ in range(1 << n)]
    for i in range(n):
        best[1 << i][i] = 0
    for mask in range(1 << n):
        for last in range(n):
            value = best[mask][last]
            if value < 0:
                continue
            for nxt in range(n):
                if mask >> nxt & 1:
                    continue
                candidate = value + overlap[last][nxt]
                target = mask | 1 << nxt
                if candidate > best[target][nxt]:
                    best[target][nxt] = candidate
    return sum(map(len, strings)) - max(best[(1 << n) - 1])


def check(instance: dict, output, reference: int) -> tuple[bool, str]:
    if not isinstance(output, str):
        return False, f"expected a string, got {type(output).__name__}"
    missing = [s for s in instance["strings"] if s not in output]
    if missing:
        return False, f"{missing[0]!r} is not a substring of the output"
    if len(output) > 2 * reference:
        return False, f"length {len(output)} exceeds twice the optimum {reference}"
    return True, f"length {len(output)} (optimum {reference})"


def baseline(instance: dict) -> str:
    """Classical greedy: repeatedly merge the pair with the largest overlap."""

    strings = _reduce(instance["strings"])
    while len(strings) > 1:
        k, i, j = max(
            (_overlap(a, b), i, j) for i, a in enumerate(strings) for j, b in enumerate(strings) if i != j
        )
        merged = strings[i] + strings[j][k:]
        strings = [s for index, s in enumerate(strings) if index not in (i, j)] + [merged]
        strings = _reduce(strings)
    return strings[0] if strings else ""
