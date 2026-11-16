# How Traceback was built

Traceback was built in one day by three people at **Agents in Context Toronto** (MongoDB),
November 14, 2026, for **Challenge 2: Memory You Can Govern**: memory that changes what an agent does
next time, with rules for who can read it, how long it lives, and how it is corrected or forgotten.
This document covers the plan, the decisions behind the design, what changed along the way, and how
to work on the code. The system itself is described in [ARCHITECTURE.md](ARCHITECTURE.md).

## Team

| | Owned | Code |
|---|---|---|
| **Yasin Dehfouli** | Agent loop, API, shared contracts, the experiment | `agent/`, `api/`, `core/`, `contracts/`, `evals/` |
| **Elham Razi** | Governed memory on Atlas: schema, recall, governance outcomes, audit, correction, forgetting, staleness | `memory/`, `scripts/atlas_setup.py`, `scripts/seed_demo.py`, `web/memory.js` |
| **Sepehr** | Test world, trusted tests, sandboxed runner, run view, demo tooling | `fixture_app/`, `cases/`, `trusted_tests/`, `runner/`, `web/`, `scripts/demo*.py`, `scripts/live_app.py` |

Each folder had one owner, so three people could merge all day without stepping on each other.
Changes to `contracts/` needed all three to approve.

## How the work was sequenced

**Contracts first.** Before anyone built a feature, the shared shapes were agreed and merged:
the parsed observations of an incident, a memory draft and its two typed conditions, the runner's
verification result (including how much failure detail the agent may see), the run event stream,
and the memory API. Each contract came with an in-memory fake, so the agent could be tested without
Atlas, the UI against recorded events, and the memory service without an LLM.

**A walking skeleton without an LLM.** The first end-to-end path verified a reference fix with the
real runner, promoted it into Atlas, and recalled it as both teams: Payments found one memory,
Platform found none. Earn and Fence worked from a terminal before any model was involved.

**A priority ladder.** Features were then added in an order where every step left a working demo:

1. The real agent: case A fixed by the LLM and promoted; case B recalls it and passes first time
2. The run view and memory card
3. Fence on screen, with a leak test
4. Forget, the tombstone, and the with/without-memory comparison
5. Refuse: the look-alike case
6. Correction with version history and the admin drawer
7. Realistic recall: 20 labelled distractors and a score cutoff
8. The placebo experiment
9. The poisoned-log refusal shown on screen
10. Staleness when the code changes

A feature counted only once it was merged and worked in the demo. A voice interface was planned near
the bottom of the ladder and cut, to keep the time on governance and on the experiment.

## Design decisions

**Make memory necessary.** A capable model fixes a plain duplicate-key bug without help, so a memory
would only add prompt text. The Payments app therefore has a team rule, recording replayed events
with `ledger.mark_replayed`, that appears only in an operations document, and a trusted test for it.
Without memory the agent's first fix fails that test; with it, the fix is right the first time. Early
calibration runs with no memory confirmed the agent did not find the rule on its own.

**Conditions are code, not LLM judgement.** The runner drops its database after every check, so
there is nothing live for a tool to inspect. Instead the `E11000` message is parsed (it names the
index and the duplicate key) and two typed conditions are compared in code. Refusing a look-alike
takes milliseconds and happens before the model is called.

**The database is the proof gate.** `promote()` deliberately has no Python check. The Atlas
`$jsonSchema` validator rejects a memory without passing proof, and the application's database user
cannot change the validator, so no code path in the app can save an unproven fix.

**Correction is core.** The challenge asks for memory that can be corrected, so a correction creates
a new version that supersedes the old one, and both stay in the history.

**Make vector search mean something.** With one or two memories any search looks right, so the demo
database carries 20 labelled distractors, including near misses, and recall applies a score cutoff
tuned against them.

**Forgetting that holds up.** Tombstones carry no content hash. Audit events reference content through
an HMAC keyed by a secret stored in the memory itself, so deleting the memory makes old audit hashes
unlinkable.

**Whole-file fixes.** The agent proposes a complete file for one allowlisted path. That is simpler to
verify and to compare with a remembered fix than a diff.

**Not Atlas Agent Engine.** Its memory SDK documented no delete, update or expiry operations, which
the challenge requires, so the governed memories live in our own collections.

## What changed along the way

- **A weak test let a weak fix in.** The agent's first fix for the look-alike created an index inside
  the request handler and passed. Two trusted tests closed the gap (handlers may not change indexes;
  one record per distinct event). The memory code didn't change: a memory is only as good as the check
  that proves it.
- **The recall text.** Embedding the reporter's own words let a look-alike outrank true repeats,
  because free text shared vocabulary with the trap and varied between real repeats. Recall now
  embeds parsed facts only, and the score cutoff and "strong" threshold were re-measured.
- **Receipts follow the store.** The agent originally reported the outcome it expected. It now reports
  what the memory service actually did, which differs when an admin acted during a run or a memory
  had reached its maximum lifetime.
- **Experiments can't fall back to fakes.** The API can be told to require the real runner and Atlas
  and to never create new memories, and every run records what it ran with. The experiment uses
  these settings and one throwaway database per run.
- **Demo resets.** Resetting the demo now also forgets memories that earlier live runs created, so
  each session starts from the same state.

## How it compares

Agent memory with scoping, expiry, history and deletion already exists: GitHub Copilot Memory keeps
repository-scoped memories that are checked against the current branch and expire unless reinforced;
Zep/Graphiti keeps superseded facts as history; Mem0 filters memories by scope at query time. In each,
a model decides what is saved and whether it still applies. Traceback's claim is narrower: a memory is
admitted only after an external test runner shows the fix turns a failing test into a passing one,
and before reuse, typed conditions from the incident are checked in code.

## Working on the code

**Setup.** Python 3.12 with [uv](https://docs.astral.sh/uv/). Copy `.env.example` to `.env` and fill
in the Atlas connection string, the Voyage key and the Anthropic key. The runner needs a local MongoDB
for the practice apps:

```bash
uv sync
docker run -d --name fixture-mongo -p 27018:27017 mongo
uv run python scripts/check_env.py
uv run python scripts/atlas_setup.py --db traceback_dev   # collections, validator, indexes, vector index
uv run python scripts/seed_demo.py --db traceback_dev --reset
```

**Tests.** Tests that need Atlas are marked `atlas`.

```bash
uv run pytest -m "not atlas"      # no cloud services; what CI runs, with a MongoDB service container
uv run pytest -m atlas            # memory tests against a live Atlas database
uv run ruff check .
```

**Useful entry points.**

| Command | What it does |
|---|---|
| `uv run python -m agent.run --case B --team payments` | One investigation in the terminal (`--memory off\|placebo\|real`, `--runner`, `--store`) |
| `uv run python -m runner reproduce C` | Show that a case's bug is real |
| `uv run python -m runner verify A cases/A/reference/webhooks.py` | Verify a fix without the agent |
| `uv run python scripts/db_trace.py --case B` | Every Atlas command and Voyage call that recall makes, as both teams |
| `uv run python scripts/demo.py` | API and run view on port 8000 |
| `uv run python scripts/live_app.py` | The practice app on port 8100, before and after a verified fix |

**Settings that matter.** `MONGODB_DB` picks the database. `AGENT_RUNNER=local` and
`AGENT_STORE=atlas` make the API refuse to start rather than use fakes; `AGENT_PROMOTE=false` stops
runs from creating memories; `AGENT_MAX_TOOL_CALLS`, `AGENT_MAX_PATCH_ATTEMPTS` and
`AGENT_DEADLINE_SECONDS` set the budget; `MEMORY_MIN_SCORE` overrides the recall cutoff.

**Repository rules.** The repository is public: never commit `.env`. Every change goes through a pull
request; CI runs ruff and the non-Atlas tests on each one. Don't name a module `traceback`, which
would shadow Python's standard library.

## What's next

- Sharing a memory with another team, and revoking it
- More bug families, each with its own error parser and condition fields
- Real authentication in place of the demo keys
- An audit log that is append-only by database role
- Letting an admin's correction change the coded conditions, not only the text the agent sees
- Restoring a disputed memory
