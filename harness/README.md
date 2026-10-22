# qed: from mathematical results to verified industrial tools

This directory adds a harness to the manuscript collection. It does three things.

1. **Solves problems with models, under verification.** A generate → verify → refine loop
   samples several attempts per round in parallel, each steered toward a different strategy,
   and runs every attempt through trusted checks: a reference answer, a checker written by
   the problem's author, an exact oracle, or a Lean compile with an axiom audit. Verifier
   messages (counterexamples, failing instances, referee objections) seed the next round.
   Models may return values, objects, proofs or implementations, or a **search program**
   whose output is checked and scored, with an optimize mode that keeps improving the best
   verified score.
2. **Puts results from the collection to work.** Four applications in which a theorem from
   the collection changes an engineering decision today. Each produces its output and an
   evidence report.
3. **Maps the rest.** It triages all 372 result families by industrial readiness. For
   algorithmic results it provides paper-to-code kits that check a model's transcription of a
   paper's algorithm against an exact oracle.

Every statement the harness makes carries an **evidence tier**. A model can never raise a
tier; only a check that ran can.

## Quick start

```sh
cd harness
pip install -e '.[all]'     # the core is standard-library only; numpy speeds search and is needed
                            # for maxcut; anthropic is needed for the Claude provider
cd ..                       # qed finds the collection from the working directory (or --repo / QED_REPO)

qed map                                          # industrial map of the curated families
qed app pulse-code --length 31                   # radar / sync code with a proven-optimal PSL
qed app crossbar --m 8 --n 12 --out report/      # crossing-optimal layout, report and SVG
qed app null-model --demo                        # does clustering exceed what degrees explain?
qed app maxcut --demo                            # a cut with a certified optimality gap
qed kit check three-machine                      # the kit rejects a classical heuristic

# The model loop. Offline, with hand-written scripted replays:
qed solve harness/problems/psl2-length-28.toml --provider scripted:harness/problems/replays/psl2-length-28.json
# Live, with Claude (credentials from ANTHROPIC_API_KEY or an `ant auth login` profile):
qed solve harness/problems/low-psl-code-64.toml --provider anthropic:claude-opus-5-5@high --exec --rounds 4

python -m unittest discover -s harness/tests     # 54 tests, about 10 seconds
```

## Evidence tiers

| Tier | Meaning |
| --- | --- |
| `verified` | Checked in this run by a deterministic checker: exact computation, a trusted checker, or a Lean/Comparator run that passed |
| `formalized` | The collection ships a Lean statement and a Comparator configuration for it. It was not re-checked in this run, and the collection's own review status is `unchecked` |
| `published` | Stated in a manuscript of the collection or in the classical literature, without a formalization |
| `empirical` | Supported by measurements in this run: sampling, tests on generated instances, convergence diagnostics. Not a proof |
| `asserted` | Claimed by a model and not independently checked |
| `unknown` | Not established |

A conclusion is only as strong as its weakest support. When an application cites a theorem,
it uses the tier the collection actually supports: `formalized` only when the specific
Comparator challenge exists, and `published` otherwise. `qed verify <family>` runs
Comparator where Lean, `comparator`, `landrun` and `lean4export` are installed. A pass
upgrades the theorem to `verified` for anyone who depends on it.

`--require TIER` makes any app exit with status 2 when one of its conclusions falls below
that tier, so a CI job can refuse to ship a decision without enough evidence behind it.

## Applications

| App | Families | Problem | What the theorem changes |
| --- | --- | --- | --- |
| `pulse-code` | 179, 076 | Binary codes with low autocorrelation sidelobes for radar and sonar pulse compression, synchronisation words and preambles | Barker codes stop at length 13, so above it PSL 2 is the floor. The app searches for codes, proves PSL lower bounds by exhaustive branch and bound where that fits the budget, and otherwise cites the theorem. Merit factors have no absolute ceiling (076, asymptotic) |
| `crossbar` | 165 | Single-layer wiring of m sources to n sinks: crossbars, bus meshes, brickyards | Z(m, n) is the exact minimum number of crossings, and so of jumpers. The app emits a layout that attains it, checked with exact integer geometry, and an SVG |
| `null-model` | 131 | Is a network's clustering more than its degree sequence explains? Fraud and AML rings, security graphs, supply chains | The explicit mixing bound `switch_chain_tv_bound` gives a certified step count for the exact formal chain (`--chain theorem --certify-tv`), affordable on small graphs. The fast edge-swap default is judged by R-hat diagnostics and labelled `empirical`. The app also ranks the most over-clustered nodes |
| `maxcut` | 102 | Max-Cut / QUBO for VLSI, spin glasses and quantum-hardware baselines | Beating the Goemans–Williamson ratio on every instance is NP-hard, so the useful guarantee is per instance. The app returns a cut together with an SDP dual bound, built with an explicit floating-point margin |

Example reports, generated with fixed seeds, are in [`docs/examples/`](docs/examples/):

- **`pulse-code-31`:** PSL 3. Exhaustive search proves no length-31 code has PSL 2, so the
  code is PSL-optimal (`verified`).
- **`pulse-code-64`:** PSL 4 in 20 s. Exhaustive search rules out Barker codes at length 64.
  Whether PSL 3 is achievable stays `unknown` within the budget.
- **`crossbar-8x12`:** 360 crossings, equal to Z(8, 12). Optimality is `formalized`.
- **`null-model-demo`:** 114 triangles against 60 ± 8 under the null (z ≈ 6.8). All 10
  top-flagged nodes belong to the planted ring.
- **`maxcut-demo`:** the cut is certified to be at least 94% of the maximum.

## The solve loop

```
problem.toml ─┐
related results from the catalogue (with tiers) ─┼─► N parallel attempts (diverse strategies)
source papers (LaTeX, from the collection) ──────┘            │
                                                               ▼
              trusted checks: expected answer · checker · kit oracle · Lean + axiom audit
              soft check: model referee (ranks attempts; never raises a tier)
                                                               │
              target tier reached? ── yes ──► report.md / report.json
                     │ no (or optimize mode)
                     └──► feedback: counterexamples, failing instances, best score ──► next round
```

| Kind | The model returns | Checked by |
| --- | --- | --- |
| `compute` | a final `ANSWER:` line | `expected`, or `checker`. Without either, self-consistency is recorded but the answer stays `asserted` |
| `construct` | JSON, or a Python `construct()` program run with `--exec` | `checker`, which may also return a score (`optimize = true`) |
| `prove` | a proof; with `[lean]`, a tactic proof of a fixed statement | Lean compile plus `#print axioms` (with `--exec`), screened for `sorry`, `axiom`, `set_option`, `native_decide` and metaprogramming. Otherwise a model referee, which leaves the proof `asserted` |
| `implement` | a Python module | a kit's exact oracle on generated and adversarial instances, which can reach `empirical` |

- **Providers.** `anthropic[:model[@effort]]` uses the official SDK: Claude Opus 5.5 by
  default at `high` effort, adaptive thinking, streaming, and the server-side refusal
  fallback. `openai-compat:<url>#<model>` reaches an open-weight prover behind a vLLM-style
  server. `scripted:<file.json>` replays fixed responses. `--critic` adds a referee model,
  so a run can pair a general reasoning model with a specialised one.
- **Authority.** Model-written code and Lean run only with `--exec`, in a child process with
  CPU, memory, file-size and file-descriptor limits. That limits accidents; it is not a
  security boundary.
- **Run records.** `runs/<time>-<problem>/` holds `attempts.jsonl` (every prompt, response
  and verdict), `report.md`, `report.json` and `training.jsonl`. The training file stores
  prompt and response pairs with rewards taken from verifier outcomes, ready for
  rejection-sampling fine-tuning or RL with verifiable rewards.

Example problems are in [`problems/`](problems/): a constructive code with a trusted
checker, an open-ended code-design task in optimize mode, two paper-to-code transcriptions, a
computation with a reference answer, and a Lean target. Each file in
[`problems/replays/`](problems/replays/) is a set of hand-written scripted responses for
offline runs. None of them is model output, and each file says so.

## Paper-to-code kits

Several results in the collection are algorithms that are intricate enough to need careful
transcription. A kit makes a transcription checkable.

| Kit | Family | Oracle | Notes |
| --- | --- | --- | --- |
| `three-machine` | 124 | exact minimum makespan by dynamic programming over completed-job sets | Random DAGs almost never separate list-scheduling heuristics from the optimum. The kit therefore pins adversarial instances, found by hill-climbing, that defeat highest-level-first, Coffman–Graham and most-successors rules, and relabels them at random on every run |
| `superstring` | 128 | exact shortest superstring (Held–Karp) | Checks containment and length ≤ 2·OPT. The classical greedy passes these instances even though its factor-2 guarantee is unproven, which shows why kit agreement is only `empirical` |

A kit checks a stated guarantee on instances. It does not check fidelity to the paper's
algorithm or its running time, and the reports say so.

## Industrial map

`qed map --markdown` generates [`docs/industrial-map.md`](docs/industrial-map.md). Of 372
families:

- 5 are deployed here (R3);
- 11 have explicit algorithms worth transcribing (R2);
- 12 settle a limit or guarantee that changes an engineering decision (R1);
- the rest are research for now (R0).

13 uncurated families whose summaries mention algorithms or sampling are listed as
candidates for the next kits. Each curated entry gives the sectors, the "industrial reading"
(the harness's interpretation, not a claim of the manuscripts) and the caveat that limits it.
Examples of such caveats: the galactic constants of the new multiplication exponents, and
the fact that Thorp-shuffle mixing is not a cipher security proof.

## What was borrowed, and from where

- **The collection's own process.** Many attempts per problem with substantial test-time
  compute, aggregation of outputs into families, results built on earlier ones, and formal
  checking with Comparator under a fixed list of permitted axioms. This led to parallel
  attempts, retrieval of related results with their tiers, and the Lean gate with its axiom
  audit.
- **Generate-and-verify systems such as AlphaEvolve and FunSearch.** Programs as candidates,
  scored by trusted evaluators, with the best result fed back.
- **REA, the sibling repository.** Claims distinguish what was observed, derived, inferred
  or left unknown. Authority fails closed: nothing runs without explicit permission.
  Deliverables are reports whose exit status can gate CI.

## Limits of this version

- No model API was called while building this. The loop is exercised end to end with
  scripted replays. The Anthropic provider follows the SDK 2.1 interface but has not yet run
  against the live API.
- Lean is not installed in the environment used to build it. The Lean and Comparator checks
  are implemented, and their screening, failure paths and output parsing are tested, but no
  proof has been compiled through them yet.
- Theorems cited as `formalized` were not re-checked here, and the collection marks its
  formalizations' review status `unchecked`.
- The apps are prototypes. Dedicated long searches report lower PSL values at longer
  lengths. Certified null-model sampling only fits small graphs. The dense Max-Cut
  certificate is limited to 4000 vertices.

## Extending

- **App:** add `qed/apps/<name>.py` returning an `AppResult`, cite theorems with
  `family_claim(...)`, then register it in `qed/apps/__init__.py` and `qed/cli.py`.
- **Kit:** add `qed/kits/<name>.py` with `NAME`, `FAMILY`, `ENTRYPOINT`, `INTERFACE`,
  `instances`, `oracle`, `check` and `baseline`, plus `problems/<name>.toml`. If random
  instances do not separate plausible wrong algorithms, add adversarial ones.
- **Problem:** write a TOML file. The fields are documented in `qed/solve/problem.py`.

```
harness/
  qed/
    evidence.py      tiers, claims, weakest-link conclusions
    catalog.py       CONTENTS.md, overview.tex, lean/docs, Comparator configs, formalization.yaml
    search.py        BM25 over families
    industry.py      curated registry and triage of all families
    llm/             anthropic (SDK), openai-compat, scripted providers
    solve/           problem specs, engine, verifiers, sandbox, Lean gate, reports
    kits/            paper-to-code oracles (124, 128)
    apps/            pulse-code, crossbar, null-model, maxcut
    cli.py
  problems/          example problem files, checkers and labelled replays
  docs/              industrial map and example reports
  tests/
```
