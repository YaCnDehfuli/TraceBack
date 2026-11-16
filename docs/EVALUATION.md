# Does the memory change what the agent does?

A memory system is easy to demo and easy to fool yourself with: put anything relevant in the prompt
and the agent often looks smarter. This experiment separates "the memory carried the right
knowledge" from "the prompt got longer". The generated report with every run is
[`evals/results/results.md`](../evals/results/results.md).

## Design

**Cases.** B, B2 and B3 are the same bug as case A, the one the memory was earned on, but reported
in different words and with the faulty insert in a different place: a renamed handler, a helper
function, a collection held in a variable. The fix needs the Payments team's reconciliation rule
(`ledger.mark_replayed`), which lives only in an operations document inside the app.

**Arms.** Each case runs under three arms:

| Arm | What the agent gets |
|---|---|
| `off` | No memory |
| `placebo` | One unrelated memory (an export timeout, a token clock skew, accented search terms, or large photo uploads crashing a media service), injected through the same prompt block as a real memory |
| `real` | Normal recall, with only case A's earned memory in the database |

The placebos are length-matched on what reaches the prompt: the confirmed cause and resolution, the
proven fix, and their total are each within 0.85–1.15 of the real memory's length. Each placebo is
also checked to contain none of the real bug's vocabulary.

**Isolation.** Every run gets its own throwaway Atlas database, created with the same setup script
as production, seeded (for `real`) by verifying case A's reference fix with the real runner and
promoting it through the memory service, and dropped afterwards. Runs go through the public API in
their own process with the real runner and Atlas required (no fallback to fakes) and memory
promotion turned off, so no run's renewals, disputes or new memories can reach another run.

**Fairness.** Same model (`claude-sonnet-5-5`), same prompt version, same budget (8 tool calls, 2 fix
attempts, 120 seconds) for every run. The report records the code, fixture and test-suite revisions
and refuses to call a run clean if any of them had uncommitted changes.

**Scoring.** Only facts from the run's event stream count: the runner's verification results, the
attempt numbers, the tool calls and the final outcome, compared against each case's hidden
`labels.json`. A run where the arm's condition did not hold (for example, a placebo that wasn't
injected) is marked invalid and listed, never counted. The headline metric is **verified on the
first attempt**, reported as raw counts.

## Results

27 runs on revision `45afa59`, 3 per case and arm:

| | off | placebo | real |
|---|---:|---:|---:|
| valid runs | 9/9 | 9/9 | 9/9 |
| **verified on the first attempt** | **0/9** | **0/9** | **9/9** |
| verified at all | 9/9 | 9/9 | 9/9 |
| attempts per run | 2 in every run | 2 in every run | 1 in every run |
| tool calls per run | 5 | 5–6 | 4 |

Every `off` and `placebo` run shipped the generic duplicate-key fix first, failed
`test_replay_recorded_for_reconciliation`, read the failure, and fixed it on the second attempt.
Every `real` run applied the remembered rule and passed on the first. The placebo behaved exactly
like no memory, so the effect comes from the memory's content rather than from extra prompt text.

## The look-alike

Case C has the same error code and endpoint, but its unique index is on `customer_id`. Two runs with
the real memory and two without (one throwaway database each, after the trusted tests were
strengthened): **4/4 escalated** to a human, nothing verified, nothing saved. In both real-memory
runs the memory was recalled and refused by its conditions before the LLM was called.
[Case C runs](../evals/results/case_c/README.md)

## Recall separation

The text that recall embeds was itself measured. With the reporter's free text included, a
look-alike outranked two true repeats. Built from parsed facts only, every true repeat scores above
every look-alike and every distractor (0.952 against 0.927–0.939 and at most 0.778).
`scripts/embed_separation.py` reruns the comparison against Voyage without touching the database.

## What this does and doesn't show

- It shows the mechanism works on one bug family: a proven, team-scoped memory carried a rule the
  model could not otherwise know, and the agent used it.
- All three cases are variants of the bug the memory came from. Nothing here says the approach
  generalises to other bugs.
- N=3 per case and arm. We report counts, not rates or significance.
- The incidents are synthetic; the errors are real MongoDB errors and the tests really run.

## Reproduce

```bash
uv run python -m evals.run_ablation --dry-run                                 # the plan and the placebo checks
uv run python -m evals.run_ablation --cases B B2 B3 --arms off placebo real --repeats 3
```

The full run needs Atlas, Voyage, an Anthropic key and the local practice-app database, and writes
`evals/results/results.md` and `results.json`.
