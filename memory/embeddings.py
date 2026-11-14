"""Voyage embeddings through Atlas AI Model APIs (P2-2).

POST {VOYAGE_BASE_URL}/embeddings  with  Authorization: Bearer {VOYAGE_API_KEY}
body: {"input": [...], "model": EMBEDDING_MODEL, "input_type": "document" | "query"}
Use "document" for memories being stored and "query" for incident observations.
Result vectors must have EMBEDDING_DIMENSIONS (1024) numbers to match the vector index.
"""

from __future__ import annotations

from typing import Literal


def embed(texts: list[str], input_type: Literal["document", "query"]) -> list[list[float]]:
    raise NotImplementedError("P2-2: embeddings")
