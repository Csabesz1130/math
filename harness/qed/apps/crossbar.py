"""Crossing-optimal layouts of complete bipartite interconnects.

When m sources must each be wired to n sinks in one routing layer (a crossbar
on a single-layer board, a full bus-to-bus mesh, a brickyard of rail tracks
between kilns and storage sites), every crossing costs a via, a jumper or a
bridge. Zarankiewicz's drawing (sources on one axis, sinks on the other,
straight edges) has

    Z(m, n) = floor(m/2) floor((m-1)/2) floor(n/2) floor((n-1)/2)

crossings. Family 165 proves no drawing of K_{m,n} with continuous edges does
better, so the layout is optimal and Z(m, n) is the exact jumper budget. It
also settles cr(K_n) (the Harary–Hill formula); there the optimal drawings are
not straight-line, so this app reports that number without a layout.

The app builds the drawing with integer coordinates in general position,
counts its crossings with exact geometric predicates, and checks that no
three edges meet at a point, so the drawing is admissible in the sense of the
formal statement.
"""

from __future__ import annotations

import random
from fractions import Fraction

from ..catalog import Catalog
from ..evidence import Conclusion
from .base import AppResult, computed, family_claim

MAX_EXACT_EDGES = 1600  # exact pairwise check is quadratic in the edge count


def zarankiewicz(m: int, n: int) -> int:
    return (m // 2) * ((m - 1) // 2) * (n // 2) * ((n - 1) // 2)


def harary_hill(n: int) -> int:
    return (n // 2) * ((n - 1) // 2) * ((n - 2) // 2) * ((n - 3) // 2) // 4


def drawing(m: int, n: int, seed: int = 0, spread: int = 1000) -> tuple[list[int], list[int]]:
    """Axis positions: sources at (x, 0), sinks at (0, y), split across both sides of the origin.

    Positions are distinct random integers, which puts the drawing in general
    position with overwhelming probability; the caller verifies it.
    """

    rng = random.Random(seed)

    def axis(count: int) -> list[int]:
        positive = sorted(rng.sample(range(1, spread * count), (count + 1) // 2))
        negative = sorted(-v for v in rng.sample(range(1, spread * count), count // 2))
        return negative + positive

    return axis(m), axis(n)


def _orient(ax: int, ay: int, bx: int, by: int, cx: int, cy: int) -> int:
    value = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    return (value > 0) - (value < 0)


def count_crossings(xs: list[int], ys: list[int]) -> tuple[int, int]:
    """Exact crossing pairs and distinct crossing points of the straight-line drawing.

    Edges sharing an endpoint meet only there; any other pair crosses exactly
    when each segment strictly separates the other's endpoints.
    """

    edges = [(x, y) for x in xs for y in ys]
    pairs = 0
    points: set[tuple[Fraction, Fraction]] = set()
    for i, (x1, y1) in enumerate(edges):
        for x2, y2 in edges[i + 1 :]:
            if x1 == x2 or y1 == y2:
                continue
            d1 = _orient(x1, 0, 0, y1, x2, 0)
            d2 = _orient(x1, 0, 0, y1, 0, y2)
            d3 = _orient(x2, 0, 0, y2, x1, 0)
            d4 = _orient(x2, 0, 0, y2, 0, y1)
            if d1 * d2 < 0 and d3 * d4 < 0:
                pairs += 1
                points.add(_intersection(x1, y1, x2, y2))
    return pairs, len(points)


def _intersection(x1: int, y1: int, x2: int, y2: int) -> tuple[Fraction, Fraction]:
    # Segment i lies on x / x_i + y / y_i = 1; solve the 2 x 2 system exactly.
    a1, b1, a2, b2 = Fraction(1, x1), Fraction(1, y1), Fraction(1, x2), Fraction(1, y2)
    det = a1 * b2 - a2 * b1
    return (b2 - b1) / det, (a1 - a2) / det


def svg(xs: list[int], ys: list[int], size: int = 640) -> str:
    span = max(map(abs, xs + ys)) * 1.08
    scale = size / (2 * span)

    def px(v: float) -> float:
        return round(size / 2 + v * scale, 2)

    def py(v: float) -> float:
        return round(size / 2 - v * scale, 2)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">',
             '<rect width="100%" height="100%" fill="white"/>']
    for x in xs:
        for y in ys:
            parts.append(f'<line x1="{px(x)}" y1="{py(0)}" x2="{px(0)}" y2="{py(y)}" stroke="#4a6fa5" stroke-width="0.8" stroke-opacity="0.7"/>')
    parts += [f'<circle cx="{px(x)}" cy="{py(0)}" r="4" fill="#c0392b"/>' for x in xs]
    parts += [f'<circle cx="{px(0)}" cy="{py(y)}" r="4" fill="#27ae60"/>' for y in ys]
    parts.append("</svg>")
    return "\n".join(parts)


def run(m: int, n: int, *, seed: int = 0, catalog: Catalog | None = None) -> AppResult:
    if m < 1 or n < 1:
        raise ValueError("both sides need at least one vertex")
    if m * n > MAX_EXACT_EDGES:
        raise ValueError(f"K_{{{m},{n}}} has {m * n} edges; exact verification is limited to {MAX_EXACT_EDGES}")
    target = zarankiewicz(m, n)
    for attempt in range(20):
        xs, ys = drawing(m, n, seed + attempt)
        pairs, points = count_crossings(xs, ys)
        if pairs == points:
            break
    else:
        raise RuntimeError("could not place the drawing in general position")
    if pairs != target:
        raise AssertionError(f"Zarankiewicz drawing has {pairs} crossings, expected {target}")

    achieved = computed(
        f"This straight-line drawing of K_{{{m},{n}}} has exactly {pairs} crossings, at {points} distinct points (no three edges concurrent)",
        "crossbar.count_crossings (exact integer orientation tests)",
        {"crossing_pairs": pairs, "crossing_points": points},
    )
    formula = computed(f"Z({m}, {n}) = {target}", "crossbar.zarankiewicz")
    lower = family_claim(
        catalog, "165", f"Every drawing of K_{{{m},{n}}} with continuous edges has at least Z({m}, {n}) crossings",
        challenges=["BipartiteCrossing"],
    )
    claims = [achieved, formula, lower]
    conclusions = [
        Conclusion(f"This layout is crossing-optimal: {target} is the minimum number of jumpers for a single-layer K_{{{m},{n}}}", [achieved, formula, lower]),
    ]
    outputs = {
        "m": m,
        "n": n,
        "crossings": pairs,
        "lower_bound": target,
        "sources": [[x, 0] for x in xs],
        "sinks": [[0, y] for y in ys],
        "edges": "every source joined to every sink by a straight segment",
    }
    if m == n:
        complete = family_claim(
            catalog, "165", f"For comparison, the crossing number of the complete graph K_{m} is {harary_hill(m)}",
            challenges=["CompleteCrossing"],
            limitations=["optimal drawings of K_n are not straight-line; straight-line layouts can need more crossings"],
        )
        claims.append(complete)
    headline = [
        f"K_{{{m},{n}}}: {pairs} crossings, equal to the proven minimum Z({m}, {n}) = {target}",
        f"{len(xs)} sources on the x-axis, {len(ys)} sinks on the y-axis, straight edges",
    ]
    return AppResult("crossbar", f"Crossing-optimal layout of K_{{{m},{n}}}", headline, outputs, claims, conclusions,
                     files={f"crossbar-{m}x{n}.svg": svg(xs, ys)})
