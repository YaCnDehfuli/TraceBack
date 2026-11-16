# trusted_tests

Tests that decide whether a fix is verified. They live outside anything the agent may change,
and the runner copies them into the sandbox read-only. The agent sees test names and assertion
messages, never this source.

1. `test_duplicate_event_reproduces`: the same event twice crashes on the original code
2. `test_duplicate_event_single_effect`: after the fix, twice returns OK and credits exactly once
3. `test_replay_recorded_for_reconciliation`: a duplicate delivery calls `mark_replayed` exactly once
4. `test_distinct_events_same_customer`: two different events from one customer are both processed
5. `test_unique_index_still_present`: the unique index on the event id still exists
6. Regression tests: normal single payments still work

