"""Memory-service constants (P2). Connection and secrets come from core.config / core.db."""

from __future__ import annotations

import os

VECTOR_INDEX = "incident_memory_v2"
EMBEDDING_VERSION = 1

# Minimum vector score for recall. 0 until R8 (distractors) tunes it.
MIN_SCORE = float(os.getenv("MEMORY_MIN_SCORE", "0"))

TEAM_DBS = ["traceback_demo", "traceback_p1", "traceback_p2", "traceback_p3"]
