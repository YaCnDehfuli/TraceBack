"""The investigation loop (P1-2). Stub until then.

Steps, each written as a RunEvent (contracts.models.*Payload):
  1. run_started
  2. observation      parse logs; agent.conditions.apply_e11000; delivery event ids
  3. recall           memory.recall(...) unless memory_mode is "off" ("placebo" injects evals/placebo_memories.json)
  4. precondition_check   agent.conditions.check_conditions, in code, before any LLM call
                          failed -> record_use(decision="rejected") and a not_applied_reason event
  5. tool_call / tool_result   LLM-chosen file tools, every call charged to the Budget
  6. patch_proposed   whole-file FilePatch; tag lines matching the memory's resolution_patch (P1-6)
  7. verification     runner.verify(...); a failed attempt feeds test names + assertion messages back
  8. memory_outcome   promote (new fix) or record_use (reused memory); a refused write -> "refused"
  9. run_finished     RunFinishedPayload with a one-sentence summary
"""

from __future__ import annotations

from agent.budgets import Budget
from contracts.interfaces import MemoryStore, Runner
from contracts.models import CaseManifest, MemoryMode, Principal, RunView


def run_investigation(
    principal: Principal,
    case: CaseManifest,
    memory: MemoryStore,
    runner: Runner,
    budget: Budget | None = None,
    memory_mode: MemoryMode = "real",
) -> RunView:
    raise NotImplementedError("P1-2: agent loop")
