# evals

The memory experiment: cases B, B2 and B3 × memory `off` / `placebo` / `real`, each run in its own
throwaway Atlas database. Design and results: [docs/EVALUATION.md](../docs/EVALUATION.md).

- `run_ablation.py`: plans and runs the experiment through the API, scores each run against
  `cases/*/labels.json`, and writes `results/results.md` and `results/results.json`.
- `placebo_memories.json`: unrelated memories, length-matched to the real one on what reaches the prompt.
- `calibrate.py`: repeated no-memory runs of one case, to check the agent can't find the team rule unaided.
- Headline metric: **verified on the first attempt**, reported as raw counts.
