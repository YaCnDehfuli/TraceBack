**What it does:**

**How I tested it:**

- [ ] Touches only my own folders (or `contracts/` with the other owners' approval)
- [ ] `git status` showed no `.env` and no secrets
- [ ] `uv run pytest -m "not atlas"` passes
- [ ] `uv run python scripts/demo.py` still starts
