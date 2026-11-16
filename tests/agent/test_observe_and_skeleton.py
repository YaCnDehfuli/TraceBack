from __future__ import annotations

import importlib.util
from pathlib import Path

from agent.drafts import build_draft
from agent.observe import observations_from_case
from contracts.models import CaseManifest, FilePatch

LOGS = (
    "2026-11-14T03:02:21Z ERROR Exception in ASGI application\n"
    "Traceback (most recent call last):\n"
    '  File "app/webhooks.py", line 20, in receive\n'
    "    get_db().payments.insert_one(\n"
    "pymongo.errors.DuplicateKeyError: E11000 duplicate key error collection: fixture_payments.payments "
    'index: provider_event_id_1 dup key: { provider_event_id: "evt_1001" }'
)
CASE = CaseManifest.model_validate(
    {
        "caseId": "A",
        "teamId": "team-payments",
        "repositoryId": "payments-webhooks",
        "fixturePath": "fixture_app/payments-webhooks",
        "request": {
            "method": "POST",
            "path": "/webhooks/provider",
            "report": "Provider notifications are failing with HTTP 500.",
            "deliveries": [{"id": "evt_1001"}, {"id": "evt_1001"}],
        },
        "logs": LOGS,
        "patchableFiles": ["app/webhooks.py"],
        "reproductionTest": "test_duplicate_event_reproduces",
    }
)


def test_observations_from_case():
    obs = observations_from_case(CASE, "inc_1")
    assert obs.error_code == "11000"
    assert (obs.dup_key_index, obs.dup_key_field, obs.dup_key_value) == (
        "provider_event_id_1",
        "provider_event_id",
        "evt_1001",
    )
    assert obs.exception_type == "DuplicateKeyError"
    assert obs.delivery_event_ids == ["evt_1001", "evt_1001"]
    assert obs.stack_frames == ["app/webhooks.py:20 in receive"]
    assert obs.operation == "POST /webhooks/provider"
    assert "same event id" in obs.summary and "mark_replayed" not in obs.summary


def test_draft_fills_the_two_conditions():
    obs = observations_from_case(CASE, "inc_1")
    draft = build_draft(
        obs,
        FilePatch(path="app/webhooks.py", new_content="x"),
        source_revision="abc",
        confirmed_cause="c",
        resolution_summary="r",
    )
    assert draft.applicability.conditions.dup_key_field == "provider_event_id"
    assert draft.applicability.conditions.same_event_id_on_both_deliveries is True
    assert draft.signature == {"errorCode": "11000", "operation": "POST /webhooks/provider"}


def test_walking_skeleton_with_fakes(capsys):
    path = Path(__file__).resolve().parents[2] / "scripts" / "skeleton.py"
    spec = importlib.util.spec_from_file_location("skeleton", path)
    skeleton = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(skeleton)
    assert skeleton.main(["--runner", "fake", "--memory", "fake"]) == 0
    assert "Skeleton OK: Payments finds 1, Platform finds 0" in capsys.readouterr().out
