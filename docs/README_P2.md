<!-- P2's README section. Paste into README.md at 15:45 (merge order: P2, P3, P1). Describe only what is merged. -->

## Memory you can govern (P2)

Everything here was built on Saturday, November 14, 2026, at Agents in Context Toronto, on the event's **MongoDB Atlas Hackathon Sandbox** (Cluster0, M10, MongoDB 9.0.7).

A memory in Traceback is **one proven fix**: what the incident looked like, why it happened, the fix, the conditions under which it applies, and the proof that it worked. Memories live only in the `memories` collection, are searched with **Atlas Vector Search**, and every action on them is written to an append-only `memory_audit` collection. All of it is in `memory/` (the only code allowed to write memories), `scripts/atlas_setup.py` and `scripts/seed_demo.py`.

### The rules, and what enforces each

| Rule | Enforced by |
| --- | --- |
| **Only proven fixes become memories.** The fix must have failed before and passed after, under the trusted tests. | The **Atlas `$jsonSchema` validator** on `memories` (`validationAction: "error"`): `verification.status` must be `passed`, `beforeFailed` and `afterPassed` must be `true`. `promote()` has no Python pre-check on purpose: the database is the gate. The app's own database user (`readWrite`) cannot change the validator, so the app can't switch the check off. |
| **Every memory belongs to a team; only that team can find it.** | A pre-filter **inside `$vectorSearch`** (`tenantId`, `readableBy`, `status: "active"`, `expiresAt > now`, `embeddingVersion`), so other teams' memories are never even candidates. Every hit is then **re-read** with the same filter before use (protects against index lag). |
| **Memories expire.** | Each memory gets `expiresAt` from its team's policy (demo: 24 h, at most 48 h from creation). A verified reuse renews it, capped at the maximum. A **TTL index** on `purgeAt` deletes it after a 10-minute grace. |
| **Corrections never overwrite.** | `correct()` retires the current version (`superseded`) and adds the next one; both stay in the lineage, and recall only ever returns the active one. |
| **Forgetting is complete.** | `forget()` hard-deletes **every version** and leaves a tombstone with no content. Audit hashes are HMACs keyed by a secret stored inside the memory, so once it's deleted they can't be linked to any content. |
| **Everything is logged.** | `memory_audit`: `promoted`, `retrieved`, `viewed`, `used`, `renewed`, `near_miss`, `disputed`, `corrected`, `expired_now`, `forgotten`, `refused`, `index_lag_dropped`. Events never contain memory text. |

### The life of a memory

1. **Earn.** A run verifies a fix; `promote()` stores it. If verification failed, Atlas refuses the write: **"Memory refused: no proof."** (shown on screen with the failing test).
2. **Recall.** A new incident is embedded (`voyage-4-lite`, `input_type="query"`) and searched with the team filter, plus an exact lookup on error code and operation. Each hit is re-read before it is used.
3. **Use or refuse.** The agent checks the memory's two conditions in code. Conditions false → `near_miss` (the memory stays active). Used and verified → `renewed`. Conditions held but the fix failed → `disputed` (paused, no longer recalled). The store decides; a run in flight can never undo an admin's expire or a dispute.
4. **Correct, expire or forget.** Only an admin of the owner team, always with a reason.
5. **Stale.** Each memory records a fingerprint of the files its fix touched, as they were when it was proven. If the code changes, the card shows **"Stale: code changed since this was proven"** within 5 seconds. Stale is a warning: the fix must still pass verification.

### Why vector search, with so few memories?

The demo database holds the earned memory plus **20 labelled distractor memories** across both teams (other bug families, `seeded: true`), including deliberate near misses: a webhook signature failure, a webhook relay timeout, a missing index. Recall drops vector hits below a **score cutoff of 0.83**, measured with `voyage-4-lite` against every case's real recall query:

| | Score |
| --- | --- |
| Real memory, cases A, B, B2, B3, C, D, P | 0.899–0.945 |
| Real memory, the generic Fence query | 0.867 |
| **Best distractor, any case** | **0.791** |

Exact signature matches bypass the cutoff, so a look-alike (case C) is still found and then refused by its conditions. `tests/memory/test_distractors.py` re-checks the separation for every case.

### What you see on screen (`web/memory.js`)

- **The memory card:** owner team, "Visible to: Payments only", the proof, the conditions as ✓/✗ for this incident, a live expiry bar, and "match: strong/weak" (never a raw score).
- **Fence:** the same search under each team's key: "Payments sees 1 / Platform sees 0", what Platform's search would return without the team filter (struck through, and redacted by the API), and the `$vectorSearch` filter printed underneath.
- **The admin drawer** (only under an admin key of the owner team): Expire now, Forget, Correct, History. After Forget, the card's lines are blacked out under a VOID stamp, and "Recall: 0 candidates · unsearchable".
- **The refusal receipt:** "Memory refused: no proof.", the failing test, "Nothing was stored", REFUSED stamp.

### Memory API

All routes take `X-API-Key` and are scoped to the caller's team. A memory of another team answers 404, the same as one that doesn't exist, so ids can't be probed.

| Route | Who | What |
| --- | --- | --- |
| `GET /memories`, `GET /memories/{id}` | engineer | The team's memory cards |
| `GET /memories/search?q=` | engineer | Same scoped search as recall, plus the filter that ran |
| `GET /memories/compare-unscoped?q=` | admin | What the search would return without the team filter; other teams' hits redacted. Never given to the agent |
| `GET /memories/{id}/stale` | engineer | `{stale, changedFiles}` |
| `GET /memories/refusals` | engineer | Writes Atlas refused for the team |
| `GET /memories/{id}/audit` | admin, owner team | The lineage's full history ("who read memory X?"), also after Forget |
| `POST /memories/{id}/correct` | admin, owner team | Body `{excludes, reason}`: the next version supersedes this one |
| `POST /memories/{id}/expire` | admin, owner team | Body `{reason}` |
| `DELETE /memories/{id}` | admin, owner team | Body `{reason}`: forget for good |

### Setup and tests

```bash
uv run python scripts/atlas_setup.py --all                  # collections, validator, indexes, vector index; safe to rerun
uv run python scripts/seed_demo.py --db traceback_demo --reset            # policies, Earn memory, canary, 20 distractors
uv run python scripts/seed_demo.py --db traceback_demo --poison --no-earn  # a real "Memory refused: no proof"
uv run pytest -m atlas tests/memory                          # 37 tests against live Atlas
```

The Earn memory is created the way a real run creates it: case A's reference fix is verified by the real runner, then promoted. If the runner can't run, the script fails instead of faking proof. Seeded data (the canary, the distractors) is always labelled `seeded: true`.

### Honest limits

- **Demo identities, not real authentication.** API keys map to a team and role from `.env`.
- **The audit log is append-only by convention**, not yet by a database role (`audit_writer` was a stretch goal).
- **TTL purges don't write audit events.** The scheduled deletion (`expiresAt`, `purgeAt`) is recorded when the memory is created.
- **Corrections don't reach the agent yet.** They narrow `excludes` and are versioned and audited, but the agent only checks the two coded conditions.
- **Not built:** sharing a memory with another team, revoking, and resolving a dispute (a disputed memory is paused automatically, but there is no restore button).
- Staleness checks files in this checkout (`fixture_app/`), not a live repository.
