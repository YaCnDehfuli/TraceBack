# Memory experiment

## Raw counts per arm

| | off | placebo | real |
|---|---|---|---|
| valid runs | 9/9 | 9/9 | 9/9 |
| verified on attempt 1 | 0/9 | 0/9 | 9/9 |
| verified at all | 9/9 | 9/9 | 9/9 |
| attempts per run | 2, 2, 2, 2, 2, 2, 2, 2, 2 | 2, 2, 2, 2, 2, 2, 2, 2, 2 | 1, 1, 1, 1, 1, 1, 1, 1, 1 |
| tool calls per run | 5, 5, 5, 5, 5, 5, 5, 5, 5 | 6, 5, 5, 5, 5, 5, 6, 5, 5 | 4, 4, 4, 4, 4, 4, 4, 4, 4 |

27 runs: cases B, B2, B3 x off / placebo / real x 3 repeats, claude-sonnet-5-5, equal budgets, one throwaway Atlas database per run, main `45afa59`. Raw counts, no rates claimed. Full method and every run: `evals/results/results.md`.
