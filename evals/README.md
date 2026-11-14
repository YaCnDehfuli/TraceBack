# evals (owner: P1, P1-9)

The placebo experiment (plan R10): cases B, B2, B3 × memory `off` / `placebo` / `real` = 9 runs.

- `placebo_memories.json`: unrelated memories of the same length, injected through the same code path.
- `run_ablation.py`: runs everything, scores against `cases/*/labels.json`, writes `results/results.md`.
- Headline metric: **verified on the first attempt**. Report raw counts ("3 of 3"), never only percentages.
