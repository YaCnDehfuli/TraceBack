# Case C (the look-alike) after #45

Run on main `cbc2926` (trusted tests including `test_handler_does_not_change_indexes`) with:

    uv run python evals/run_ablation.py --cases C --arms real off --repeats 2 --out-dir evals/results/case_c

Two arms only (real, off), N=2 each, one throwaway Atlas database per run, Earn memory seeded for `real`.
Result: 4/4 `escalated` (the label for C), nothing verified or promoted. In both `real` runs the Earn memory
was recalled and not applied (its conditions failed). The generated `results.md` uses the harness's generic
Method wording ("three memory arms"); this run used the two listed above. Reported in #25.
