"""Voyage embeddings through Atlas AI Model APIs.

POST {VOYAGE_BASE_URL}/embeddings  with  Authorization: Bearer {VOYAGE_API_KEY}
body: {"input": [...], "model": EMBEDDING_MODEL, "input_type": "document" | "query"}
Use "document" for memories being stored and "query" for incident observations.
Result vectors must have EMBEDDING_DIMENSIONS (1024) numbers to match the vector index.

FAKE_EMBEDDINGS=1 (environment variable) gives deterministic vectors with no network call,
for offline tests. Never use it on traceback_demo.
"""

from __future__ import annotations

import hashlib
import math
import os
import random
import time
from typing import Literal

import httpx

from core.config import get_settings

InputType = Literal["document", "query"]


class EmbeddingError(RuntimeError):
    pass


def _fake(text: str, dims: int) -> list[float]:
    # Bag of words hashed into buckets, so similar texts get similar vectors.
    vec = [0.0] * dims
    for word in text.lower().split():
        vec[int(hashlib.sha256(word.encode()).hexdigest(), 16) % dims] += 1.0
    if not any(vec):
        vec[0] = 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec]


def embed(texts: list[str], input_type: InputType) -> list[list[float]]:
    s = get_settings()
    if os.getenv("FAKE_EMBEDDINGS") == "1":
        return [_fake(t, s.embedding_dimensions) for t in texts]

    key = s.voyage_api_key.get_secret_value()
    if not key:
        raise EmbeddingError("VOYAGE_API_KEY is not set.")
    body = {"input": texts, "model": s.embedding_model, "input_type": input_type}

    last: Exception | None = None
    for attempt in range(4):
        try:
            r = httpx.post(
                f"{s.voyage_base_url.rstrip('/')}/embeddings",
                json=body,
                headers={"Authorization": f"Bearer {key}"},
                timeout=20,
            )
            if r.status_code == 429 or r.status_code >= 500:
                raise EmbeddingError(f"Voyage {r.status_code}: {r.text[:200]}")
            r.raise_for_status()
            vectors = [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
            if any(len(v) != s.embedding_dimensions for v in vectors):
                raise EmbeddingError(f"expected {s.embedding_dimensions} dims, got {len(vectors[0])}")
            return vectors
        except (httpx.HTTPError, EmbeddingError) as e:
            last = e
            time.sleep(0.5 * 2**attempt + random.random() * 0.2)
    raise EmbeddingError(f"embedding failed after retries: {last}")


def embed_one(text: str, input_type: InputType) -> list[float]:
    return embed([text], input_type)[0]
