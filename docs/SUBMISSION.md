<!-- Draft text for the Cerebral Valley submission form. P3 pastes it by hand; nothing here submits anything.
     Every claim below was checked against the code or docs on main at 2150ed0. Re-check the Results section after the 27-run version lands. -->

# Traceback: submission text

Agents in Context Toronto: a MongoDB Hackathon, Saturday, November 14, 2026. Challenge 2: Memory You Can Govern. Submissions are due 17:00.

## 1. Project name and tagline

**Traceback**

**Memory with receipts.** (21 characters)

## 2. Elevator pitch

Traceback is a debugging agent that remembers fixes only after a test run proves them. A new incident recalls the memory from MongoDB Atlas Vector Search, checks in code that the memory's conditions still hold, and reuses the fix, or refuses to. Memories belong to one team, expire, can be corrected, and can be forgotten for good.

## 3. The problem

Teams fix the same incident again and again. The person who solved it last time has moved on, and the fix lives in a chat thread or in nobody's head. An agent with memory could help, but an agent that saves whatever it "learned" has three problems:

- It can save a wrong or poisoned fix, for example from a log line that says "remember this for all teams", and then repeat it.
- It can show one team's memory to another team.
- Once a memory exists, nobody can say who used it, when it should expire, or how to remove it completely.

Challenge 2 asks for memory that changes what the agent does next time, with rules for who can read it, how long it lives, and how it is corrected or forgotten. Traceback is our answer, for one kind of bug (duplicate-key retries in a payment webhook) from end to end.

## 4. What it does

Five beats, each one verb:

- **Earn.** The agent investigates a failing webhook and proposes a fix. A fix becomes a memory only if the trusted tests failed before it and pass after it. If not, Atlas refuses the write ("Memory refused: no proof").
- **Reuse.** A fresh session on a differently worded incident recalls the memory, checks its two typed conditions in code, and applies the fix. The screen highlights the line that came from memory. In our runs the fix passed on the first attempt.
- **Refuse.** A look-alike bug (the unique index is on `customer_id`, not `provider_event_id`) finds the same memory, fails its conditions, and is not given the remembered fix. The agent escalates with evidence.
- **Fence.** Another team's engineer asks the same question and gets nothing. The team filter runs inside the Atlas vector search, so other teams' memories are never candidates.
- **Forget.** An admin of the owning team deletes the memory with a reason. Every version is removed and only a tombstone with no content is left. The rerun then loses the line that came from memory.

## 5. How it's built

- **MongoDB Atlas Vector Search** (`memory/schema.py`, `memory/store.py`). `$vectorSearch` runs with a pre-filter on `tenantId`, `readableBy`, `status: "active"`, `expiresAt > now` and `embeddingVersion`. Every hit is re-read with the same filter before use, to guard against index lag. Exact error-signature matches are merged in.
- **The `$jsonSchema` validator is the proof gate** (`memory/schema.py`, `scripts/atlas_setup.py`). The `memories` collection has `validationAction: "error"`. A memory needs `verification.status == "passed"` with `beforeFailed` and `afterPassed` both true, or Atlas rejects the insert. `promote()` has no Python pre-check, so the database is the gate. The app's database user cannot change the validator.
- **Audit collection** (`memory/audit.py`). Every action is written to `memory_audit` (`promoted`, `retrieved`, `used`, `renewed`, `near_miss`, `disputed`, `corrected`, `forgotten`, `refused` and others), with no memory text in the events. A TTL index on `purgeAt` removes expired memories.
- **Voyage embeddings** (`memory/embeddings.py`). `voyage-4-lite`, called directly, with `document` and `query` input types. Recall has a score cutoff of 0.83, tuned against 20 labelled distractor memories (`tests/memory/test_distractors.py`).
- **FastAPI** (`api/main.py`, `api/routes.py`, `api/runs.py`, `memory/router.py`). Routes take an `X-API-Key` that maps to a team and a role. The run view in `web/` is plain HTML and JavaScript, served by the same app.
- **The safe test runner** (`runner/sandbox.py`). Each check copies the practice app to a temp folder, accepts a whole-file patch to one allowlisted path, runs the trusted tests (`trusted_tests/test_webhooks.py`) on the original code and then on the patched code, in a separate `pytest` process with a timeout and no secrets in its environment. If infrastructure breaks, the result is `inconclusive`, never a pass.
- **The LLM agent loop** (`agent/loop.py`, `agent/llm.py`, `agent/conditions.py`). Parse the error in code, recall, check conditions in code before any LLM call, let the model read and search the app within a tool-call budget, propose a fix, verify it, and then renew, dispute or promote the memory. The model used in the experiment is `claude-sonnet-5-5`.
- **The test world** (`fixture_app/`, `cases/`). Two synthetic FastAPI webhook receivers for two teams, and seven cases (A, B, B2, B3, C, D, P). Payments has a reconciliation rule, `ledger.mark_replayed`, that is written only in an operations document and not in the code. That is why memory is needed: the model knows the generic fix but not this team's rule.

## 6. What makes it different

A memory is written only after an external test runner shows the fix turns a failing test into a passing one, and before reuse, typed conditions from the incident are checked in code. Scoping, expiry, history and deletion exist in other tools (e.g. GitHub Copilot Memory); we don't claim they're new.

## 7. Results

Memory ablation, from `evals/results/results.md` (generated by `evals/run_ablation.py` at 2026-11-14T19:18:19+00:00). Cases B, B2 and B3, each under three arms, N=1 per case and arm. **off**: no memory. **placebo**: one unrelated memory of similar length, injected through the same prompt block. **real**: the proven memory from case A. Each run used its own throwaway Atlas database. Raw counts only; with this N we claim no rates and no significance.

| | off | placebo | real |
|---|---|---|---|
| valid runs | 3/3 | 3/3 | 3/3 |
| INVALID / ERROR runs (not counted) | 0 / 0 | 0 / 0 | 0 / 0 |
| verified on attempt 1 | 0/3 | 0/3 | 3/3 |
| verified at all | 3/3 | 3/3 | 3/3 |
| outcome as labelled (`verified`) | 3/3 | 3/3 | 3/3 |
| attempts per run | 2, 2, 2 | 2, 2, 2 | 1, 1, 1 |
| tool calls per run | 5, 5, 5 | 5, 5, 5 | 4, 4, 4 |
| failing tests on last attempt, per run | 0, 0, 0 | 0, 0, 0 | 0, 0, 0 |
| outcomes | verified 3 | verified 3 | verified 3 |

Note: a fresh 27-run version of this experiment (more runs per case and arm) will replace these counts. [P3: update this section if it lands before submission.]

## 8. Challenges

- **Making memory necessary.** A strong model fixes a plain duplicate-key bug without any memory. So the practice app has a team rule (a replayed event must be recorded with `ledger.mark_replayed`) that appears only in a month-end operations document. Without memory the agent needs a second attempt; with it, one.
- **Weak tests let a weak fix in.** The agent's first fix for the look-alike case C created an index inside the request handler and passed our tests. We closed the gap in the trusted tests (`test_handler_does_not_change_indexes`, and one payment row per event). The memory code did not change. A memory is only as good as the check that proves it.
- **Telling "memory helped" from "more words in the prompt".** The experiment adds a placebo arm: an unrelated memory length-matched to the real one (ratios between 0.85 and 1.15) and injected through the same code path.
- **Vector search with few memories.** With one real memory, any score looks good. We added 20 labelled distractors across both teams, including near misses, and set a score cutoff (0.83) above the best distractor (0.791) and below the weakest real match (0.867 to 0.945 depending on the query).
- **Experiment isolation.** Each experiment run used its own Atlas database so one run's renewals, disputes or promotions could not reach another's.
- **We looked at Atlas Agent Engine and did not use it.** Its memory SDK documented no delete, update or expiry operation, and Challenge 2 requires those. Our governed memories live in our own collections.

## 9. What's next

- Sharing a memory with another team, and revoking it.
- More bug families. Each needs its own error parser and condition fields; the proof gate, team filter, expiry and deletion stay the same.
- Real authentication in place of the demo keys.
- An audit log that is append-only by database role, not only by convention.
- Letting an admin's correction reach the agent's decision. Today it is versioned and audited but the agent checks only the two coded conditions.
- A restore button for disputed memories.

## 10. Honest limits

- **Synthetic incidents.** Two small practice apps and hand-written logs. The `E11000` error is real and the tests really run, but this is not production data.
- **Demo identities, not real authentication.** Four API keys map to a team and role from `.env`. They are fake and local-only.
- **One bug family.** Duplicate-key retries on two apps. The applicability conditions are a fixed typed list (`dup_key_field`, `same_event_id_on_both_deliveries`). We make no claim about other bugs.
- **Proof is only as strong as the tests.** A weak test suite would let a weak fix become a memory. In a real team the gate would be the required CI checks.
- **Small experiment.** Three cases, N=1 per case and arm. All three are variants of the same bug, and the real memory comes from a fix to that same bug. The result shows the mechanism works on this family, not that it generalises.
- **Seeded distractors.** The 20 extra memories that make vector search realistic are labelled `seeded: true`.
- **The audit log is append-only by convention**, not yet by a database role. TTL purges do not write audit events.
- **Corrections do not change the agent's checks yet.** Not built: sharing, revoking, and restoring a disputed memory.
- **Staleness** compares files in this checkout (`fixture_app/`), not a live repository, and it is a warning: the fix must still pass verification.
- **Live runs need the network** (Atlas, Voyage, the LLM). The page itself loads nothing from the internet, and the sample replay (key `0`) is a recording that the page labels "Replay".

## 11. Team

- **P1, Yasin** (GitHub: YaCnDehfuli): agent loop and API.
- **P2, Elham** (GitHub: elhamrazi): governed memory and Atlas.
- **P3, Sepehr** (GitHub: SepehrAsh): test world, runner, UI and demo.

## 12. Links

- Repository: https://github.com/YaCnDehfuli/TraceBack
- Video (1 minute): [PASTE VIDEO LINK HERE]
- Slides: [PASTE SLIDES LINK HERE]

## Short fields

For forms with a length limit. Each is within its limit; the count is given above each block.

**50 characters (49):**

```
Agent memory written only after a test proves it.
```

**150 characters (147):**

```
Debugging agent whose memory is written only after a test proves the fix, then scoped to one team in Atlas Vector Search, expiring and forgettable.
```

**300 characters (291):**

```
Traceback is a debugging agent that saves a fix as memory only after tests show it turns a failing test into a passing one. Memories live in MongoDB Atlas, are searched with Vector Search filtered by team, are checked in code before reuse, expire, and can be corrected or forgotten for good.
```
