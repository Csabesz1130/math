"""Max-Cut with a per-instance optimality certificate.

Max-Cut appears in VLSI via minimisation, ground states of Ising spin glasses,
graph partitioning and clustering, and as the standard QUBO benchmark against
which quantum and annealing hardware is compared.

Family 102 proves the Unique Games Conjecture and, directly, that
approximating Max-Cut beyond the Goemans–Williamson constant (about 0.87856)
is NP-hard. So no polynomial-time method can promise more on every instance;
what an engineer can have instead is a certificate for the instance at hand.

This app computes a cut (SDP relaxation by the low-rank mixing method,
random-hyperplane rounding, then 1-flip local search) and an upper bound from
a dual-feasible point of the SDP, built with an explicit floating-point error
margin. The ratio cut / bound is then a guarantee for this instance.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from ..catalog import Catalog
from ..evidence import Claim, Conclusion
from .base import AppResult, computed, family_claim, literature_claim

ALPHA_GW = 0.8785672057848516
MAX_NODES = 4000
EXACT_MAX_NODES = 22


def _np():
    try:
        import numpy as np
    except ImportError as error:
        raise RuntimeError("the maxcut app needs numpy: pip install numpy") from error
    return np


def read_weighted_edges(path: str | Path) -> tuple[list[str], list[tuple[int, int, float]]]:
    """Lines 'u v [w]' (weight defaults to 1); '#' starts a comment; parallel edges are summed."""

    index: dict[str, int] = {}
    labels: list[str] = []
    weights: dict[tuple[int, int], float] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        parts = line.split("#", 1)[0].replace(",", " ").split()
        if len(parts) < 2:
            continue
        ends = []
        for label in parts[:2]:
            if label not in index:
                index[label] = len(labels)
                labels.append(label)
            ends.append(index[label])
        u, v = ends
        if u == v:
            continue
        key = (min(u, v), max(u, v))
        weights[key] = weights.get(key, 0.0) + (float(parts[2]) if len(parts) > 2 else 1.0)
    return labels, [(u, v, w) for (u, v), w in sorted(weights.items())]


def demo_graph(seed: int = 3, n: int = 200, p: float = 0.06) -> tuple[list[str], list[tuple[int, int, float]]]:
    rng = random.Random(seed)
    edges = [(u, v, float(rng.randint(1, 10))) for u in range(n) for v in range(u + 1, n) if rng.random() < p]
    return [str(i) for i in range(n)], edges


def cut_value(edges: list[tuple[int, int, float]], side: list[int]) -> float:
    return math.fsum(w for u, v, w in edges if side[u] != side[v])


def _adjacency(n: int, edges):
    np = _np()
    neighbours = [[] for _ in range(n)]
    weights = [[] for _ in range(n)]
    for u, v, w in edges:
        neighbours[u].append(v)
        weights[u].append(w)
        neighbours[v].append(u)
        weights[v].append(w)
    return [np.array(a, dtype=np.int64) for a in neighbours], [np.array(a, dtype=float) for a in weights]


def mixing_method(n: int, edges, rank: int, sweeps: int, rng) -> "object":
    """Block-coordinate ascent on unit vectors for max sum w_ij (1 - v_i . v_j) / 2."""

    np = _np()
    neighbours, weights = _adjacency(n, edges)
    v = rng.standard_normal((n, rank))
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    for _ in range(sweeps):
        moved = 0.0
        for i in range(n):
            if len(neighbours[i]) == 0:
                continue
            g = weights[i] @ v[neighbours[i]]
            norm = np.linalg.norm(g)
            if norm < 1e-15:
                continue
            new = -g / norm
            moved += float(np.sum((new - v[i]) ** 2))
            v[i] = new
        if moved < 1e-10 * n:
            break
    return v


def dual_bound(n: int, edges, v) -> tuple[float, dict]:
    """A certified upper bound on the maximum cut.

    For L the weighted Laplacian, max cut <= max {<L, X>/4 : X psd, diag X = 1}
    <= sum(y) for any y with Diag(y) - L/4 psd (weak duality). Take y from the
    first-order conditions at v, compute the least eigenvalue of
    Diag(y) - L/4, and shift y by enough to cover it plus a backward-error
    margin for the floating-point eigensolver.
    """

    np = _np()
    lap = np.zeros((n, n))
    for a, b, w in edges:
        lap[a, b] -= w
        lap[b, a] -= w
        lap[a, a] += w
        lap[b, b] += w
    y = 0.25 * np.einsum("ij,ij->i", lap @ v, v)
    a = np.diag(y) - 0.25 * lap
    least = float(np.linalg.eigvalsh(a)[0])
    margin = 64 * n * float(np.finfo(float).eps) * float(np.linalg.norm(a))
    shift = max(0.0, margin - least)
    bound = math.fsum(y.tolist()) + n * shift
    bound += 1e-12 * max(1.0, abs(bound))
    return bound, {"least_eigenvalue": least, "eigen_margin": margin, "shift": shift}


def round_and_improve(n: int, edges, v, roundings: int, rng) -> list[int]:
    np = _np()
    us = np.array([e[0] for e in edges], dtype=np.int64)
    vs = np.array([e[1] for e in edges], dtype=np.int64)
    ws = np.array([e[2] for e in edges], dtype=float)
    signs = np.sign(v @ rng.standard_normal((v.shape[1], roundings)))
    signs[signs == 0] = 1
    values = ws @ (signs[us] != signs[vs])
    x = signs[:, int(np.argmax(values))].astype(float)
    # 1-flip local search: flipping i changes the cut by x_i * sum_j w_ij x_j.
    neighbours, weights = _adjacency(n, edges)
    field = np.array([weights[i] @ x[neighbours[i]] if len(neighbours[i]) else 0.0 for i in range(n)])
    while True:
        gains = x * field
        i = int(np.argmax(gains))
        if gains[i] <= 1e-12:
            break
        field[neighbours[i]] -= 2 * weights[i] * x[i]
        x[i] = -x[i]
    return [1 if value > 0 else 0 for value in x]


def exact_max_cut(n: int, edges) -> float:
    """Enumerate all 2^(n-1) cuts (vertex n-1 fixed on side 0) in vectorised blocks."""

    np = _np()
    us = np.array([e[0] for e in edges], dtype=np.int64)
    vs = np.array([e[1] for e in edges], dtype=np.int64)
    ws = np.array([e[2] for e in edges], dtype=float)
    best = -math.inf
    total = 1 << (n - 1)
    block = 1 << 15
    for start in range(0, total, block):
        masks = np.arange(start, min(total, start + block), dtype=np.int64)
        bits = (masks[:, None] >> np.arange(n, dtype=np.int64)[None, :]) & 1
        values = (bits[:, us] != bits[:, vs]) @ ws
        best = max(best, float(values.max()))
    return best


def run(
    labels: list[str],
    edges: list[tuple[int, int, float]],
    *,
    seed: int = 0,
    roundings: int = 400,
    sweeps: int = 300,
    exact: bool = True,
    catalog: Catalog | None = None,
) -> AppResult:
    np = _np()
    n = len(labels)
    if n < 2 or not edges:
        raise ValueError("the graph needs at least two vertices and one edge")
    if n > MAX_NODES:
        raise ValueError(f"{n} vertices exceeds the dense certificate limit of {MAX_NODES}")
    rng = np.random.default_rng(seed)
    rank = min(n, int(math.ceil(math.sqrt(2 * n))) + 1)
    v = mixing_method(n, edges, rank, sweeps, rng)
    side = round_and_improve(n, edges, v, roundings, rng)
    value = cut_value(edges, side)
    bound, certificate = dual_bound(n, edges, v)
    positive = all(w >= 0 for _, _, w in edges)

    claims: list[Claim] = []
    cut_claim = computed(f"The cut has weight {value:g}", "maxcut.cut_value (exact summation over edges)")
    bound_claim = computed(
        f"No cut of this graph weighs more than {bound:.6g} (SDP dual certificate)",
        "maxcut.dual_bound", certificate,
        ["least eigenvalue from LAPACK with an explicit backward-error margin"],
    )
    claims += [cut_claim, bound_claim]
    conclusions: list[Conclusion] = []
    optimum = None
    if exact and n <= EXACT_MAX_NODES:
        optimum = exact_max_cut(n, edges)
        exact_claim = computed(f"The maximum cut weighs exactly {optimum:g} (exhaustive enumeration)", "maxcut.exact_max_cut")
        claims.append(exact_claim)
        status = "optimal" if value >= optimum - 1e-9 else f"{value / optimum:.4%} of optimal"
        conclusions.append(Conclusion(f"This cut is {status}", [cut_claim, exact_claim]))
    ratio = value / bound if positive and bound > 0 else None
    if ratio is not None:
        conclusions.append(Conclusion(f"This cut is within {1 - ratio:.2%} of the maximum (at least {ratio:.4f} of optimal)", [cut_claim, bound_claim]))
    else:
        conclusions.append(Conclusion(f"The maximum cut lies between {value:g} and {bound:.6g}", [cut_claim, bound_claim]))
    hardness = family_claim(
        catalog, "102", f"Approximating Max-Cut within any fixed factor above {ALPHA_GW:.5f} is NP-hard, even on unweighted graphs",
        challenges=["OptimalMaxCut"],
    )
    claims.append(hardness)
    claims.append(literature_claim(
        f"Random-hyperplane rounding of an optimal SDP solution cuts at least {ALPHA_GW:.5f} of the SDP value in expectation (nonnegative weights)",
        "Goemans and Williamson, J. ACM 42 (1995)",
        ["this run's SDP solution is approximate; the per-instance certificate above is what is verified"],
    ))
    conclusions.append(Conclusion(
        "No polynomial-time method can promise a better worst-case ratio than Goemans–Williamson unless P = NP; "
        "per-instance certificates like this one are how to know a cut is near-optimal", [hardness],
    ))
    outputs = {
        "nodes": n,
        "edges": len(edges),
        "cut_weight": value,
        "upper_bound": bound,
        "certified_ratio": ratio,
        "exact_optimum": optimum,
        "side": {labels[i]: side[i] for i in range(n)},
        "sdp": {"rank": rank, **certificate},
    }
    headline = [f"{n} nodes, {len(edges)} edges: cut weight {value:g}, certified upper bound {bound:.6g}"]
    if ratio is not None:
        headline.append(f"Certified: this cut is at least {ratio:.2%} of the maximum")
    if optimum is not None:
        headline.append(f"Exact maximum by enumeration: {optimum:g}")
    return AppResult("maxcut", "Max-Cut with an optimality certificate", headline, outputs, claims, conclusions)
