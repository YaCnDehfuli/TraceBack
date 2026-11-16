"""Run events: numbered from 1 with no gaps, each payload a contracts.models.*Payload.

EventSink keeps them in memory and calls `on_event` for each one (the CLI prints it; the API
writes it to the run_events collection).
"""

from __future__ import annotations

from collections.abc import Callable

from contracts.models import Contract, RunEvent, RunEventType
from core.clock import utc_now


class EventSink:
    def __init__(self, run_id: str, on_event: Callable[[RunEvent], None] | None = None):
        self.run_id = run_id
        self.events: list[RunEvent] = []
        self.on_event = on_event

    def emit(self, type_: RunEventType, payload: Contract) -> RunEvent:
        event = RunEvent(
            run_id=self.run_id,
            seq=len(self.events) + 1,
            type=type_,
            payload=payload.model_dump(by_alias=True, mode="json"),
            at=utc_now(),
        )
        self.events.append(event)
        if self.on_event:
            self.on_event(event)
        return event
