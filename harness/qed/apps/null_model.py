"""Degree-preserving null models for network structure.

Is the clustering in a transaction, communication or supply network more than
its degree sequence explains? The standard test compares an observed statistic
with its distribution over random graphs having exactly the same degrees,
sampled with the switch chain. That test is only as good as the sampler.

Family 131 proves the Kannan–Tetali–Vempala conjecture for simple graphs: the
lazy switch chain that proposes a switch on a uniform 4-set of vertices mixes
in polynomial time for every degree sequence, with the explicit bound
(formal statement ``switch_chain_tv_bound``)

    TV(t) <= sqrt(|Omega|) / 2 * exp(-t / (24 n^2 C(n, 4))).

With ``--chain theorem`` this app runs exactly that kernel and, with
``--certify-tv``, runs every sample for the number of steps the bound needs,
so each null sample's law is provably within the requested distance of
uniform. That is only affordable for small graphs. The default
``--chain edge`` is the usual fast double-edge swap: same uniform target, no
formal rate, so its mixing is judged by diagnostics and labelled empirical.
"""

from __future__ import annotations

import math
import random
import statistics as stats
from dataclasses import dataclass
from pathlib import Path

from ..catalog import Catalog
from ..evidence import Claim, Conclusion, Source, Tier
from .base import AppResult, computed, family_claim, literature_claim

STATISTICS = ("triangles", "transitivity", "assortativity")


@dataclass
class Graph:
    n: int
    edges: list[tuple[int, int]]
    labels: list[str]
    dropped_loops: int = 0
    dropped_duplicates: int = 0
    planted: tuple[str, ...] = ()  # demo only: the members of the planted ring

    def adjacency(self) -> list[set[int]]:
        adj: list[set[int]] = [set() for _ in range(self.n)]
        for u, v in self.edges:
            adj[u].add(v)
            adj[v].add(u)
        return adj


def read_edge_list(path: str | Path) -> Graph:
    """Whitespace- or comma-separated edge list; '#' starts a comment; extra columns ignored."""

    index: dict[str, int] = {}
    labels: list[str] = []
    seen: set[tuple[int, int]] = set()
    edges: list[tuple[int, int]] = []
    loops = duplicates = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].replace(",", " ").split()
        if len(line) < 2:
            continue
        ends = []
        for label in line[:2]:
            if label not in index:
                index[label] = len(labels)
                labels.append(label)
            ends.append(index[label])
        u, v = ends
        if u == v:
            loops += 1
            continue
        key = (min(u, v), max(u, v))
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        edges.append(key)
    return Graph(len(labels), edges, labels, loops, duplicates)


def demo_graph(seed: int = 7, n: int = 300, ring: int = 12) -> Graph:
    """Heterogeneous random network (Chung–Lu weights) with a planted dense ring of accounts."""

    rng = random.Random(seed)
    weights = [min(40.0, rng.paretovariate(2.2) * 2.5) for _ in range(n)]
    total = sum(weights)
    edges = set()
    for u in range(n):
        for v in range(u + 1, n):
            if rng.random() < min(1.0, weights[u] * weights[v] / total):
                edges.add((u, v))
    members = rng.sample(range(n), ring)
    for i, u in enumerate(members):
        for v in members[i + 1 :]:
            if rng.random() < 0.6:
                edges.add((min(u, v), max(u, v)))
    labels = [f"acct{u:03d}" for u in range(n)]
    return Graph(n, sorted(edges), labels, planted=tuple(labels[u] for u in members))


# -- statistics --------------------------------------------------------------------


def local_triangles(adj: list[set[int]]) -> list[int]:
    counts = [0] * len(adj)
    for u, neighbours in enumerate(adj):
        for v in neighbours:
            if v <= u:
                continue
            for w in neighbours & adj[v]:
                if w > v:
                    counts[u] += 1
                    counts[v] += 1
                    counts[w] += 1
    return counts


def measure(adj: list[set[int]], edges: list[tuple[int, int]], local: list[int] | None = None) -> dict[str, float]:
    local = local if local is not None else local_triangles(adj)
    triangles = sum(local) // 3
    triples = sum(len(a) * (len(a) - 1) // 2 for a in adj)
    degree = [len(a) for a in adj]
    m = len(edges)
    s_jk = sum(degree[u] * degree[v] for u, v in edges) / m
    s_mean = sum(degree[u] + degree[v] for u, v in edges) / (2 * m)
    s_sq = sum(degree[u] ** 2 + degree[v] ** 2 for u, v in edges) / (2 * m)
    denominator = s_sq - s_mean**2
    return {
        "triangles": float(triangles),
        "transitivity": 3 * triangles / triples if triples else 0.0,
        "assortativity": (s_jk - s_mean**2) / denominator if denominator > 1e-12 else 0.0,
    }


# -- chains ------------------------------------------------------------------------


class EdgeSwapChain:
    """Double-edge swap: pick two edges uniformly, rewire them one of two ways if the result stays simple."""

    name = "edge"

    def __init__(self, graph: Graph, rng: random.Random):
        self.edges = list(graph.edges)
        self.adj = graph.adjacency()
        self.rng = rng

    def step(self) -> bool:
        m = len(self.edges)
        i, j = self.rng.randrange(m), self.rng.randrange(m)
        if i == j:
            return False
        (a, b), (c, d) = self.edges[i], self.edges[j]
        if self.rng.random() < 0.5:
            c, d = d, c
        # Replace {a,b},{c,d} by {a,d},{c,b}.
        if a == d or c == b or d in self.adj[a] or b in self.adj[c]:
            return False
        for x, y in ((a, b), (c, d)):
            self.adj[x].discard(y)
            self.adj[y].discard(x)
        for x, y in ((a, d), (c, b)):
            self.adj[x].add(y)
            self.adj[y].add(x)
        self.edges[i] = (min(a, d), max(a, d))
        self.edges[j] = (min(c, b), max(c, b))
        return True

    def snapshot(self) -> tuple[list[set[int]], list[tuple[int, int]]]:
        return self.adj, self.edges


class TheoremChain:
    """The exact kernel of family 131's ``switchKernel``.

    With probability 1/2 stay put; otherwise choose a uniform 4-set S and a
    uniform ordered pair (M, N) of distinct perfect matchings of S, and replace
    M by N when M is present and N absent. Each proposal has probability
    1 / (12 C(n, 4)), as in the formal statement.
    """

    name = "theorem"

    def __init__(self, graph: Graph, rng: random.Random):
        if graph.n < 4:
            raise ValueError("the theorem chain needs at least 4 vertices")
        self.n = graph.n
        self.adj = graph.adjacency()
        self.rng = rng

    def step(self) -> bool:
        if self.rng.random() < 0.5:
            return False
        p, q, r, s = self.rng.sample(range(self.n), 4)
        matchings = (((p, q), (r, s)), ((p, r), (q, s)), ((p, s), (q, r)))
        remove, add = self.rng.sample(matchings, 2)
        adj = self.adj
        if not all(y in adj[x] for x, y in remove) or any(y in adj[x] for x, y in add):
            return False
        for x, y in remove:
            adj[x].discard(y)
            adj[y].discard(x)
        for x, y in add:
            adj[x].add(y)
            adj[y].add(x)
        return True

    def snapshot(self) -> tuple[list[set[int]], list[tuple[int, int]]]:
        edges = [(u, v) for u in range(self.n) for v in self.adj[u] if u < v]
        return self.adj, edges


def certified_steps(n: int, m: int, tv: float) -> int:
    """Steps after which ``switch_chain_tv_bound`` guarantees total variation <= tv.

    Uses |Omega| <= C(C(n, 2), m): every state is a simple graph with m edges.
    """

    if not 0 < tv < 1:
        raise ValueError("the total-variation target must lie in (0, 1)")
    pairs = n * (n - 1) // 2
    log_omega = math.lgamma(pairs + 1) - math.lgamma(m + 1) - math.lgamma(pairs - m + 1)
    rate = 24 * n * n * math.comb(n, 4)
    needed = rate * (0.5 * log_omega - math.log(2 * tv))
    return max(0, math.ceil(needed * (1 + 1e-9)) + 1)


# -- application --------------------------------------------------------------------


def _rhat(chains: list[list[float]]) -> float | None:
    """Gelman–Rubin potential scale reduction across chains."""

    if len(chains) < 2 or min(len(c) for c in chains) < 2:
        return None
    means = [stats.fmean(c) for c in chains]
    within = stats.fmean(stats.variance(c) for c in chains)
    length = min(len(c) for c in chains)
    between = length * stats.variance(means)
    if within <= 0:
        return 1.0 if between <= 0 else float("inf")
    pooled = (length - 1) / length * within + between / length
    return math.sqrt(pooled / within)


def run(
    graph: Graph,
    *,
    chain: str = "edge",
    samples: int = 200,
    chains: int = 4,
    swaps_per_edge: float = 20.0,
    certify_tv: float | None = None,
    max_steps: int = 50_000_000,
    seed: int = 0,
    top: int = 10,
    catalog: Catalog | None = None,
) -> AppResult:
    if chain not in ("edge", "theorem"):
        raise ValueError("chain must be edge or theorem")
    if certify_tv is not None and chain != "theorem":
        raise ValueError("--certify-tv applies only to --chain theorem, the chain family 131 bounds")
    if graph.n < 4 or len(graph.edges) < 2:
        raise ValueError("the graph needs at least 4 vertices and 2 edges")
    rng = random.Random(seed)
    adj = graph.adjacency()
    observed_local = local_triangles(adj)
    observed = measure(adj, graph.edges, observed_local)
    m = len(graph.edges)
    claims: list[Claim] = []
    conclusions: list[Conclusion] = []
    notes: dict[str, object] = {"chain": chain}

    chain_type = TheoremChain if chain == "theorem" else EdgeSwapChain
    per_sample_steps: int | None = None
    if certify_tv is not None:
        per_sample_steps = certified_steps(graph.n, m, certify_tv)
        notes["certified_steps_per_sample"] = per_sample_steps
        if per_sample_steps * samples > max_steps:
            raise ValueError(
                f"certifying TV <= {certify_tv:g} needs {per_sample_steps:,} steps per sample "
                f"({per_sample_steps * samples:,} in total), above --max-steps {max_steps:,}; "
                "use fewer samples, a looser target, a smaller graph, or drop --certify-tv"
            )

    null: dict[str, list[float]] = {name: [] for name in STATISTICS}
    by_chain: list[dict[str, list[float]]] = []
    local_sum = [0.0] * graph.n
    local_sq = [0.0] * graph.n
    accepted = proposed = 0

    def record(sample_adj, sample_edges, bucket) -> None:
        local = local_triangles(sample_adj)
        values = measure(sample_adj, sample_edges, local)
        for name in STATISTICS:
            null[name].append(values[name])
            bucket[name].append(values[name])
        for v, count in enumerate(local):
            local_sum[v] += count
            local_sq[v] += count * count

    if per_sample_steps is not None:
        # Independent restarts from the observed graph, each run for the certified length.
        bucket = {name: [] for name in STATISTICS}
        for _ in range(samples):
            walker = chain_type(graph, random.Random(rng.random()))
            for _ in range(per_sample_steps):
                accepted += walker.step()
            proposed += per_sample_steps
            record(*walker.snapshot(), bucket)
        by_chain.append(bucket)
    else:
        burn = int(swaps_per_edge * m)
        thin = max(1, m)
        per_chain = math.ceil(samples / chains)
        for _ in range(chains):
            walker = chain_type(graph, random.Random(rng.random()))
            bucket = {name: [] for name in STATISTICS}
            for _ in range(burn):
                accepted += walker.step()
            proposed += burn
            for _ in range(per_chain):
                for _ in range(thin):
                    accepted += walker.step()
                proposed += thin
                record(*walker.snapshot(), bucket)
            by_chain.append(bucket)
        notes.update({"chains": chains, "burn_in_steps": burn, "thinning_steps": thin})
    notes["acceptance_rate"] = round(accepted / max(1, proposed), 4)
    total = len(null["triangles"])

    claims.append(computed(
        f"Observed: {int(observed['triangles'])} triangles, transitivity {observed['transitivity']:.4f}, "
        f"degree assortativity {observed['assortativity']:.4f} ({graph.n} nodes, {m} edges)",
        "null-model.measure", {k: round(v, 6) for k, v in observed.items()},
    ))
    if per_sample_steps is not None:
        steps = computed(
            f"{per_sample_steps:,} steps make the bound sqrt(|Omega|)/2 exp(-t / (24 n^2 C(n,4))) at most {certify_tv:g} "
            f"(n = {graph.n}, |Omega| <= C(C(n,2), m))",
            "null-model.certified_steps",
        )
        theorem = family_claim(
            catalog, "131", "The lazy 4-set switch chain satisfies TV(t) <= sqrt(|Omega|)/2 exp(-t / (24 n^2 C(n,4))) for every graphical degree sequence",
            challenges=["SwitchChain"],
        )
        sampler = Claim(
            f"Each null sample's law is within total variation {certify_tv:g} of uniform over graphs with these degrees",
            max(steps.tier, theorem.tier), steps.sources + theorem.sources, theorem.limitations,
        )
        claims += [steps, theorem]
    else:
        rhats = {name: _rhat([b[name] for b in by_chain]) for name in STATISTICS}
        notes["rhat"] = {k: (None if v is None else round(v, 4)) for k, v in rhats.items()}
        worst = max((v for v in rhats.values() if v is not None), default=None)
        limitations = ["convergence diagnostics can miss slow mixing; they are not a guarantee"]
        if chain == "edge":
            limitations.append("family 131's rate covers the lazy 4-set chain (--chain theorem), not this edge-swap chain")
        sampler = Claim(
            f"The {chain} chain's null samples are close to uniform over graphs with these degrees "
            f"(Gelman–Rubin R-hat across {chains} chains: {'n/a' if worst is None else f'{worst:.3f}'})",
            Tier.EMPIRICAL if worst is not None and worst < 1.1 else Tier.UNKNOWN,
            [Source("measurement", "null-model.rhat", str(notes["rhat"]))], limitations,
        )
        if chain == "edge":
            claims.append(literature_claim(
                "The double-edge swap chain has the uniform distribution on simple graphs with a given degree sequence as its stationary law",
                "Taylor (1981), connectivity of degree-sequence realisations; symmetric proposals",
            ))
    claims.append(sampler)

    results = {}
    for name in STATISTICS:
        values = null[name]
        mean = stats.fmean(values)
        sd = stats.pstdev(values)
        obs = observed[name]
        upper = (1 + sum(v >= obs for v in values)) / (1 + total)
        lower = (1 + sum(v <= obs for v in values)) / (1 + total)
        results[name] = {
            "observed": round(obs, 6),
            "null_mean": round(mean, 6),
            "null_sd": round(sd, 6),
            "z": None if sd == 0 else round((obs - mean) / sd, 3),
            "p_upper": round(upper, 5),
            "p_lower": round(lower, 5),
            "p_two_sided": round(min(1.0, 2 * min(upper, lower)), 5),
        }
        r = results[name]
        direction = "above" if obs > mean else "below"
        test = Claim(
            f"{name}: observed {obs:.4g} vs null {mean:.4g} ± {sd:.3g} (z = {r['z']}, two-sided p = {r['p_two_sided']})",
            Tier.EMPIRICAL, [Source("measurement", "null-model", f"{total} null samples")],
            ["Monte Carlo p-value; resolution limited by the sample count"],
        )
        claims.append(test)
        if r["p_two_sided"] <= 0.05:
            conclusions.append(Conclusion(
                f"{name} is significantly {direction} what the degree sequence explains (p = {r['p_two_sided']})", [test, sampler],
            ))
    if not conclusions:
        conclusions.append(Conclusion("No tested statistic departs from the degree-preserving null at p <= 0.05",
                                      [c for c in claims if c.tier == Tier.EMPIRICAL][:1] + [sampler]))

    flagged = []
    for v in range(graph.n):
        mean = local_sum[v] / total
        var = max(0.0, local_sq[v] / total - mean * mean)
        if observed_local[v] > mean and var > 0:
            flagged.append((round((observed_local[v] - mean) / math.sqrt(var), 2), graph.labels[v], observed_local[v], round(mean, 2)))
    flagged.sort(reverse=True)
    outputs = {
        "nodes": graph.n,
        "edges": m,
        "dropped": {"self_loops": graph.dropped_loops, "duplicate_edges": graph.dropped_duplicates},
        "samples": total,
        "statistics": results,
        "sampler": notes,
        "top_excess_triangle_nodes": [
            {"node": label, "z": z, "triangles": obs, "null_mean": mean} for z, label, obs, mean in flagged[:top]
        ],
    }
    if graph.planted:
        hits = sum(entry["node"] in graph.planted for entry in outputs["top_excess_triangle_nodes"])
        outputs["demo_check"] = {"planted_ring": list(graph.planted), "planted_in_top": hits, "top": len(outputs["top_excess_triangle_nodes"])}
    tri = results["triangles"]
    headline = [
        f"{graph.n} nodes, {m} edges; {total} degree-preserving null samples ({chain} chain)",
        f"Triangles: {int(tri['observed'])} observed vs {tri['null_mean']:.1f} ± {tri['null_sd']:.1f} expected (z = {tri['z']})",
    ]
    if flagged[:top]:
        headline.append("Most over-clustered nodes: " + ", ".join(f"{label} (z={z})" for z, label, _, _ in flagged[: min(5, top)]))
    if "demo_check" in outputs:
        check = outputs["demo_check"]
        headline.append(f"Demo check: {check['planted_in_top']} of the top {check['top']} flagged nodes belong to the planted ring of {len(graph.planted)}")
    return AppResult("null-model", "Degree-preserving null-model test", headline, outputs, claims, conclusions)
