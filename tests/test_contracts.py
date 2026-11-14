"""The contracts hold together: fakes satisfy the interfaces, aliases round-trip, and the sample
run events the UI builds against are valid."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contracts.fakes import REFERENCE_FIX, FakeMemoryStore, FakeRunner
from contracts.interfaces import MemoryStore, Runner
from contracts.models import (
    Applicability,
    Conditions,
    FilePatch,
    MemoryDraft,
    MemoryOutcomePayload,
    Observations,
    PatchPayload,
    PreconditionPayload,
    Principal,
    RecallPayload,
    RunEvent,
    RunFinishedPayload,
    RunStartedPayload,
    VerificationPayload,
)

SAMPLE = Path(__file__).resolve().parent.parent / "contracts" / "sample_run_events.json"
PAYLOADS = {
    "run_started": RunStartedPayload,
    "recall": RecallPayload,
    "precondition_check": PreconditionPayload,
    "patch_proposed": PatchPayload,
    "verification": VerificationPayload,
    "memory_outcome": MemoryOutcomePayload,
    "run_finished": RunFinishedPayload,
}


def obs(**kw) -> Observations:
    return Observations(incident_id="inc_1", repository_id="payments-webhooks", summary="dup", **kw)


def test_fakes_satisfy_interfaces():
    assert isinstance(FakeMemoryStore(), MemoryStore)
    assert isinstance(FakeRunner(), Runner)


def test_camel_case_aliases_round_trip():
    p = Principal(tenant_id="demo-org", team_id="team-payments")
    dumped = p.model_dump(by_alias=True)
    assert dumped["tenantId"] == "demo-org" and dumped["teamId"] == "team-payments"
    assert Principal.model_validate(dumped) == p


def test_fake_store_is_team_scoped(payments, platform):
    store = FakeMemoryStore()
    assert len(store.recall(payments, obs(error_code="11000"), "run_1")) == 1
    assert store.recall(platform, obs(error_code="11000"), "run_2") == []


def test_fake_store_refuses_unverified_promotion(payments):
    store = FakeMemoryStore(seed_example=False)
    runner = FakeRunner()
    draft = MemoryDraft(
        incident_id="inc_9",
        repository_id="payments-webhooks",
        source_revision="abc",
        retrieval_text="E11000 on provider_event_id",
        signature={"errorCode": "11000"},
        confirmed_cause="replay",
        applicability=Applicability(conditions=Conditions(dup_key_field="provider_event_id")),
        resolution_summary="idempotent replay",
        patch=FilePatch(path="app/webhooks.py", new_content="pass"),
    )
    with pytest.raises(ValueError, match="no proof"):
        store.promote(payments, draft, runner.verify("A", draft.patch))
    good = runner.verify("A", FilePatch(path="app/webhooks.py", new_content=REFERENCE_FIX))
    memory_id = store.promote(payments, draft, good)
    assert store.promote(payments, draft, good) == memory_id  # idempotent
    assert store.is_searchable(payments, memory_id)


def test_fake_runner_models_the_team_convention():
    runner = FakeRunner()
    generic = REFERENCE_FIX.replace("        ledger.mark_replayed(event.id)\n", "")
    first = runner.verify("B", FilePatch(path="app/webhooks.py", new_content=generic))
    assert not first.verified
    failed = [t.name for t in first.tests if not t.passed]
    assert failed == ["test_replay_recorded_for_reconciliation"]
    second = runner.verify("B", FilePatch(path="app/webhooks.py", new_content=REFERENCE_FIX))
    assert second.verified and second.tests_passed == len(second.tests) == 7


def test_fake_runner_rejects_files_outside_the_allowlist():
    result = FakeRunner().verify("B", FilePatch(path="tests/test_x.py", new_content=REFERENCE_FIX))
    assert not result.verified and "allowlisted" in (result.detail or "")


def test_sample_run_events_are_valid():
    events = [RunEvent.model_validate(e) for e in json.loads(SAMPLE.read_text(encoding="utf-8"))]
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert events[0].type == "run_started" and events[-1].type == "run_finished"
    for e in events:
        if e.type in PAYLOADS:
            PAYLOADS[e.type].model_validate(e.payload)
