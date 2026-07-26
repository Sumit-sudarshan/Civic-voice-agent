"""
Phase 9 — regression test for a real bug found via live load testing: with
Supavisor pool_size=5/max_overflow=0 and a single uvicorn worker, a burst of
20-50 concurrent citizens (the design's own stated peak) failed roughly half
to all of the time with `sqlalchemy.exc.TimeoutError: QueuePool limit of
size 5 ... connection timed out`. Root cause: SQLAlchemy's Session
auto-begins a transaction (and checks out a pooled connection) on
check_rate_limit's SELECT, and never releases it until the request's session
closes — holding the connection hostage for however long the gatekeeper/
dialogue-manager LLM calls block, even though nothing after that point
touches the DB until a rejection or the final stub insert.

The fix (_prepare_turn in orchestrator.py) is a single session.rollback()
right after check_rate_limit, before any LLM call — free (no pending writes
yet) and releases the connection back to the pool for the LLM-heavy
remainder of the turn. Confirmed live: before the fix, waves of 20 and 50
concurrent /intake/message requests against the deployed VM got 10/20 and
0/50 successes; after the fix, 20/20 and 50/50, zero pool-timeout errors,
memory unchanged. This test proves the same ordering holds structurally,
without needing a live Postgres pool to reproduce the timeout.
"""
from app.models.schemas import ChatMessageRequest


def test_prepare_turn_releases_connection_before_any_llm_call(monkeypatch):
    """Session.rollback() must happen after the rate-limit check but before
    the gatekeeper/dialogue-manager calls — the exact ordering the live
    QueuePool exhaustion bug depended on getting wrong."""
    from app.pipeline import orchestrator

    call_log = []

    class _FakeSession:
        def rollback(self):
            call_log.append("rollback")

        def commit(self):
            call_log.append("commit")

        def add(self, *a, **kw):
            pass

    def _fake_check_rate_limit(session, owner_user_id):
        call_log.append("rate_limit_check")
        return None

    def _fake_gatekeeper(text):
        call_log.append("gatekeeper")
        from app.llm.prompts.gatekeeper import GatekeeperResponse
        return GatekeeperResponse(label="too_vague_to_process", confidence="high")

    def _fake_dialogue_manager(transcript):
        call_log.append("dialogue_manager")
        from app.llm.prompts.dialogue import DialogueState
        return DialogueState(issue_clear=False)

    monkeypatch.setattr(orchestrator, "check_rate_limit", _fake_check_rate_limit)
    monkeypatch.setattr(orchestrator, "run_gatekeeper", _fake_gatekeeper)
    monkeypatch.setattr(orchestrator, "run_dialogue_manager", _fake_dialogue_manager)

    payload = ChatMessageRequest(
        new_message="Something is wrong somewhere",
        history=[], citizen_first_name="Test", citizen_phone="9876543210",
    )
    orchestrator._prepare_turn(payload, _FakeSession())

    assert call_log.index("rollback") < call_log.index("gatekeeper"), (
        f"connection must be released before the first LLM call: {call_log}"
    )
    assert call_log.index("rollback") < call_log.index("dialogue_manager"), (
        f"connection must be released before the dialogue manager call: {call_log}"
    )
    assert call_log.index("rate_limit_check") < call_log.index("rollback"), (
        f"rollback must come after the rate-limit read it's releasing: {call_log}"
    )
