"""
Phase 8 — Fault injection (NFR7, roadmap Phase 8).

Three failure modes are forced here, each checked for the same property:
degrade gracefully (retry -> fallback -> needs_human_review), never crash,
never silently drop the submission.

  1. Forced OpenRouter timeout — parser.parse_with_retries against a client
     that raises a timeout/connection error on every attempt.
  2. Forced DB disconnect mid-finalize — _run_finalize_and_update's outer
     try/except around finalize_submission(), triggered by a DB-shaped
     exception (OperationalError) instead of a plain one, to prove the catch
     isn't accidentally narrower than "any exception".
  3. Simulated VM restart mid-finalize — resume_stuck_pipelines() picking up
     a row left in pending/processing by a prior crash and re-dispatching it.
"""
import time
import uuid
import threading
import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.exc import OperationalError

from app.models.db_models import Complaint, SubmissionType, Category, Status, PipelineStatus
from app.llm.parser import parse_with_retries
from pydantic import BaseModel


class _DummySchema(BaseModel):
    value: str


# ── 1. Forced LLM timeout — parser must exhaust retries and return None ────

class _AlwaysTimesOutClient:
    def __init__(self):
        self.call_count = 0

    def chat(self, **kwargs):
        self.call_count += 1
        raise TimeoutError("simulated OpenRouter timeout")


def test_parser_exhausts_retries_on_persistent_timeout_and_returns_none():
    client = _AlwaysTimesOutClient()
    result = parse_with_retries(
        client=client, model="dummy", system_prompt="sp", user_prompt="up",
        response_model=_DummySchema, max_retries=2, backoff_schedule=[0, 0],
    )
    assert result is None
    assert client.call_count == 3  # max_retries + 1, bounded — never infinite


def test_parser_never_raises_on_persistent_connection_error():
    """A ConnectionError (DB/network-shaped) must degrade the same way as a
    timeout — parse_with_retries's contract is "never raises", so the caller
    (finalize_submission) can always fall back rather than crash."""
    class _AlwaysConnErrorClient:
        def chat(self, **kwargs):
            raise ConnectionError("simulated network drop")

    result = parse_with_retries(
        client=_AlwaysConnErrorClient(), model="dummy", system_prompt="sp", user_prompt="up",
        response_model=_DummySchema, max_retries=1, backoff_schedule=[0],
    )
    assert result is None


# ── 2. finalize_submission — each stage's LLM failure must flag
#    needs_human_review, never raise, never drop the submission ───────────

def test_finalize_submission_classifier_failure_flags_needs_human_review(monkeypatch):
    from app.pipeline import orchestrator

    def _raise(*a, **kw):
        raise TimeoutError("simulated classify timeout")

    monkeypatch.setattr(orchestrator, "run_classifier", _raise)

    result = orchestrator.finalize_submission(
        raw_text="Huge pothole on MG Road",
        submission_type=SubmissionType.complaint,
        citizen_name="Bob", citizen_phone="9876543210",
    )
    assert result.needs_human_review is True
    assert result.review_reason == "LLM failed at classification stage"
    assert result.id is not None  # the row is still constructible/persistable, never dropped


def test_finalize_submission_urgency_failure_flags_needs_human_review(monkeypatch):
    from app.pipeline import orchestrator
    from app.llm.prompts.classify import ClassifyResponse

    monkeypatch.setattr(orchestrator, "run_classifier", lambda x: ClassifyResponse(category=Category.roads, confidence="high"))
    monkeypatch.setattr(orchestrator, "run_urgency_scorer", lambda x: (_ for _ in ()).throw(TimeoutError("simulated urgency timeout")))

    result = orchestrator.finalize_submission(
        raw_text="Huge pothole on MG Road",
        submission_type=SubmissionType.complaint,
        citizen_name="Bob", citizen_phone="9876543210",
    )
    assert result.needs_human_review is True
    assert result.review_reason == "LLM failed at urgency stage"


def test_finalize_submission_extractor_failure_flags_needs_human_review(monkeypatch):
    from app.pipeline import orchestrator
    from app.llm.prompts.classify import ClassifyResponse
    from app.llm.prompts.urgency import UrgencyResponse

    monkeypatch.setattr(orchestrator, "run_classifier", lambda x: ClassifyResponse(category=Category.roads, confidence="high"))
    monkeypatch.setattr(orchestrator, "run_urgency_scorer", lambda x: UrgencyResponse(urgency="low", reasoning="fine"))
    monkeypatch.setattr(orchestrator, "run_extractor", lambda *a, **kw: (_ for _ in ()).throw(ConnectionError("simulated DB/network drop")))

    result = orchestrator.finalize_submission(
        raw_text="Huge pothole on MG Road",
        submission_type=SubmissionType.complaint,
        citizen_name="Bob", citizen_phone="9876543210",
    )
    assert result.needs_human_review is True
    assert result.review_reason == "LLM failed at extraction stage"


# ── 3. DB disconnect mid-finalize — _run_finalize_and_update's outer catch ──

def test_run_finalize_and_update_marks_failed_not_lost_on_db_disconnect(monkeypatch):
    """finalize_submission raising an OperationalError (simulating the DB
    connection dropping mid-finalize, e.g. during the dedup pgvector query)
    must be caught by _run_finalize_and_update's outer try/except: the stub
    row is marked pipeline_status=failed + needs_human_review, never left
    silently pending and never crashes the background thread."""
    from app.pipeline import orchestrator
    from app.db import session as db_session_module

    test_engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr(db_session_module, "engine", test_engine)

    with Session(test_engine) as session:
        stub = Complaint(
            submission_type=SubmissionType.complaint,
            raw_text="Live wire sparking near school",
            citizen_name="Alice", citizen_phone="9876500000",
            status=Status.open, pipeline_status=PipelineStatus.pending,
        )
        session.add(stub)
        session.commit()
        session.refresh(stub)
        stub_id = stub.id

    def _raise_db_disconnect(*a, **kw):
        raise OperationalError("SELECT 1", {}, Exception("simulated connection drop"))

    monkeypatch.setattr(orchestrator, "finalize_submission", _raise_db_disconnect)

    orchestrator._run_finalize_and_update(
        stub_id, "Live wire sparking near school", "complaint",
        "Alice", "9876500000", None, None, None, None,
    )

    with Session(test_engine) as session:
        row = session.get(Complaint, stub_id)
        assert row is not None, "submission must never be silently dropped"
        assert row.pipeline_status == PipelineStatus.failed
        assert row.needs_human_review is True
        assert row.review_reason.startswith("pipeline_error")
        assert row.raw_text == "Live wire sparking near school"  # original data intact


# ── 4. Simulated VM restart mid-finalize — resume_stuck_pipelines() ─────────

def test_resume_stuck_pipelines_reprocesses_rows_left_by_a_crash(monkeypatch):
    """A row stuck in `processing` (as if the process died mid-finalize)
    must be picked back up and re-dispatched on the next startup — proving
    NFR7's "resumable, not lost on restart" claim without needing an actual
    VM reboot."""
    from app.pipeline import orchestrator
    from app.db import session as db_session_module

    test_engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr(db_session_module, "engine", test_engine)

    with Session(test_engine) as session:
        stuck = Complaint(
            submission_type=SubmissionType.complaint,
            raw_text="Stuck mid-finalize before a simulated crash",
            citizen_name="Carl", citizen_phone="9876500001",
            status=Status.open, pipeline_status=PipelineStatus.processing,
        )
        done = Complaint(
            submission_type=SubmissionType.complaint,
            raw_text="Already finished, must not be re-touched",
            citizen_name="Dana", citizen_phone="9876500002",
            status=Status.open, pipeline_status=PipelineStatus.done,
        )
        session.add(stuck)
        session.add(done)
        session.commit()
        session.refresh(stuck)
        session.refresh(done)
        stuck_id, done_id = stuck.id, done.id

    dispatched_ids = []
    dispatch_done = threading.Event()

    def _fake_finalize_and_update(stub_id, *a, **kw):
        dispatched_ids.append(stub_id)
        dispatch_done.set()

    monkeypatch.setattr(orchestrator, "_run_finalize_and_update", _fake_finalize_and_update)

    orchestrator.resume_stuck_pipelines()
    assert dispatch_done.wait(timeout=5), "stuck row was never dispatched for reprocessing"
    time.sleep(0.1)  # let any (unexpected) extra dispatch land before asserting

    assert stuck_id in dispatched_ids
    assert done_id not in dispatched_ids  # an already-done row must never be re-run
    assert len(dispatched_ids) == 1
