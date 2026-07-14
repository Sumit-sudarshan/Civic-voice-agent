"""
Concurrency Regression Test — Appendix Item 3 (bug_fix.md)

Verifies that two clearly distinct complaints processed concurrently by the
pipeline NEVER cross-contaminate each other's stored results.

This is a permanent regression test, not a one-off manual check. Run it after
any change to orchestrator.py or stages.py to confirm shared-mutable-state
bugs haven't been re-introduced.

Usage:
    cd backend
    pytest tests/test_concurrency.py -v
    pytest tests/test_concurrency.py -v -s        # show print output
"""
import concurrent.futures
import pytest

from app.models.db_models import SubmissionType, Category


# ── Two maximally distinct complaints ────────────────────────────────────────
# Chosen so that ANY bleed-through of key fields is immediately detectable:
# one is about a road pothole (infrastructure/low urgency),
# the other is about a dangerous exposed live wire (safety/high urgency).

COMPLAINT_A = dict(
    raw_text=(
        "There is a small pothole on the road near the corner of MG Road. "
        "It is slightly inconvenient for cyclists."
    ),
    citizen_name="Citizen Alpha",
    citizen_phone="9000000001",
)

COMPLAINT_B = dict(
    raw_text=(
        "A live electricity wire has snapped and is lying on the footpath "
        "near the main water tank on Gandhi Nagar, sparking continuously. "
        "Children walk past this area every morning on the way to school."
    ),
    citizen_name="Citizen Beta",
    citizen_phone="9000000002",
)

# Keyword fingerprints unique to each complaint — cross-contamination is
# detected if the wrong keywords appear in the wrong result.
KEYWORDS_A = {"pothole", "road", "mg road", "cyclist", "mg"}
KEYWORDS_B = {"wire", "electricity", "water tank", "gandhi nagar", "spark", "school", "children"}


def _any_b_keywords_in(text: str | None) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(kw in lower for kw in KEYWORDS_B)


def _any_a_keywords_in(text: str | None) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(kw in lower for kw in KEYWORDS_A)


# ── Monkeypatched fast mocks ──────────────────────────────────────────────────
# Mocks are deterministic based on the input text so they faithfully simulate
# the REAL pipeline's data-routing while being CPU-free and instant.
# The key property: mock functions read from their argument (raw_text),
# not from any shared module-level state. This mirrors the contract that
# real LLM stages must satisfy.

def _mock_classifier(text: str):
    from app.llm.prompts.classify import ClassifyResponse
    if "pothole" in text.lower() or "road" in text.lower():
        return ClassifyResponse(category=Category.roads, confidence="high")
    return ClassifyResponse(category=Category.electricity, confidence="high")


def _mock_urgency(text: str):
    from app.llm.prompts.urgency import UrgencyResponse
    # Pothole → low urgency; live wire → critical urgency
    if "pothole" in text.lower():
        return UrgencyResponse(
            urgency="low",
            reasoning="Small pothole near MG Road causing minor inconvenience to cyclists.",
        )
    return UrgencyResponse(
        urgency="critical",
        reasoning=(
            "Live electricity wire sparking on a public footpath near a water tank "
            "in Gandhi Nagar. Children at imminent risk of electrocution."
        ),
    )


def _mock_extractor(text: str, known_location: str | None = None):
    from app.llm.prompts.extract import ExtractionResponse
    if "pothole" in text.lower():
        return ExtractionResponse(
            location="MG Road corner",
            issue_summary="Small pothole causing inconvenience to cyclists near MG Road.",
            affected_parties="Cyclists and pedestrians near MG Road",
            ask="Repair the pothole at the earliest opportunity.",
        )
    return ExtractionResponse(
        location="Gandhi Nagar near main water tank",
        issue_summary=(
            "Snapped live electricity wire lying on the footpath near the Gandhi Nagar "
            "water tank, sparking continuously. Children pass this route daily."
        ),
        affected_parties="Schoolchildren, residents, and pedestrians in Gandhi Nagar",
        ask="Emergency removal or isolation of the live wire immediately.",
    )


def _mock_embed(text: str):
    # Distinct dummy embeddings — pothole gets [0.1, ...], wire gets [0.9, ...]
    val = 0.1 if "pothole" in text.lower() else 0.9
    return [val] * 5


@pytest.fixture(autouse=True)
def _patch_pipeline(monkeypatch):
    """Apply deterministic mocks to all LLM and embedding calls."""
    monkeypatch.setattr("app.pipeline.orchestrator.run_classifier",     _mock_classifier)
    monkeypatch.setattr("app.pipeline.orchestrator.run_urgency_scorer", _mock_urgency)
    monkeypatch.setattr("app.pipeline.orchestrator.run_extractor",      _mock_extractor)
    monkeypatch.setattr("app.pipeline.orchestrator.embed",              _mock_embed)


def _run(complaint: dict):
    from app.pipeline.orchestrator import finalize_submission
    return finalize_submission(submission_type=SubmissionType.complaint, **complaint)


# ── Tests ────────────────────────────────────────────────────────────────────

def test_sequential_isolation():
    """Baseline: results are correct when complaints run one after the other."""
    res_a = _run(COMPLAINT_A)
    res_b = _run(COMPLAINT_B)

    # A: roads, low urgency, pothole keywords
    assert res_a.urgency_level == "low",     f"A urgency wrong: {res_a.urgency_level}"
    assert "pothole" in (res_a.extracted_issue_summary or "").lower(), \
        f"A summary missing pothole: {res_a.extracted_issue_summary}"
    assert res_a.category == Category.roads

    # B: electricity, critical urgency, wire keywords
    assert res_b.urgency_level == "critical", f"B urgency wrong: {res_b.urgency_level}"
    assert "wire" in (res_b.extracted_issue_summary or "").lower() or \
           "electricity" in (res_b.extracted_issue_summary or "").lower(), \
        f"B summary missing wire/electricity: {res_b.extracted_issue_summary}"
    assert res_b.category == Category.electricity


def test_concurrent_no_cross_contamination():
    """
    Core regression test: submit both complaints at nearly the same time via
    two threads. Assert that each result contains only its OWN keywords — no
    data from the other complaint has leaked through shared mutable state.

    If orchestrator.py or stages.py use any module-level or instance-level
    mutable variable to pass data between calls, this test will catch it
    because at least one of the two concurrent runs will read the wrong value.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(_run, COMPLAINT_A)
        future_b = pool.submit(_run, COMPLAINT_B)
        res_a = future_a.result(timeout=30)
        res_b = future_b.result(timeout=30)

    # ── Result A must contain ONLY complaint-A data ────────────────────────
    assert res_a.category == Category.roads, \
        f"A.category contaminated: expected roads, got {res_a.category}"
    assert res_a.urgency_level == "low", \
        f"A.urgency contaminated: expected 'low', got {res_a.urgency_level!r}"
    assert not _any_b_keywords_in(res_a.extracted_issue_summary), \
        f"A.summary contains B keywords (contamination!): {res_a.extracted_issue_summary!r}"
    assert not _any_b_keywords_in(res_a.urgency_reasoning), \
        f"A.urgency_reasoning contains B keywords (contamination!): {res_a.urgency_reasoning!r}"

    # ── Result B must contain ONLY complaint-B data ────────────────────────
    assert res_b.category == Category.electricity, \
        f"B.category contaminated: expected electricity, got {res_b.category}"
    assert res_b.urgency_level == "critical", \
        f"B.urgency contaminated: expected 'critical', got {res_b.urgency_level!r}"
    assert not _any_a_keywords_in(res_b.extracted_issue_summary), \
        f"B.summary contains A keywords (contamination!): {res_b.extracted_issue_summary!r}"
    assert not _any_a_keywords_in(res_b.urgency_reasoning), \
        f"B.urgency_reasoning contains A keywords (contamination!): {res_b.urgency_reasoning!r}"


def test_concurrent_ten_requests():
    """
    Stress variant: 10 concurrent submissions (alternating A and B).
    Every result must resolve to the complaint it was given, never the other.
    This catches race conditions that only surface under higher concurrency.
    """
    inputs = [COMPLAINT_A if i % 2 == 0 else COMPLAINT_B for i in range(10)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(_run, inputs))

    for i, (inp, res) in enumerate(zip(inputs, results)):
        is_a = inp["raw_text"] == COMPLAINT_A["raw_text"]
        label = "A" if is_a else "B"

        expected_urgency  = "low" if is_a else "critical"
        expected_category = Category.roads if is_a else Category.electricity

        assert res.urgency_level == expected_urgency, \
            f"Request {i} (complaint {label}): urgency wrong — got {res.urgency_level!r}"
        assert res.category == expected_category, \
            f"Request {i} (complaint {label}): category wrong — got {res.category}"

        if is_a:
            assert not _any_b_keywords_in(res.extracted_issue_summary), \
                f"Request {i} (A): summary has B keywords: {res.extracted_issue_summary!r}"
            assert not _any_b_keywords_in(res.urgency_reasoning), \
                f"Request {i} (A): reasoning has B keywords: {res.urgency_reasoning!r}"
        else:
            assert not _any_a_keywords_in(res.extracted_issue_summary), \
                f"Request {i} (B): summary has A keywords: {res.extracted_issue_summary!r}"
            assert not _any_a_keywords_in(res.urgency_reasoning), \
                f"Request {i} (B): reasoning has A keywords: {res.urgency_reasoning!r}"
