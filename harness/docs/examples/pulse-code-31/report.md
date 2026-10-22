# Low-sidelobe binary code, length 31

- Length 31: PSL 3, ISL 67, merit factor 7.172
- Code (+1 → 1): 1010101101101100111001111110000

### Conclusions

- **This length-31 code has PSL 3 and merit factor 7.172** — `verified`
  - weakest support: The code has PSL 3, ISL 67 and merit factor 7.172
- **No length-31 code has a lower PSL: this code is PSL-optimal** — `verified`
  - weakest support: The code has PSL 3, ISL 67 and merit factor 7.172
  - weakest support: Every length-31 sequence has PSL at least 3 (exhaustive search)
- **Searching for a length-31 Barker code is futile** — `verified`
  - weakest support: No length-31 binary sequence has every sidelobe at most 1 (exhaustive search)

### Evidence

| Tier | Claim | Source | Limitations |
| --- | --- | --- | --- |
| `verified` | No length-31 binary sequence has every sidelobe at most 1 (exhaustive search) | check: pulse-codes.exhaustive_psl | — |
| `verified` | The code has PSL 3, ISL 67 and merit factor 7.172 | check: pulse-codes.autocorrelations | — |
| `verified` | Every length-31 sequence has PSL at least 3 (exhaustive search) | check: pulse-codes.exhaustive_psl | — |
| `formalized` | The largest merit factor at length N tends to infinity (Turyn's bounded-merit-factor conjecture is false) | family: 076; comparator: lean/ComparatorChallenges/AsymptoticallyMinimalLittlewood.json | asymptotic: gives no construction or rate at this length; formalization review status: unchecked; not re-checked in this run (`qed verify 076` runs Comparator where Lean is installed) |

Tiers: `verified` = checked in this run by a deterministic checker; `formalized` = Lean statement and Comparator config in this repository; not re-checked here; `published` = stated in a manuscript or the classical literature; no formalization used; `empirical` = supported by measurements in this run; not a proof; `asserted` = claimed by a model; not independently checked; `unknown` = not established.

## Outputs

```json
{
  "length": 31,
  "objective": "psl",
  "sequence": [
    1,
    -1,
    1,
    -1,
    1,
    -1,
    1,
    1,
    -1,
    1,
    1,
    -1,
    1,
    1,
    -1,
    -1,
    1,
    1,
    1,
    -1,
    -1,
    1,
    1,
    1,
    1,
    1,
    1,
    -1,
    -1,
    -1,
    -1
  ],
  "bits": "1010101101101100111001111110000",
  "psl": 3,
  "isl": 67,
  "merit_factor": 7.171642,
  "autocorrelations": [
    0,
    -1,
    0,
    -1,
    -2,
    -1,
    -2,
    1,
    2,
    1,
    -2,
    1,
    0,
    3,
    0,
    3,
    0,
    -1,
    2,
    -3,
    -2,
    1,
    -2,
    1,
    0,
    1,
    0,
    -1,
    0,
    -1
  ],
  "search": {
    "method": "tabu search (5s, seed 0)",
    "psl1_exhaustive": {
      "status": "none",
      "nodes": 1539
    },
    "psl2_exhaustive": {
      "status": "none",
      "nodes": 161115
    }
  }
}
```
