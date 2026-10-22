# Low-sidelobe binary code, length 64

- Length 64: PSL 4, ISL 444, merit factor 4.613
- Code (+1 → 1): 0111111101111110010010011000011011110010000101110010101000111010

### Conclusions

- **This length-64 code has PSL 4 and merit factor 4.613** — `verified`
  - weakest support: The code has PSL 4, ISL 444 and merit factor 4.613
- **This code may not be PSL-optimal: PSL 3 at length 64 is neither achieved nor excluded** — `unknown`
  - weakest support: Whether a length-64 code with PSL 2–3 exists
- **Searching for a length-64 Barker code is futile** — `verified`
  - weakest support: No length-64 binary sequence has every sidelobe at most 1 (exhaustive search)

### Evidence

| Tier | Claim | Source | Limitations |
| --- | --- | --- | --- |
| `verified` | No length-64 binary sequence has every sidelobe at most 1 (exhaustive search) | check: pulse-codes.exhaustive_psl | — |
| `verified` | The code has PSL 4, ISL 444 and merit factor 4.613 | check: pulse-codes.autocorrelations | — |
| `verified` | Every length-64 sequence has PSL at least 2 | check: pulse-codes.exhaustive_psl | — |
| `formalized` | The largest merit factor at length N tends to infinity (Turyn's bounded-merit-factor conjecture is false) | family: 076; comparator: lean/ComparatorChallenges/AsymptoticallyMinimalLittlewood.json | asymptotic: gives no construction or rate at this length; formalization review status: unchecked; not re-checked in this run (`qed verify 076` runs Comparator where Lean is installed) |
| `unknown` | Whether a length-64 code with PSL 2–3 exists | check: pulse-codes.exhaustive_psl | raise --exhaustive-seconds (or --seconds) to settle it |

Tiers: `verified` = checked in this run by a deterministic checker; `formalized` = Lean statement and Comparator config in this repository; not re-checked here; `published` = stated in a manuscript or the classical literature; no formalization used; `empirical` = supported by measurements in this run; not a proof; `asserted` = claimed by a model; not independently checked; `unknown` = not established.

## Outputs

```json
{
  "length": 64,
  "objective": "psl",
  "sequence": [
    -1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    -1,
    1,
    1,
    1,
    1,
    1,
    1,
    -1,
    -1,
    1,
    -1,
    -1,
    1,
    -1,
    -1,
    1,
    1,
    -1,
    -1,
    -1,
    -1,
    1,
    1,
    -1,
    1,
    1,
    1,
    1,
    -1,
    -1,
    1,
    -1,
    -1,
    -1,
    -1,
    1,
    -1,
    1,
    1,
    1,
    -1,
    -1,
    1,
    -1,
    1,
    -1,
    1,
    -1,
    -1,
    -1,
    1,
    1,
    1,
    -1,
    1,
    -1
  ],
  "bits": "0111111101111110010010011000011011110010000101110010101000111010",
  "psl": 4,
  "isl": 444,
  "merit_factor": 4.612613,
  "autocorrelations": [
    3,
    2,
    3,
    2,
    -3,
    0,
    -3,
    2,
    1,
    0,
    -3,
    4,
    1,
    -4,
    1,
    -4,
    -3,
    -4,
    -3,
    0,
    3,
    2,
    1,
    -2,
    -1,
    4,
    -1,
    2,
    3,
    2,
    -3,
    -2,
    -1,
    -2,
    -3,
    2,
    -3,
    -4,
    -3,
    2,
    3,
    2,
    -3,
    -4,
    3,
    -4,
    -1,
    4,
    3,
    -4,
    -1,
    -4,
    3,
    -4,
    3,
    2,
    3,
    0,
    -1,
    -2,
    1,
    -2,
    1
  ],
  "search": {
    "method": "tabu search (20s, seed 0)",
    "psl1_exhaustive": {
      "status": "none",
      "nodes": 178287
    },
    "psl3_exhaustive": {
      "status": "timeout",
      "nodes": 102400
    }
  }
}
```
