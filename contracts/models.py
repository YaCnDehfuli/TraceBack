"""Shared data shapes (Pydantic v2). Frozen by agreement: see contracts/__init__.py.

Python attributes are snake_case. JSON and MongoDB documents use camelCase through aliases:

    principal.model_dump(by_alias=True)              -> {"tenantId": ..., "teamId": ...}
    Principal.model_validate({"tenantId": ...})       works
    Principal(tenant_id=...)                          also works

All datetimes are timezone-aware UTC (use core.clock.utc_now()).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

Role = Literal["engineer", "memory_admin"]
RetrievalSource = Literal["vector", "signature"]
Match = Literal["strong", "weak"]  # shown on screen instead of a raw score
UseDecision = Literal["used", "rejected", "stale"]
VerificationStatus = Literal["passed", "failed", "inconclusive"]
MemoryMode = Literal["real", "off", "placebo"]  # ?memory= switch, used by the experiment
MemoryStatus = Literal["active", "disputed", "superseded", "revoked"]
MemoryOutcome = Literal["promoted", "renewed", "near_miss", "disputed", "refused"]
RunStatus = Literal["queued", "running", "finished", "error"]
RunOutcome = Literal["verified", "escalated", "unresolved"]
RunEventType = Literal[
    "run_started",
    "observation",
    "recall",
    "precondition_check",
    "tool_call",
    "tool_result",
    "patch_proposed",
    "verification",
    "memory_outcome",
    "run_finished",
    "error",
]


class Contract(BaseModel):
    """Base for every shared model: camelCase aliases, accepts either spelling, ignores unknown keys."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


# =========================================================================== identity


class Principal(Contract):
    """Who is calling. Always derived by the server from the API key, never from the LLM, a body or speech."""

    tenant_id: str
    team_id: str
    role: Role = "engineer"
    authorized_repos: list[str] = Field(default_factory=list)


# =========================================================================== incidents and observations


class Observations(Contract):
    """Facts extracted from an incident (agent/conditions.py parses the E11000 message).

    `summary` is the text that gets embedded for recall: symptoms only, never the answer.

    Example E11000 message:
      E11000 duplicate key error collection: shop.payments index: provider_event_id_1
      dup key: { provider_event_id: "evt_123" }
    -> dup_key_index="provider_event_id_1", dup_key_field="provider_event_id", dup_key_value="evt_123"
    """

    incident_id: str
    repository_id: str
    summary: str
    error_code: str | None = None
    operation: str | None = None
    exception_type: str | None = None
    dup_key_index: str | None = None
    dup_key_field: str | None = None
    dup_key_value: str | None = None
    delivery_event_ids: list[str] = Field(default_factory=list)  # event id of each delivery in the incident
    stack_frames: list[str] = Field(default_factory=list)
    versions: dict[str, str] = Field(default_factory=dict)


# =========================================================================== memory


class Conditions(Contract):
    """The fixed two-condition vocabulary (plan 4.2), filled automatically at promote time and
    checked in plain code (agent/conditions.py), never by the LLM. None = not constrained."""

    dup_key_field: str | None = None
    same_event_id_on_both_deliveries: bool | None = None


class Applicability(Contract):
    conditions: Conditions = Field(default_factory=Conditions)
    excludes: list[str] = Field(default_factory=list)  # human-readable; a correction (version 2) narrows these


class FileAnchor(Contract):
    """Fingerprint of a file the fix touched, used for the staleness warning (plan R12)."""

    path: str
    sha256: str


class FilePatch(Contract):
    """A proposed fix: the complete new contents of ONE allowlisted file (never a diff)."""

    path: str
    new_content: str


class MemoryRef(Contract):
    """Metadata-only reference to a memory: safe for events, the voice agent and logs (no memory text)."""

    memory_id: str
    version: int
    owner_team_id: str
    match: Match | None = None


class MemoryCandidate(Contract):
    """A memory returned by recall: already filtered by team scope, status and expiry, and re-read."""

    memory_id: str
    version: int
    owner_team_id: str
    repository_id: str
    rank: int
    score: float  # internal; the UI shows `match`
    match: Match
    source: RetrievalSource
    retrieval_text: str
    confirmed_cause: str
    resolution_summary: str
    resolution_patch: FilePatch | None = None  # the proven fix, used to tag "from memory" lines (P1-6)
    applicability: Applicability
    anchors: list[FileAnchor] = Field(default_factory=list)
    expires_at: datetime
    stale: bool = False

    def ref(self) -> MemoryRef:
        return MemoryRef(
            memory_id=self.memory_id, version=self.version, owner_team_id=self.owner_team_id, match=self.match
        )


class PreconditionResult(Contract):
    """One condition checked against the current incident. held=None: could not be evaluated."""

    check: str  # "dup_key_field" | "same_event_id_on_both_deliveries"
    expected: str
    actual: str | None
    held: bool | None


class MemoryDraft(Contract):
    """What the agent hands the memory service after a verified fix, to be promoted into a memory."""

    incident_id: str
    repository_id: str
    source_revision: str
    retrieval_text: str
    signature: dict[str, str] = Field(default_factory=dict)  # {"errorCode": "11000", "operation": "..."}
    confirmed_cause: str
    applicability: Applicability
    resolution_summary: str
    patch: FilePatch
    anchors: list[FileAnchor] = Field(default_factory=list)


# =========================================================================== verification


class TestOutcome(Contract):
    __test__ = False  # stop pytest from trying to collect this class

    name: str
    passed: bool
    detail: str | None = None  # the assertion message only (truncated); NEVER the trusted test source


class VerificationResult(Contract):
    """Facts produced by the runner. The LLM saying "tests passed" never counts; only this does.

    reproduce(): expected `before_failed=True` (the bug is real) and `status="failed"`.
    verify():    `status="passed"` only when the bug reproduced on the original code AND every
                 trusted test passes on the patched copy. "inconclusive" = our infrastructure broke.
    The agent sees test names and `detail` (assertion messages), not the trusted test source.
    """

    run_id: str
    case_id: str
    status: VerificationStatus
    before_failed: bool
    after_passed: bool
    tests: list[TestOutcome] = Field(default_factory=list)
    evidence_hashes: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    detail: str | None = None

    @property
    def verified(self) -> bool:
        return self.status == "passed" and self.before_failed and self.after_passed

    @property
    def tests_passed(self) -> int:
        return sum(t.passed for t in self.tests)


class MemoryUseDecision(Contract):
    """What the agent did with one recalled memory. The memory service turns it into the governance
    outcome (renewed / disputed / near_miss); the agent never decides that itself."""

    decision: UseDecision
    preconditions: list[PreconditionResult] = Field(default_factory=list)
    reason: str
    verification: VerificationResult | None = None


class MemoryInfluence(Contract):
    """One entry of a run's memory-influence record."""

    memory: MemoryRef
    rank: int
    decision: UseDecision
    preconditions: list[PreconditionResult] = Field(default_factory=list)


# =========================================================================== runs and timeline


class RunEvent(Contract):
    """One step in a run's timeline. `seq` starts at 1 and increases by 1 per run, with no gaps.
    `payload` follows the *Payload model for its type (below). See contracts/sample_run_events.json."""

    run_id: str
    seq: int
    type: RunEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    at: datetime


class RunStartedPayload(Contract):
    incident_id: str
    case_id: str | None = None
    team_id: str
    memory_mode: MemoryMode = "real"


class ObservationPayload(Contract):
    observations: Observations


class RecallPayload(Contract):
    count: int
    memories: list[MemoryRef] = Field(default_factory=list)


class PreconditionPayload(Contract):
    memory: MemoryRef
    held: int
    total: int
    results: list[PreconditionResult]
    not_applied_reason: str | None = None  # e.g. "Not applied: duplicate key is `customer_id`; ..."


class ToolCallPayload(Contract):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolResultPayload(Contract):
    tool: str
    evidence_id: str
    summary: str


class PatchPayload(Contract):
    attempt: int
    patch: FilePatch
    from_memory: MemoryRef | None = None
    from_memory_lines: list[int] = Field(default_factory=list)  # 1-based lines in patch.new_content to highlight


class VerificationPayload(Contract):
    attempt: int
    result: VerificationResult


class MemoryOutcomePayload(Contract):
    outcome: MemoryOutcome
    memory: MemoryRef | None = None
    message: str  # e.g. "Memory refused: no proof."


class RunFinishedPayload(Contract):
    outcome: RunOutcome
    attempt: int | None = None
    seen_before: bool
    tests_passed: int = 0
    tests_total: int = 0
    memory_used: MemoryRef | None = None
    summary: str  # one plain sentence, also what the voice agent may read out
    escalation: str | None = None  # escalated / unresolved runs: a plain-text handoff a human can copy


class ErrorPayload(Contract):
    message: str


class BudgetUsage(Contract):
    tool_calls: int = 0
    patch_attempts: int = 0
    elapsed_ms: int = 0
    max_tool_calls: int
    max_patch_attempts: int
    deadline_seconds: int


class RunView(Contract):
    """GET /runs/{id}. Also what the voice tool get_run_status returns (metadata only)."""

    run_id: str
    incident_id: str
    case_id: str | None = None
    team_id: str
    status: RunStatus
    outcome: RunOutcome | None = None
    attempt: int | None = None
    seen_before: bool = False
    tests_passed: int = 0
    tests_total: int = 0
    memory_used: MemoryRef | None = None
    memory_mode: MemoryMode = "real"
    budget: BudgetUsage
    memory_influence: list[MemoryInfluence] = Field(default_factory=list)
    model: str | None = None
    prompt_version: str | None = None


# =========================================================================== memory REST shapes (P2)


class Proof(Contract):
    before_failed: bool
    after_passed: bool
    tests_total: int
    verification_run_id: str


class Tombstone(Contract):
    forgotten_by: str
    reason: str
    at: datetime


class MemoryCard(Contract):
    """What web/memory.js renders (plan 7.3). No IDs or scores in the main view; they go under "details"."""

    memory_id: str
    version: int
    title: str
    owner_team_id: str
    readable_by: list[str]
    status: MemoryStatus
    created_at: datetime
    expires_at: datetime
    purge_at: datetime
    proof: Proof
    applicability: Applicability
    stale: bool = False
    seeded: bool = False
    match: Match | None = None
    forgotten: Tombstone | None = None


class MemorySearchResult(Contract):
    """GET /memories/search?q= : the same scoped search as recall, for the caller's team."""

    query: str
    team_id: str
    count: int
    memories: list[MemoryCard] = Field(default_factory=list)
    filter: dict[str, Any] = Field(default_factory=dict)  # the $vectorSearch pre-filter, printed in the Fence view


class ReasonBody(Contract):
    reason: str


class CorrectBody(Contract):
    excludes: list[str]
    reason: str


# =========================================================================== cases (P3)


class CaseManifest(Contract):
    """cases/<id>/manifest.json: what the agent may see about a case. Answers live in labels.json."""

    case_id: str
    team_id: str
    repository_id: str
    fixture_path: str
    request: dict[str, Any] = Field(default_factory=dict)
    logs: str
    patchable_files: list[str]
    reproduction_test: str
    test_ids: list[str] = Field(default_factory=list)
    revision: str | None = None


# =========================================================================== API shapes shared with the UI


class IncidentCreate(Contract):
    """Body of POST /incidents."""

    repository_id: str
    logs: str
    request: dict[str, Any] = Field(default_factory=dict)
    revision: str | None = None
    case_id: str | None = None


class IncidentCreated(Contract):
    incident_id: str


class RunStarted(Contract):
    run_id: str
    status: RunStatus = "queued"
