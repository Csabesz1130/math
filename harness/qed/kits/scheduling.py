"""Kit for family 124: minimum-makespan scheduling of unit jobs with precedence
constraints on three identical machines (P3 | prec, p_j = 1 | C_max).

Family 124 gives a deterministic polynomial-time algorithm for this problem,
open since Garey and Johnson. The algorithm is intricate; this kit checks a
transcription of it against an exact exponential-time oracle on small DAGs.

Industrial reading: build and CI systems, compiler instruction scheduling and
batch pipelines schedule unit-ish tasks with dependencies on a few identical
workers; an exact polynomial algorithm replaces heuristics with optimal plans.
"""

from __future__ import annotations

import random
from functools import lru_cache
from itertools import combinations

NAME = "three-machine"
FAMILY = "124"
ENTRYPOINT = "schedule"
MACHINES = 3
INTERFACE = """
def schedule(instance: dict) -> list[int]

instance = {"jobs": n, "edges": [[u, v], ...]}
    Jobs are 0..n-1, each of unit length. An edge [u, v] means job u must finish before job v starts.
    The edges form a DAG.

Return slot, a list of n non-negative integers: slot[j] is the time step in which job j runs on one of
three identical machines. At most three jobs may share a step, and slot[u] < slot[v] for every edge.
The schedule must have minimum makespan, max(slot) + 1.
"""


# Random DAGs almost never separate list-scheduling heuristics from the optimum,
# so a transcription that silently degrades to a greedy rule would pass on them.
# These instances were found by hill-climbing on the gap between the optimum and
# highest-level-first, Coffman–Graham labelling and most-successors-first list
# scheduling; each defeats at least one of those rules. The oracle recomputes
# every optimum at check time, so nothing here is trusted beyond its edges.
ADVERSARIAL = (
    (7, ((0, 1), (1, 6), (2, 3), (2, 6), (4, 1), (5, 1), (5, 3))),
    (7, ((0, 1), (2, 1), (2, 5), (3, 1), (3, 5), (4, 0), (4, 1), (6, 0), (6, 1), (6, 5))),
    (9, ((1, 0), (1, 5), (1, 6), (2, 0), (2, 5), (2, 6), (4, 5), (4, 6), (7, 0), (7, 3), (8, 2), (8, 3))),
    (9, ((0, 2), (0, 3), (0, 4), (1, 3), (1, 4), (1, 8), (2, 3), (5, 4), (5, 7), (5, 8), (6, 2), (6, 8))),
    (9, ((0, 5), (0, 6), (0, 8), (1, 4), (1, 6), (1, 8), (2, 4), (2, 6), (3, 4), (3, 5), (3, 8), (7, 2), (7, 5))),
    (10, ((2, 0), (3, 0), (3, 4), (3, 6), (5, 4), (5, 6), (5, 8), (7, 1), (7, 4), (7, 6), (8, 2), (9, 8))),
    (11, ((1, 0), (2, 3), (2, 4), (2, 6), (2, 8), (3, 6), (4, 0), (5, 0), (5, 6), (5, 7), (7, 0), (7, 6), (8, 0),
          (8, 1), (8, 3), (8, 6), (8, 7), (9, 1), (9, 4), (9, 6), (9, 8), (10, 0), (10, 4))),
    (12, ((3, 1), (3, 4), (3, 7), (3, 8), (3, 9), (3, 11), (4, 1), (4, 10), (5, 1), (5, 7), (5, 10), (6, 1), (6, 4),
          (6, 9), (6, 10), (7, 1), (7, 10), (8, 10), (8, 11), (9, 0), (9, 2), (11, 0), (11, 1), (11, 10))),
    (12, ((0, 2), (0, 4), (0, 7), (1, 2), (1, 6), (3, 4), (3, 6), (4, 5), (7, 2), (8, 2), (9, 1), (9, 4), (9, 6),
          (9, 7), (9, 8), (10, 1), (10, 3), (10, 4), (10, 8), (11, 3), (11, 5))),
)


def instances(seed: int, count: int) -> list[dict]:
    """Adversarial instances under a fresh random relabelling, then random DAGs."""

    rng = random.Random(seed)
    out = []
    for n, edges in ADVERSARIAL[: max(1, count // 3)]:
        label = list(range(n))
        rng.shuffle(label)
        out.append({"jobs": n, "edges": sorted([label[u], label[v]] for u, v in edges)})
    shapes = ("random", "layered", "chains", "intree", "outtree")
    for index in range(count - len(out)):
        n = rng.randint(6, 14)
        out.append({"jobs": n, "edges": _edges(rng, n, shapes[index % len(shapes)])})
    return out


def _edges(rng: random.Random, n: int, shape: str) -> list[list[int]]:
    order = list(range(n))
    rng.shuffle(order)
    edges: set[tuple[int, int]] = set()
    if shape == "random":
        p = rng.choice((0.15, 0.25, 0.4))
        edges = {(order[i], order[j]) for i in range(n) for j in range(i + 1, n) if rng.random() < p}
    elif shape == "layered":
        layers = [order[i::3] for i in range(3)]
        for upper, lower in zip(layers, layers[1:]):
            for v in lower:
                for u in rng.sample(upper, k=min(len(upper), rng.randint(1, 2))):
                    edges.add((u, v))
    elif shape == "chains":
        cut = sorted(rng.sample(range(1, n), k=min(n - 1, rng.randint(1, 4))))
        for chain in (order[a:b] for a, b in zip([0, *cut], [*cut, n])):
            edges.update(zip(chain, chain[1:]))
    elif shape == "intree":
        for i in range(1, n):
            edges.add((order[i], order[rng.randrange(i)]))
    else:
        for i in range(1, n):
            edges.add((order[rng.randrange(i)], order[i]))
    return sorted([u, v] for u, v in edges)


def _predecessors(instance: dict) -> list[int]:
    preds = [0] * instance["jobs"]
    for u, v in instance["edges"]:
        preds[v] |= 1 << u
    return preds


def oracle(instance: dict) -> int:
    """Exact minimum makespan by dynamic programming over completed-job sets.

    Some optimal schedule never idles a machine while a job is available (move
    any such job earlier: its predecessors are done and its successors run after
    its old slot), so each step runs min(3, available) jobs.
    """

    n = instance["jobs"]
    preds = _predecessors(instance)
    full = (1 << n) - 1

    @lru_cache(maxsize=None)
    def best(done: int) -> int:
        if done == full:
            return 0
        available = [j for j in range(n) if not done >> j & 1 and preds[j] & done == preds[j]]
        if len(available) <= MACHINES:
            return 1 + best(done | sum(1 << j for j in available))
        return 1 + min(best(done | (1 << a) | (1 << b) | (1 << c)) for a, b, c in combinations(available, MACHINES))

    return best(0)


def check(instance: dict, output, reference: int) -> tuple[bool, str]:
    n = instance["jobs"]
    if not isinstance(output, list) or len(output) != n or not all(isinstance(s, int) and s >= 0 for s in output):
        return False, f"expected a list of {n} non-negative integers, got {output!r}"
    load: dict[int, int] = {}
    for slot in output:
        load[slot] = load.get(slot, 0) + 1
    crowded = [slot for slot, count in load.items() if count > MACHINES]
    if crowded:
        return False, f"step {crowded[0]} runs {load[crowded[0]]} jobs on {MACHINES} machines"
    for u, v in instance["edges"]:
        if output[u] >= output[v]:
            return False, f"precedence {u} -> {v} violated (slots {output[u]} and {output[v]})"
    makespan = max(output) + 1
    if makespan != reference:
        return False, f"makespan {makespan}, but the optimum is {reference}"
    return True, "feasible and optimal"


def baseline(instance: dict) -> list[int]:
    """Highest-level-first list scheduling (Hu). Optimal on in-forests, not in general."""

    n = instance["jobs"]
    successors: list[list[int]] = [[] for _ in range(n)]
    for u, v in instance["edges"]:
        successors[u].append(v)
    level = [0] * n
    for j in reversed(_topological(instance)):
        level[j] = 1 + max((level[s] for s in successors[j]), default=0)
    preds = _predecessors(instance)
    slot = [-1] * n
    done = 0
    step = 0
    while done != (1 << n) - 1:
        available = [j for j in range(n) if slot[j] < 0 and preds[j] & done == preds[j]]
        chosen = sorted(available, key=lambda j: (-level[j], j))[:MACHINES]
        for j in chosen:
            slot[j] = step
        done |= sum(1 << j for j in chosen)
        step += 1
    return slot


def _topological(instance: dict) -> list[int]:
    n = instance["jobs"]
    indegree = [0] * n
    successors: list[list[int]] = [[] for _ in range(n)]
    for u, v in instance["edges"]:
        successors[u].append(v)
        indegree[v] += 1
    ready = [j for j in range(n) if indegree[j] == 0]
    order = []
    while ready:
        j = ready.pop()
        order.append(j)
        for s in successors[j]:
            indegree[s] -= 1
            if indegree[s] == 0:
                ready.append(s)
    return order
