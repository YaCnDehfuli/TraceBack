"""Memory-service constants (P2). Connection and secrets come from core.config / core.db."""

from __future__ import annotations

import os

VECTOR_INDEX = "incident_memory_v2"
EMBEDDING_VERSION = 1

# Minimum vector score for recall and search (R8, plan 4.4). Tuned with voyage-4-lite against the 20
# labelled distractors in scripts/seed_demo.py and every case's real recall query:
#   real memory, lowest (generic Fence query) 0.867; cases A-D, B2, B3, P: 0.899-0.945
#   best distractor, any case: 0.791 ("Reload the signing secret after rotation", a webhook near miss)
# 0.83 sits in the middle of that gap. tests/memory/test_distractors.py keeps it honest.
# Exact signature matches (same error code and operation) bypass it, so a look-alike is still refused.
MIN_SCORE = float(os.getenv("MEMORY_MIN_SCORE", "0.83"))

TEAM_DBS = ["traceback_demo", "traceback_p1", "traceback_p2", "traceback_p3"]
