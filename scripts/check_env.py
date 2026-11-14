"""Check that your .env works: Atlas, Voyage embeddings, the LLM, and the ElevenLabs agent id.

    uv run python scripts/check_env.py

Never prints secret values. Exit code 0 = everything required works.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from core.config import Settings, get_settings  # noqa: E402


def check_atlas(s: Settings) -> tuple[bool, str]:
    uri = s.mongodb_uri.get_secret_value()
    if not uri or "<password>" in uri:
        return False, "MONGODB_URI is not set. Ask P2 for the connection string (sent privately)."
    try:
        from pymongo import MongoClient

        client = MongoClient(uri, serverSelectionTimeoutMS=8000, appname="traceback-check")
        client.admin.command("ping")
        names = client[s.mongodb_db].list_collection_names()
        return True, f"ping ok; database '{s.mongodb_db}' has {len(names)} collections"
    except Exception as e:  # noqa: BLE001
        name = type(e).__name__
        if "ServerSelectionTimeout" in name:
            return False, (
                "timed out: add your IP in Atlas > Database & Network Access > IP Access List "
                "(the venue Wi-Fi needs one entry)"
            )
        if "OperationFailure" in name or "Authentication" in str(e):
            return False, "authentication failed: check the user and password (URL-encode @ : / ?)"
        return False, f"{name}: {str(e)[:160]}"


def check_voyage(s: Settings) -> tuple[bool, str]:
    key = s.voyage_api_key.get_secret_value()
    if not key:
        return False, "VOYAGE_API_KEY is not set (Atlas > AI Model APIs > Create model API key)."
    try:
        r = httpx.post(
            f"{s.voyage_base_url.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {key}"},
            json={"input": ["hello"], "model": s.embedding_model, "input_type": "document"},
            timeout=20,
        )
    except httpx.HTTPError as e:
        return False, f"could not reach {s.voyage_base_url}: {type(e).__name__}"
    if r.status_code != 200:
        return False, f"HTTP {r.status_code} from {s.voyage_base_url}: {r.text[:160]}"
    dims = len(r.json()["data"][0]["embedding"])
    if dims != s.embedding_dimensions:
        return False, f"got {dims} dimensions, expected {s.embedding_dimensions}"
    return True, f"{s.embedding_model} returned {dims} dimensions"


def check_llm(s: Settings) -> tuple[bool, str]:
    key = s.llm_api_key.get_secret_value()
    if not key or not s.llm_model:
        return False, "LLM_API_KEY and LLM_MODEL must both be set."
    try:
        if s.llm_provider == "anthropic":
            import anthropic

            reply = anthropic.Anthropic(api_key=key).messages.create(
                model=s.llm_model, max_tokens=16, messages=[{"role": "user", "content": "Reply with OK."}]
            )
            text = "".join(getattr(b, "text", "") for b in reply.content)
        elif s.llm_provider == "openai":
            import openai

            reply = openai.OpenAI(api_key=key).chat.completions.create(
                model=s.llm_model, messages=[{"role": "user", "content": "Reply with OK."}]
            )
            text = reply.choices[0].message.content or ""
        else:
            return False, f"LLM_PROVIDER must be anthropic or openai, not {s.llm_provider!r}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {str(e)[:160]}"
    return True, f"{s.llm_provider}/{s.llm_model} answered: {text.strip()[:40]!r}"


def check_elevenlabs(s: Settings) -> tuple[bool, str]:
    if not s.elevenlabs_agent_id:
        return False, "ELEVENLABS_AGENT_ID is not set (only needed for the voice agent, rung R9)."
    return True, "agent id set"


def main() -> int:
    s = get_settings()
    checks = [
        ("Atlas", check_atlas, True),
        ("Voyage", check_voyage, True),
        ("LLM", check_llm, True),
        ("ElevenLabs", check_elevenlabs, False),
    ]
    ok_required = True
    for name, fn, required in checks:
        ok, msg = fn(s)
        mark = "OK  " if ok else ("FAIL" if required else "SKIP")
        print(f"[{mark}] {name:<10} {msg}")
        ok_required &= ok or not required
    return 0 if ok_required else 1


if __name__ == "__main__":
    raise SystemExit(main())
