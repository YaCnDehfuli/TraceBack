# Traceback: memory with receipts

An AI debugging agent for small web services whose memory you can govern. It fixes a failing
request, proves the fix with tests, and remembers **only proven fixes**: scoped to the team that
earned them, expiring unless re-proven, correctable, and truly forgettable.

Built at **Agents in Context Toronto** (MongoDB), November 14, 2026, for **Challenge 2: Memory You
Can Govern**. Everything in this repository was built today. It was built with AI coding assistants
(Claude Code), and many commits carry a Claude co-author line.

## Status

What is merged on `main`:

- **Earn, Reuse, Refuse, Fence, Forget.** The five verbs below, on MongoDB Atlas with Atlas Vector Search.
- **Correction with history.** An admin can narrow a memory's conditions. Version 2 replaces version 1,
  and both stay in the history.
- **Staleness chip.** A memory is marked Stale when the code it was proven against has changed. It is a
  warning, not a revocation.
- **"Memory refused: no proof."** If a fix did not pass the tests, Atlas refuses the memory write. The
  UI shows that refusal as a receipt.
- **Safe runner.** Every fix is checked in a temporary copy of the practice app, in a separate process,
  with a timeout and no secrets in its environment. Trusted tests decide; the agent never sees them.
- **Run view.** The web UI shows a run step by step, with the identity pill, keyboard shortcuts and a
  with/without memory comparison.
- **Experiment harness.** `evals/run_ablation.py` runs the cases with memory off, with a placebo
  memory and with the real memory.

Not part of this build: **voice**. The voice agent was cancelled. `web/voice.js` is an empty stub, and
the ElevenLabs settings in `.env.example` are unused.

## The five verbs

**Earn** (only a test-proven fix becomes memory) · **Reuse** (a fresh session recalls it and checks
its conditions in code) · **Refuse** (a look-alike bug is not given the remembered fix) · **Fence**
(another team sees nothing, enforced inside the Atlas vector search) · **Forget** (deleted, with a
content-free tombstone).

## Quickstart

```bash
# macOS / Linux:   curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell):   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
git clone https://github.com/YaCnDehfuli/TraceBack.git
cd TraceBack
uv sync
cp .env.example .env          # then fill in the values (sent privately; never commit .env)
uv run python scripts/check_env.py
uv run python scripts/demo.py # http://localhost:8000
```

| Command | What it does |
| --- | --- |
| `uv run pytest -m "not atlas"` | Tests that need no Atlas connection |
| `uv run pytest` | All tests, including Atlas ones |
| `uv run ruff check .` | Lint |
| `uv run python scripts/check_env.py` | Checks Atlas, Voyage and the LLM settings (the ElevenLabs id is optional and unused) |
| `uv run python scripts/demo.py` | Starts the API and UI |
| `uv run python scripts/demo_reset.py` | Resets demo data (run before each judging session) |
| `uv run python scripts/atlas_setup.py --db traceback_p1` | Creates collections and indexes in one database |
| `uv run python -m agent.run --case B --team payments` | One investigation from the command line |

## Layout and owners

| Folder | Owner | What lives there |
| --- | --- | --- |
| `contracts/` | P1 (all approve) | Shared data shapes, interfaces, fakes, sample run events |
| `core/` | P1 | Settings, database client, API-key auth, clock and ids |
| `api/`, `agent/`, `evals/`, `web/voice.js` | P1 | API, agent loop, experiment (`voice.js` is an unused stub) |
| `memory/`, `scripts/atlas_setup.py`, `scripts/seed_demo.py`, `web/memory.js` | P2 | Governed memory on MongoDB Atlas |
| `fixture_app/`, `trusted_tests/`, `runner/`, `cases/`, `web/`, `scripts/demo*.py` | P3 | Practice apps, tests, sandbox, UI, demo |

Never name a Python module `traceback`: it would shadow Python's built-in `traceback` module.

## Docs

- [`docs/PLAN.md`](docs/PLAN.md): the final team plan (priority ladder, owners, demo script). Wins over the guide.
- [`docs/TEAM_GUIDE.md`](docs/TEAM_GUIDE.md): the full design, glossary, setup and memory rules.
- [`docs/DEMO.md`](docs/DEMO.md): the demo guide (presenter's runbook). It still mentions the voice agent, which was cancelled.
- [`docs/README_P2.md`](docs/README_P2.md): governed memory and Atlas.
- [`docs/README_P3.md`](docs/README_P3.md): practice apps, trusted tests, runner and run view.
- [`docs/SUBMISSION.md`](docs/SUBMISSION.md): draft text for the submission form.
- [`evals/results/results.md`](evals/results/results.md): the memory experiment (off, placebo, real). This is a
  **historical** run. It was generated before trusted test 7 and before the code-facts recall change.
  A fresh validation is pending on [#60](https://github.com/YaCnDehfuli/TraceBack/pull/60) (`add769c`).
- [`evals/results/case_c/`](evals/results/case_c/README.md): the look-alike case C after trusted test 7, with and
  without memory. All 4 runs escalated, the right outcome for C, and none saved a fix.

## Rules for this repository

- It is public: **never commit `.env`** or any key. Run `git status` before each commit.
- One branch per item (`p1/P1-2-agent-loop`), a PR touching only your folders, one review, squash and merge.
- `main` must always run `uv run python scripts/demo.py`.

## Team

P1 Yasin (YaCnDehfuli): agent loop and API · P2 Elham (elhamrazi): governed memory and Atlas · P3 Sepehr (SepehrAsh): test world, runner, run view and demo.
