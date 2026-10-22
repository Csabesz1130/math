"""Binary pulse-compression and synchronisation codes with low autocorrelation sidelobes.

Radar and sonar pulse compression, frame synchronisation words and
spread-spectrum preambles want a ±1 sequence whose aperiodic autocorrelation
sidelobes are small: a low peak sidelobe level (PSL) or a high merit factor.

Two result families bear on this directly:

- 179 proves the circulant Hadamard conjecture; with the classical odd-length
  results this settles that sequences with every sidelobe at most 1 (Barker
  sequences) exist only at lengths 2, 3, 4, 5, 7, 11 and 13. Beyond 13 the
  best achievable PSL is at least 2, so searching for a longer Barker code is
  futile.
- 076 shows the largest merit factor at length N tends to infinity, disproving
  Turyn's bounded-merit-factor conjecture. It is asymptotic and gives no rate,
  so it removes a believed ceiling rather than supplying a code.

The app searches for a code, computes its sidelobes exactly, and where an
exhaustive search fits the time budget it proves the PSL lower bound itself.
"""

from __future__ import annotations

import random
import time
from typing import Sequence

from ..catalog import Catalog
from ..evidence import Claim, Conclusion, Source, Tier
from .base import AppResult, computed, family_claim, literature_claim

BARKER = {
    2: (1, -1),
    3: (1, 1, -1),
    4: (1, 1, -1, 1),
    5: (1, 1, 1, -1, 1),
    7: (1, 1, 1, -1, -1, 1, -1),
    11: (1, 1, 1, -1, -1, -1, 1, -1, -1, 1, -1),
    13: (1, 1, 1, 1, 1, -1, -1, 1, 1, -1, 1, -1, 1),
}


def autocorrelations(seq: Sequence[int]) -> list[int]:
    """Aperiodic autocorrelations C_1 .. C_{n-1}."""

    n = len(seq)
    return [sum(seq[j] * seq[j + k] for j in range(n - k)) for k in range(1, n)]


def psl(seq: Sequence[int]) -> int:
    return max((abs(c) for c in autocorrelations(seq)), default=0)


def isl(seq: Sequence[int]) -> int:
    return sum(c * c for c in autocorrelations(seq))


def merit_factor(seq: Sequence[int]) -> float:
    energy = isl(seq)
    return float("inf") if energy == 0 else len(seq) ** 2 / (2 * energy)


def isl_parity_bound(n: int) -> int:
    """C_k has the parity of n - k, so ISL is at least the number of odd n - k."""

    return sum((n - k) % 2 for k in range(1, n))


# -- exhaustive search ------------------------------------------------------------


def exhaustive_psl(n: int, bound: int, deadline: float | None = None) -> tuple[str, list[int] | None, int]:
    """Decide whether some ±1 sequence of length n has PSL <= bound.

    Positions are fixed from both ends inward. Every correlation term between
    fixed positions is accumulated incrementally, and a branch is cut as soon
    as some |C_k| must exceed the bound however the free positions are set.
    Negation and alternation (s_j -> (-1)^j s_j) preserve every |C_k|, so s_0
    and s_1 are fixed to +1. Returns ("found", sequence, nodes),
    ("none", None, nodes) or ("timeout", None, nodes).
    """

    if n <= 2:
        return "found", [1] * n, 1
    s = [0] * n
    part = [0] * n  # part[k]: sum of known terms of C_k
    known = [0] * n  # known[k]: number of known terms of C_k
    nodes = 0
    left: list[int] = []
    right: list[int] = []

    def place(positions: tuple[int, ...]) -> list[tuple[int, int]] | None:
        """Add the terms that the newly fixed positions complete; None on prune."""

        changes: list[tuple[int, int]] = []
        fixed = left + right  # positions fixed before this step
        for p in positions:
            for q in fixed:
                k = abs(p - q)
                term = s[p] * s[q]
                part[k] += term
                known[k] += 1
                changes.append((k, term))
        if len(positions) == 2:
            a, b = positions
            k = b - a
            term = s[a] * s[b]
            part[k] += term
            known[k] += 1
            changes.append((k, term))
        for k, _ in changes:
            if abs(part[k]) - (n - k - known[k]) > bound:
                undo(changes)
                return None
        return changes

    def undo(changes: list[tuple[int, int]]) -> None:
        for k, term in changes:
            part[k] -= term
            known[k] -= 1

    class Timeout(Exception):
        pass

    def descend(depth: int) -> bool:
        nonlocal nodes
        nodes += 1
        if deadline is not None and nodes % 4096 == 0 and time.monotonic() > deadline:
            raise Timeout
        a, b = depth, n - 1 - depth
        if a > b:
            return True
        positions = (a,) if a == b else (a, b)
        choices_a = (1,) if a in (0, 1) else (1, -1)
        for va in choices_a:
            for vb in ((None,) if a == b else (1, -1)):
                s[a] = va
                if vb is not None:
                    s[b] = vb
                changes = place(positions)
                if changes is None:
                    continue
                left.append(a)
                if a != b:
                    right.append(b)
                if descend(depth + 1):
                    return True
                left.pop()
                if a != b:
                    right.pop()
                undo(changes)
        s[a] = 0
        if a != b:
            s[b] = 0
        return False

    try:
        found = descend(0)
    except Timeout:
        return "timeout", None, nodes
    return ("found", list(s), nodes) if found else ("none", None, nodes)


# -- heuristic search ---------------------------------------------------------------


def tabu_search(n: int, seconds: float, seed: int = 0, power: int = 4) -> list[int]:
    """Tabu search on sum |C_k|^power (power 2 targets merit factor, 4 targets PSL).

    Returns the best sequence seen, ranked by (PSL, ISL) for power > 2 and by
    ISL otherwise.
    """

    rng = random.Random(seed)
    deadline = time.monotonic() + seconds
    flips = _flip_energies(n, power)

    def key(c: list[int]) -> tuple[int, int]:
        isl_value = sum(x * x for x in c)
        return (max(abs(x) for x in c), isl_value) if power > 2 else (isl_value, max(abs(x) for x in c))

    best_seq = [rng.choice((1, -1)) for _ in range(n)]
    best_key = key(autocorrelations(best_seq))
    while time.monotonic() < deadline:
        s = [rng.choice((1, -1)) for _ in range(n)] if rng.random() < 0.5 else _perturb(best_seq, rng)
        c = [0] + autocorrelations(s)
        energy = sum(abs(x) ** power for x in c[1:])
        run_best = energy
        tabu = [0] * n
        step = stall = 0
        while stall < 8 * n and time.monotonic() < deadline:
            step += 1
            choice, choice_energy = -1, None
            for i, e in enumerate(flips(s, c)):
                if tabu[i] > step and e >= run_best:
                    continue
                if choice_energy is None or e < choice_energy:
                    choice, choice_energy = i, e
            if choice < 0:
                break
            _apply_flip(s, c, choice)
            energy = choice_energy
            tabu[choice] = step + rng.randint(max(1, n // 10), max(2, n // 4))
            k = key(c[1:])
            if k < best_key:
                best_key, best_seq = k, list(s)
            if energy < run_best:
                run_best, stall = energy, 0
            else:
                stall += 1
    return best_seq


def _perturb(seq: list[int], rng: random.Random) -> list[int]:
    out = list(seq)
    for i in rng.sample(range(len(out)), k=max(1, len(out) // 8)):
        out[i] = -out[i]
    return out


def _flip_energies(n: int, power: int):
    """Return f(s, c) giving, for every i, the energy after flipping s[i].

    Flipping s_i changes C_k by -2 s_i (s_{i+k} + s_{i-k}). With numpy all n
    flips are evaluated as one n x n array operation; without it, in Python.
    """

    try:
        import numpy as np
    except ImportError:
        np = None
    if np is None:
        def python(s: list[int], c: list[int]) -> list[int]:
            out = []
            for i in range(n):
                si2 = 2 * s[i]
                total = 0
                for k in range(1, n):
                    v = c[k] - si2 * ((s[i + k] if i + k < n else 0) + (s[i - k] if i >= k else 0))
                    total += (v * v) ** (power // 2)
                out.append(total)
            return out

        return python
    i = np.arange(n)[:, None]
    k = np.arange(1, n)[None, :]
    plus, minus = n + i + k, n + i - k  # indices into s padded by n zeros on each side

    def vectorised(s: list[int], c: list[int]) -> list[int]:
        padded = np.zeros(3 * n, dtype=np.int64)
        padded[n : 2 * n] = s
        sv = padded[n : 2 * n, None]
        new = np.asarray(c[1:], dtype=np.int64)[None, :] - 2 * sv * (padded[plus] + padded[minus])
        return ((new * new) ** (power // 2)).sum(axis=1).tolist()

    return vectorised


def _apply_flip(s: list[int], c: list[int], i: int) -> None:
    n = len(s)
    si2 = 2 * s[i]
    for k in range(1, n):
        a = (s[i + k] if i + k < n else 0) + (s[i - k] if i >= k else 0)
        c[k] -= si2 * a
    s[i] = -s[i]


# -- application --------------------------------------------------------------------


def run(
    length: int,
    *,
    objective: str = "psl",
    seconds: float = 10.0,
    exhaustive_seconds: float = 20.0,
    seed: int = 0,
    catalog: Catalog | None = None,
) -> AppResult:
    if length < 2:
        raise ValueError("code length must be at least 2")
    if objective not in ("psl", "merit"):
        raise ValueError("objective must be psl or merit")
    n = length
    claims: list[Claim] = []
    conclusions: list[Conclusion] = []
    search_notes: dict[str, object] = {}

    if n in BARKER:
        seq = list(BARKER[n])
        search_notes["method"] = "Barker sequence"
    else:
        seq = tabu_search(n, seconds, seed, power=4 if objective == "psl" else 2)
        search_notes["method"] = f"tabu search ({seconds:g}s, seed {seed})"

    deadline = time.monotonic() + exhaustive_seconds
    # The PSL-1 question: can a Barker code of this length exist?
    if n in BARKER:
        barker_claim = computed(f"A length-{n} Barker code (every sidelobe at most 1) exists: this one", "pulse-codes.autocorrelations")
    else:
        status, _, nodes = exhaustive_psl(n, 1, deadline)
        search_notes["psl1_exhaustive"] = {"status": status, "nodes": nodes}
        if status == "none":
            barker_claim = computed(
                f"No length-{n} binary sequence has every sidelobe at most 1 (exhaustive search)",
                "pulse-codes.exhaustive_psl", {"nodes": nodes},
            )
        elif status == "found":  # impossible by the theorem; surfaced rather than hidden
            raise AssertionError(f"exhaustive search found a length-{n} Barker sequence, contradicting family 179")
        elif n % 2 == 0:
            barker_claim = family_claim(
                catalog, "179", f"No length-{n} binary sequence has every sidelobe at most 1 (even Barker lengths are only 2 and 4)",
                challenges=["EvenBarker"],
            )
        else:
            barker_claim = literature_claim(
                f"No length-{n} binary sequence has every sidelobe at most 1 (odd Barker lengths stop at 13)",
                "Turyn and Storer, On binary sequences, Proc. AMS 12 (1961)",
                ["classical result, cited by family 179; not formalized in the collection"],
            )
    claims.append(barker_claim)

    # The proven lower bound on PSL at this length, and the claim it rests on.
    best_psl = psl(seq)
    if best_psl <= 1:
        lower_value = 1
        lower = computed(f"Every length-{n} sequence has PSL at least 1 (C_{n - 1} = s_0 s_{n - 1} = ±1)", "parity")
    else:
        lower_value = 2
        lower = Claim(f"Every length-{n} sequence has PSL at least 2", barker_claim.tier, barker_claim.sources, barker_claim.limitations)
        # Improve the code or raise the bound by exact search while the budget lasts.
        bound = best_psl - 1
        while objective == "psl" and bound >= lower_value and time.monotonic() < deadline:
            status, found, nodes = exhaustive_psl(n, bound, deadline)
            search_notes[f"psl{bound}_exhaustive"] = {"status": status, "nodes": nodes}
            if status == "found":
                seq, best_psl = found, psl(found)
                search_notes["method"] += f"; improved by exhaustive search to PSL {best_psl}"
                bound = best_psl - 1
                continue
            if status == "none":
                lower_value = bound + 1
                lower = computed(
                    f"Every length-{n} sequence has PSL at least {lower_value} (exhaustive search)",
                    "pulse-codes.exhaustive_psl", {"nodes": nodes},
                )
            break

    corr = autocorrelations(seq)
    profile = computed(
        f"The code has PSL {best_psl}, ISL {isl(seq)} and merit factor {merit_factor(seq):.3f}",
        "pulse-codes.autocorrelations", {"autocorrelations": corr},
    )
    claims += [profile, lower]
    if isl(seq) == isl_parity_bound(n):
        claims.append(computed(f"Its ISL {isl(seq)} equals the parity lower bound, so its merit factor is the largest possible at length {n}", "parity"))
    merit = family_claim(
        catalog, "076",
        "The largest merit factor at length N tends to infinity (Turyn's bounded-merit-factor conjecture is false)",
        challenges=["AsymptoticallyMinimalLittlewood"],
        limitations=["asymptotic: gives no construction or rate at this length"],
    )
    claims.append(merit)

    conclusions.append(Conclusion(f"This length-{n} code has PSL {best_psl} and merit factor {merit_factor(seq):.3f}", [profile]))
    if lower_value == best_psl:
        conclusions.append(Conclusion(f"No length-{n} code has a lower PSL: this code is PSL-optimal", [profile, lower]))
    else:
        gap = Claim(
            f"Whether a length-{n} code with PSL {lower_value}–{best_psl - 1} exists",
            Tier.UNKNOWN, [Source("check", "pulse-codes.exhaustive_psl", "not settled within the budget")],
            ["raise --exhaustive-seconds (or --seconds) to settle it"],
        )
        claims.append(gap)
        conclusions.append(Conclusion(f"This code may not be PSL-optimal: PSL {best_psl - 1} at length {n} is neither achieved nor excluded", [gap]))
    if n not in BARKER:
        conclusions.append(Conclusion(f"Searching for a length-{n} Barker code is futile", [barker_claim]))

    outputs = {
        "length": n,
        "objective": objective,
        "sequence": seq,
        "bits": "".join("1" if x > 0 else "0" for x in seq),
        "psl": best_psl,
        "isl": isl(seq),
        "merit_factor": round(merit_factor(seq), 6),
        "autocorrelations": corr,
        "search": search_notes,
    }
    headline = [
        f"Length {n}: PSL {best_psl}, ISL {isl(seq)}, merit factor {merit_factor(seq):.3f}",
        f"Code (+1 → 1): {outputs['bits']}",
    ]
    return AppResult("pulse-code", f"Low-sidelobe binary code, length {n}", headline, outputs, claims, conclusions)
