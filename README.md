# Traceback: memory with receipts

An AI debugging agent for small web services whose memory you can govern. It fixes a failing
request, proves the fix with tests, and remembers **only proven fixes**: scoped to the team that
earned them, expiring unless re-proven, correctable, and truly forgettable.

Built at **Agents in Context Toronto** (MongoDB), November 14, 2026, for **Challenge 2: Memory You
Can Govern**. Everything in this repository was built today.

> Status: skeleton. Contracts, fakes, the API shell and the condition checks work; everything else is a
> stub owned by one teammate (see below). This README grows as features merge.

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
| `uv run python scripts/check_env.py` | Checks Atlas, Voyage, the LLM and ElevenLabs settings |
| `uv run python scripts/demo.py` | Starts the API and UI |
| `uv run python scripts/demo_reset.py` | Resets demo data (run before each judging session) |
| `uv run python scripts/atlas_setup.py --db traceback_p1` | Creates collections and indexes in one database |
| `uv run python -m agent.run --case B --team payments` | One investigation from the command line |

## Layout and owners

| Folder | Owner | What lives there |
| --- | --- | --- |
| `contracts/` | P1 (all approve) | Shared data shapes, interfaces, fakes, sample run events |
| `core/` | P1 | Settings, database client, API-key auth, clock and ids |
| `api/`, `agent/`, `evals/`, `web/voice.js` | P1 | API, agent loop, experiment, voice agent |
| `memory/`, `scripts/atlas_setup.py`, `scripts/seed_demo.py`, `web/memory.js` | P2 | Governed memory on MongoDB Atlas |
| `fixture_app/`, `trusted_tests/`, `runner/`, `cases/`, `web/`, `scripts/demo*.py` | P3 | Practice apps, tests, sandbox, UI, demo |

Never name a Python module `traceback`: it would shadow Python's built-in `traceback` module.

## Docs

- [`docs/PLAN.md`](docs/PLAN.md): the final team plan (priority ladder, owners, demo script). Wins over the guide.
- [`docs/TEAM_GUIDE.md`](docs/TEAM_GUIDE.md): the full design, glossary, setup and memory rules.

## Rules for this repository

- It is public: **never commit `.env`** or any key. Run `git status` before each commit.
- One branch per item (`p1/P1-2-agent-loop`), a PR touching only your folders, one review, squash and merge.
- `main` must always run `uv run python scripts/demo.py`.

## Team

_P1 · P2 · P3: names and GitHub handles go here._
