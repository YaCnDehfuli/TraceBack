"""Memory-service constants (P2). Connection and secrets come from core.config / core.db."""

from __future__ import annotations

import os

VECTOR_INDEX = "incident_memory_v2"
EMBEDDING_VERSION = 1

# Minimum vector score for recall and search (R8, plan 4.4), against the 20 labelled distractors in
# scripts/seed_demo.py and every case's real recall query. Measured with voyage-4-lite on main 45afa59
# (#60: recall embeds code-derived facts only), memory embedded as "document", query as "query".
# Scores are Atlas vectorSearchScore = (1 + cosine) / 2, not raw cosine:
#   true repeats A, B, B2, B3, P: 0.952 | look-alikes D 0.939, C 0.927 | best distractor: 0.778
#   ("Reload the signing secret after rotation", a webhook near miss) | generic Fence query: 0.897
# 0.83 leaves a clear gap on both sides. tests/memory/test_distractors.py re-checks it per case.
# Exact signature matches (same error code and operation) bypass it, so a look-alike is still refused.
# (Before #60, with free-text recall, the same cutoff separated 0.867-0.945 from 0.791.)
MIN_SCORE = float(os.getenv("MEMORY_MIN_SCORE", "0.83"))

TEAM_DBS = ["traceback_demo", "traceback_p1", "traceback_p2", "traceback_p3"]
