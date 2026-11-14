"""LocalRunner: the real Runner (P3-3). Stub until then; use contracts.fakes.FakeRunner.

verify(case_id, patch):
  1. fresh temp copy of fixture_app/<repo>; empty fixture database (FIXTURE_MONGODB_URI)
  2. reproduction test on the ORIGINAL code -> must fail (else the case is broken: inconclusive)
  3. another fresh copy; write patch.new_content only if patch.path is in the case's patchable_files
  4. pytest on trusted_tests/ in a separate process, with a timeout and a stripped environment
     (no MONGODB_URI, no LLM / Voyage / ElevenLabs keys)
  5. return VerificationResult with test names and assertion messages (never the test source)
  6. delete the temp copies; drop the fixture database
"""

from __future__ import annotations

from contracts.models import FilePatch, VerificationResult


class LocalRunner:
    def reproduce(self, case_id: str) -> VerificationResult:
        raise NotImplementedError("P3-3: reproduce")

    def verify(self, case_id: str, patch: FilePatch) -> VerificationResult:
        raise NotImplementedError("P3-3: verify")
