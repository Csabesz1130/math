# Crossing-optimal layout of K_{8,12}

- K_{8,12}: 360 crossings, equal to the proven minimum Z(8, 12) = 360
- 8 sources on the x-axis, 12 sinks on the y-axis, straight edges

### Conclusions

- **This layout is crossing-optimal: 360 is the minimum number of jumpers for a single-layer K_{8,12}** — `formalized`
  - weakest support: Every drawing of K_{8,12} with continuous edges has at least Z(8, 12) crossings

### Evidence

| Tier | Claim | Source | Limitations |
| --- | --- | --- | --- |
| `verified` | This straight-line drawing of K_{8,12} has exactly 360 crossings, at 360 distinct points (no three edges concurrent) | check: crossbar.count_crossings (exact integer orientation tests) | — |
| `verified` | Z(8, 12) = 360 | check: crossbar.zarankiewicz | — |
| `formalized` | Every drawing of K_{8,12} with continuous edges has at least Z(8, 12) crossings | family: 165; comparator: lean/ComparatorChallenges/BipartiteCrossing.json | formalization review status: unchecked; not re-checked in this run (`qed verify 165` runs Comparator where Lean is installed) |

Tiers: `verified` = checked in this run by a deterministic checker; `formalized` = Lean statement and Comparator config in this repository; not re-checked here; `published` = stated in a manuscript or the classical literature; no formalization used; `empirical` = supported by measurements in this run; not a proof; `asserted` = claimed by a model; not independently checked; `unknown` = not established.

## Outputs

```json
{
  "m": 8,
  "n": 12,
  "crossings": 360,
  "lower_bound": 360,
  "sources": [
    [
      -7910,
      0
    ],
    [
      -3446,
      0
    ],
    [
      -2122,
      0
    ],
    [
      -332,
      0
    ],
    [
      3156,
      0
    ],
    [
      6210,
      0
    ],
    [
      6918,
      0
    ],
    [
      7293,
      0
    ]
  ],
  "sinks": [
    [
      0,
      -9559
    ],
    [
      0,
      -8269
    ],
    [
      0,
      -4618
    ],
    [
      0,
      -3579
    ],
    [
      0,
      -2290
    ],
    [
      0,
      -2282
    ],
    [
      0,
      4970
    ],
    [
      0,
      5867
    ],
    [
      0,
      6635
    ],
    [
      0,
      7809
    ],
    [
      0,
      7962
    ],
    [
      0,
      8377
    ]
  ],
  "edges": "every source joined to every sink by a straight segment"
}
```
