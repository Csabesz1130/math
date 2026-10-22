"""From result families to industrial use: a curated registry and a triage of the whole collection.

Readiness levels:

- ``R3 deployed``: a tool in this harness puts the result to work, with
  verified outputs (``qed app ...``).
- ``R2 transcribable``: the paper gives an explicit algorithm; with a kit, a
  model-written transcription can be differentially tested (``qed solve``).
- ``R1 decision input``: the result settles a limit, guarantee or
  impossibility that changes an engineering decision without new code.
- ``R0 research``: no near-term industrial path identified here.

The "industrial reading" of each entry is this harness's interpretation, not a
claim of the manuscripts. Every entry also names the caveat that limits it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .catalog import Catalog, Family, plain

READINESS = {
    "R3": "deployed in this harness",
    "R2": "explicit algorithm; transcribe and verify",
    "R1": "decision input",
    "R0": "research",
}


@dataclass(frozen=True)
class Application:
    families: tuple[str, ...]
    readiness: str
    sectors: tuple[str, ...]
    reading: str
    caveat: str
    tool: str | None = None  # "app:<name>" or "kit:<name>"


REGISTRY: tuple[Application, ...] = (
    # -- R3: deployed -------------------------------------------------------------
    Application(
        ("179", "076"), "R3", ("radar", "sonar", "telecom synchronisation"),
        "Barker codes stop at length 13, so longer codes must accept PSL >= 2; the tool designs low-sidelobe codes, "
        "and proves PSL lower bounds by exhaustive search where it fits. Merit factors have no absolute ceiling (076).",
        "076 is asymptotic and gives no construction at practical lengths; search quality is below published records.",
        "app:pulse-code",
    ),
    Application(
        ("165",), "R3", ("PCB and VLSI layout", "interconnect design", "graph drawing"),
        "Z(m, n) is the exact minimum number of crossings, hence jumpers or vias, of a single-layer complete bipartite "
        "interconnect; the tool emits a layout that attains it, verified by exact geometry.",
        "Optimality is for complete bipartite connectivity; real netlists are usually sparser.",
        "app:crossbar",
    ),
    Application(
        ("131",), "R3", ("fraud and AML analytics", "cybersecurity", "bioinformatics", "supply-chain networks"),
        "Degree-preserving null models test whether clustering exceeds what activity levels explain; the explicit "
        "mixing bound lets small graphs be sampled with a certified total-variation distance.",
        "The certified bound is affordable only for small graphs; the fast edge-swap chain is judged by diagnostics.",
        "app:null-model",
    ),
    Application(
        ("102",), "R3", ("VLSI via minimisation", "spin-glass ground states", "QUBO and quantum-hardware benchmarking"),
        "No polynomial-time method beats the Goemans–Williamson ratio on all instances unless P = NP, so per-instance "
        "certificates are the useful guarantee; the tool returns a cut with an SDP dual bound.",
        "Dense certificate limited to a few thousand vertices.",
        "app:maxcut",
    ),
    # -- R2: transcribable ----------------------------------------------------------
    Application(
        ("124",), "R2", ("build and CI systems", "compiler instruction scheduling", "batch manufacturing"),
        "Exact minimum-makespan schedules for unit tasks with dependencies on three identical workers, replacing "
        "list-scheduling heuristics that can be a step worse.",
        "Unit processing times and exactly three machines; the algorithm is intricate.",
        "kit:three-machine",
    ),
    Application(
        ("128",), "R2", ("genome and read assembly", "dictionary compression"),
        "A polynomial-time superstring within twice the optimum on every input, a worst case greedy assembly does not "
        "guarantee.",
        "Factor 2 is a worst-case guarantee; greedy is often better in practice.",
        "kit:superstring",
    ),
    Application(
        ("115",), "R2", ("clinical and A/B statistics", "official-statistics disclosure control", "ecology"),
        "Exact uniform sampling of tables with fixed margins gives exact conditional tests of independence for sparse "
        "r x c tables, and counting with cell bounds supports disclosure-risk estimates.",
        "Polynomial bounds may carry large exponents; no kit yet.",
    ),
    Application(
        ("113",), "R2", ("statistical physics (dimer models)", "network reliability"),
        "Approximate counting of perfect matchings in general (non-bipartite, non-planar) graphs.",
        "Planar instances, including most molecules, are already exact by FKT; no kit yet.",
    ),
    Application(
        ("120",), "R2", ("assignment and matching markets", "network design"),
        "Maximum matchings and degree-constrained subgraphs in almost-linear time on general graphs.",
        "The n^{o(1)} factor may be large at practical sizes; no kit yet.",
    ),
    Application(
        ("121",), "R2", ("bioinformatics", "record linkage and deduplication"),
        "(1 + eps)-approximate edit distance in almost-linear time.",
        "Asymptotic guarantee at fixed eps; tuned heuristics are strong in practice; no kit yet.",
    ),
    Application(
        ("125",), "R2", ("facility location", "clustering", "content-delivery placement"),
        "A deterministic (1 + 2/e + eps)-approximation for metric k-median, which is the best possible unless P = NP.",
        "Worst-case ratio; local search is often better on real data; no kit yet.",
    ),
    Application(
        ("178",), "R2", ("datacenter and interconnect topologies", "expander and LDPC codes"),
        "Deterministic d-regular Ramanujan graphs for every fixed degree and every large even size.",
        "The running-time exponent depends on d and 'sufficiently large' is not quantified; no kit yet.",
    ),
    Application(
        ("142",), "R2", ("coding theory", "computer algebra", "cryptographic implementations"),
        "Deterministic polynomial-time factorisation over prime fields removes the randomness assumption from "
        "factoring-based routines.",
        "Not formalized in the collection; randomized algorithms remain faster in practice; no kit yet.",
    ),
    Application(
        ("276",), "R2", ("quantum networking", "quantum memory"),
        "The classical capacity of every generalized amplitude-damping qubit channel is an explicit one-variable "
        "maximum, so link budgets for this noise model become computable exactly.",
        "Specific noise model; no kit yet.",
    ),
    Application(
        ("273",), "R2", ("optical and satellite communication",),
        "The capacity region of the degraded two-receiver pure-loss bosonic broadcast channel is now exact under a "
        "mean-photon constraint.",
        "Degraded two-receiver case only; no kit yet.",
    ),
    # -- R1: decision inputs ----------------------------------------------------------
    Application(
        ("118",), "R1", ("cutting stock", "logistics packing", "cloud VM placement"),
        "The configuration LP can underestimate the bin-packing optimum by any additive constant, so branch-and-price "
        "stopping rules that assume an LP-plus-one round-up are unsound.",
        "Gap instances use item sizes above 1/6; typical instances may still round up.",
    ),
    Application(
        ("117",), "R1", ("graph partitioning", "clustering"),
        "Uniform sparsest cut has no constant-factor polynomial approximation unless P = NP, and the Goemans–Linial "
        "SDP has a near-sqrt(log n) gap: expect instance-dependent quality, not guarantees.",
        "Worst-case statements.",
    ),
    Application(
        ("089",), "R1", ("network flow design",),
        "On planar and bounded-treewidth networks, multicommodity flow–cut gaps are bounded by a constant, so cut-based "
        "capacity estimates are within a fixed factor of achievable flow.",
        "The constant is universal but not necessarily small.",
    ),
    Application(
        ("266",), "R1", ("quantum key distribution",),
        "Exactly three mutually unbiased bases exist in dimension six, so six-level QKD protocols needing a complete "
        "set of d + 1 = 7 bases cannot be built.",
        "The exclusion is a certified computation under stated floating-point conditions.",
    ),
    Application(
        ("235",), "R1", ("SAT-solver benchmarking", "EDA and verification tooling"),
        "Random k-SAT has a sharp limiting threshold with linear-variance hitting time, so instances generated near it "
        "are a principled hardness benchmark; the 3-SAT threshold is computable.",
        "Asymptotic; finite-size corrections matter at benchmark sizes.",
    ),
    Application(
        ("281",), "R1", ("quantum optimisation benchmarking",),
        "QAOA with fixed depth-independent angles reaches the SK ground-state energy in the limit, a reference point "
        "for claims of quantum advantage on Max-Cut-like problems.",
        "Thermodynamic-first limit; says nothing about finite sizes or noise.",
    ),
    Application(
        ("119",), "R1", ("communications", "sensor data compression"),
        "Under bit-flip noise, a single coordinate is the most informative one-bit summary of uniform bits: complex "
        "one-bit encoders cannot do better.",
        "Uniform inputs and symmetric noise.",
    ),
    Application(
        ("090",), "R1", ("materials science", "sensor and antenna placement"),
        "The triangular lattice minimises energy for every completely monotone pair potential in the plane, settling "
        "the optimal 2D arrangement for that class of interactions.",
        "Planar, infinite-configuration statement.",
    ),
    Application(
        ("278", "275"), "R1", ("computational chemistry", "materials simulation"),
        "Kohn–Sham ensemble representability fails for some molecules, and continuum Coulomb ground-state energies are "
        "QMA-hard: no general efficient method, classical or quantum, should be expected.",
        "Constructed and worst-case instances; typical molecules may behave well.",
    ),
    Application(
        ("265",), "R1", ("quantum materials simulation",),
        "Gapped 2D ground states have area laws and polynomial-bond-dimension PEPS approximations, supporting "
        "tensor-network methods for such systems.",
        "Not formalized in the collection; requires a uniform spectral gap.",
    ),
    Application(
        ("029",), "R1", ("pseudorandom generators", "cyclic codes"),
        "Every admissible base is a primitive root for infinitely many primes, with positive-density lower bounds, so "
        "searches for full-period multiplicative generators with a fixed multiplier terminate.",
        "The density constant and 'sufficiently large' threshold are not explicit.",
    ),
    # -- R0: noted, not ready ----------------------------------------------------------
    Application(
        ("238",), "R0", ("format-preserving encryption research",),
        "The Thorp shuffle mixes in Theta(log N) shuffles, relevant to Thorp-shuffle ciphers on small domains.",
        "Total-variation mixing of an ideal shuffle is not a cipher security proof; do not set cryptographic "
        "parameters from it.",
    ),
    Application(
        ("107", "109", "130"), "R0", ("high-performance computing", "big-number arithmetic"),
        "New exponents for matrix multiplication, integer multiplication and exact DFTs.",
        "Galactic: the constants (e.g. kappa = 2^-182, delta = 1e-13) give no practical speedup.",
    ),
    Application(
        ("111",), "R0", ("online pricing and allocation",),
        "One sample per item suffices for a constant-competitive matroid prophet inequality.",
        "The proved ratio is 2^-310: useful as a theorem, not as a pricing rule.",
    ),
)

_SIGNALS = {
    "algorithm": re.compile(r"\b(algorithm|polynomial[- ]time|approximation scheme|FPRAS|sampler|sampling|deterministic construction|computable)\b", re.I),
    "limit": re.compile(r"\b(NP-hard|hardness|impossible|cannot|no algorithm|undecidab|lower bound|optimal|sharp|threshold|capacity)\b", re.I),
    "counterexample": re.compile(r"\bcounterexample", re.I),
}


@dataclass
class Row:
    family: Family
    readiness: str
    application: Application | None
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        out = {
            "family": self.family.id,
            "title": plain(self.family.title),
            "subject": self.family.subject,
            "formal_tier": self.family.formal_tier.label,
            "readiness": self.readiness,
            "signals": self.signals,
        }
        if self.application:
            out.update({
                "sectors": list(self.application.sectors),
                "reading": self.application.reading,
                "caveat": self.application.caveat,
                "tool": self.application.tool,
                "group": list(self.application.families),
            })
        return out


def triage(catalog: Catalog) -> list[Row]:
    curated: dict[str, Application] = {}
    for application in REGISTRY:
        for family_id in application.families:
            curated[family_id] = application
    rows = []
    for family in catalog:
        text = f"{plain(family.title)} {plain(family.summary)}"
        signals = [name for name, pattern in _SIGNALS.items() if pattern.search(text)]
        application = curated.get(family.id)
        rows.append(Row(family, application.readiness if application else "R0", application, signals))
    return rows


def markdown(rows: list[Row], catalog: Catalog) -> str:
    counts = {level: sum(r.readiness == level for r in rows) for level in READINESS}
    curated = [r for r in rows if r.application]
    lines = [
        "# Industrial map of the result collection",
        "",
        "Generated by `qed map --markdown`. It triages all "
        f"{len(rows)} result families by how close each is to industrial use. The *industrial reading* is this "
        "harness's interpretation, not a claim of the manuscripts; every curated entry names the caveat that limits it.",
        "",
        "| Readiness | Meaning | Families |",
        "| --- | --- | --- |",
    ]
    lines += [f"| {level} | {meaning} | {counts[level]} |" for level, meaning in READINESS.items()]
    lines += ["", "`formalized` means the collection ships a Lean statement with a Comparator configuration "
              f"(review status: {catalog.review_status}); `published` means manuscript only.", ""]
    seen: set[int] = set()
    for level in ("R3", "R2", "R1", "R0"):
        group = [r for r in curated if r.readiness == level]
        if not group:
            continue
        lines += [f"## {level}: {READINESS[level]}", ""]
        for row in group:
            application = row.application
            if id(application) in seen:
                continue
            seen.add(id(application))
            members = [catalog.get(f) for f in application.families]
            names = "; ".join(f"{f.id} {plain(f.title)} (`{f.formal_tier.label}`)" for f in members)
            lines.append(f"### {names}")
            lines.append("")
            lines.append(f"- **Sectors:** {', '.join(application.sectors)}")
            lines.append(f"- **Industrial reading:** {application.reading}")
            lines.append(f"- **Caveat:** {application.caveat}")
            if application.tool:
                kind, _, name = application.tool.partition(":")
                command = f"qed app {name}" if kind == "app" else f"qed solve problems/ (kit `{name}`)"
                lines.append(f"- **Tool:** `{command}`")
            lines.append("")
    candidates = [r for r in rows if not r.application and "algorithm" in r.signals]
    lines += [
        "## Uncurated families with algorithmic signals",
        "",
        "Not yet assessed; their summaries mention algorithms, sampling or computability. Candidates for the next kits.",
        "",
        "| Family | Title | Subject | Formal |",
        "| --- | --- | --- | --- |",
    ]
    lines += [f"| {r.family.id} | {plain(r.family.title)} | {r.family.subject} | `{r.family.formal_tier.label}` |" for r in candidates]
    lines.append("")
    return "\n".join(lines)
