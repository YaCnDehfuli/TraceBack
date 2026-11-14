"""Shared API dependencies: where runs are stored and what the agent runs with.

Built once, on first use. Tests override get_repo and get_agent_deps with in-memory versions.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException, status

from api.runs import AgentDeps, MemoryRunRepo, MongoRunRepo, RunRepo


@lru_cache
def get_repo() -> RunRepo:
    try:
        return MongoRunRepo()
    except RuntimeError as e:  # Atlas not configured: keep the API usable, say so in the log
        print(f"[api] runs are kept in memory only: {e}")
        return MemoryRunRepo()


@lru_cache
def _agent_deps() -> AgentDeps:
    """Built once per process. AGENT_RUNNER / AGENT_STORE = auto falls back to the fakes (and says so in the
    log); local / atlas refuse to start instead, so an experiment can never silently run on fakes."""
    from agent.llm import get_llm
    from agent.run import git_revision, pick_runner, pick_store
    from core.config import get_settings

    s = get_settings()
    llm = get_llm()  # raises RuntimeError if LLM_API_KEY / LLM_MODEL are missing
    if s.agent_runner == "local":
        _require_fixture_db()
    try:
        runner, runner_name = pick_runner(s.agent_runner)
        store, store_name = pick_store(s.agent_store, seed=True)
    except SystemExit as e:  # pick_store("atlas") exits the CLI; here it means "not configured"
        raise RuntimeError(str(e)) from None
    print(f"[api] agent: {llm.model} · {runner_name} · {store_name} · promote={s.agent_promote}")
    return AgentDeps(
        runner=runner,
        memory=store,
        llm=llm,
        revision=git_revision(),
        promote=s.agent_promote,
        runner_name=runner_name,
        store_name=store_name,
    )


def _require_fixture_db() -> None:
    from pymongo import MongoClient

    from core.config import get_settings

    try:
        uri = get_settings().fixture_mongodb_uri.get_secret_value()
        MongoClient(uri, serverSelectionTimeoutMS=1500).admin.command("ping")
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"AGENT_RUNNER=local but the fixture database is unreachable ({type(e).__name__})") from None


def get_agent_deps() -> AgentDeps:
    try:
        return _agent_deps()
    except RuntimeError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"The agent isn't configured: {e}") from None
