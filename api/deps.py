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
    from agent.llm import get_llm
    from agent.run import git_revision, pick_runner, pick_store

    llm = get_llm()  # raises RuntimeError if LLM_API_KEY / LLM_MODEL are missing
    runner, runner_name = pick_runner("auto")
    store, store_name = pick_store("auto", seed=True)
    print(f"[api] agent: {llm.model} · {runner_name} · {store_name}")
    return AgentDeps(runner=runner, memory=store, llm=llm, revision=git_revision())


def get_agent_deps() -> AgentDeps:
    try:
        return _agent_deps()
    except RuntimeError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"The agent isn't configured: {e}") from None
