"""
Tests for GET /leaders (FR9's concerned-person dropdown source).

Calls search_leaders() directly against an isolated in-memory SQLite session
rather than going through TestClient/the shared `app` object — this endpoint
has no auth dependency to exercise over HTTP, and test_feedback_corrections.py
already documents a real collision risk from multiple files clobbering
app.dependency_overrides[get_session] on the same shared app; the cleanest
way to avoid replaying that is to not touch it at all here.

Covers the actual gap: results are now sorted alphabetically (case-
insensitive) so a searchable frontend combobox has a predictable base order,
on top of the pre-existing city/pincode matching (verified still correct).
"""
import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from app.api.leaders import search_leaders
from app.models.db_models import Leader

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)


@pytest.fixture(autouse=True)
def _db():
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


def _seed(session, name, city, pincode):
    l = Leader(name=name, phone="9000000000", email=f"{name.lower().replace(' ', '.')}@example.com",
               city=city, pincode=pincode)
    session.add(l)
    return l


def test_results_sorted_alphabetically_case_insensitive():
    with Session(engine) as session:
        _seed(session, "vikas Chandra", "Delhi", "110017")
        _seed(session, "Anita Deshmukh", "Delhi", "110018")
        _seed(session, "meena Iyer", "Delhi", "110019")
        session.commit()
        result = search_leaders(city="Delhi", pincode=None, session=session)

    names = [r.name for r in result]
    assert names == ["Anita Deshmukh", "meena Iyer", "vikas Chandra"], (
        "must sort case-insensitively — a naive sort would put 'Anita' before "
        "'meena'/'vikas' only by accident of ASCII case, not alphabetical order"
    )


def test_city_match_is_case_insensitive_substring():
    with Session(engine) as session:
        _seed(session, "Sumit", "Parbhani", "431401")
        session.commit()
        result = search_leaders(city="parb", pincode=None, session=session)

    assert [r.name for r in result] == ["Sumit"]


def test_exact_pincode_match_preferred_within_city():
    with Session(engine) as session:
        _seed(session, "A Leader", "Pune", "411001")
        _seed(session, "B Leader", "Pune", "411002")
        session.commit()
        result = search_leaders(city="Pune", pincode="411002", session=session)

    assert [r.name for r in result] == ["B Leader"]


def test_pincode_with_no_exact_match_falls_back_to_city_level_list():
    """A citizen who typed a pincode with no exact leader match must still
    see the city-level list, not an empty dropdown."""
    with Session(engine) as session:
        _seed(session, "A Leader", "Pune", "411001")
        session.commit()
        result = search_leaders(city="Pune", pincode="999999", session=session)

    assert [r.name for r in result] == ["A Leader"]


def test_no_filters_returns_everyone_sorted():
    with Session(engine) as session:
        _seed(session, "Zed", "X", "000001")
        _seed(session, "Amy", "Y", "000002")
        session.commit()
        result = search_leaders(city=None, pincode=None, session=session)

    assert [r.name for r in result] == ["Amy", "Zed"]


def test_new_leader_in_a_matching_city_appears_immediately():
    """Directly exercises this session's ask: a leader registered in a given
    city must show up for a citizen who enters that same city — no caching,
    no delay, no extra step."""
    with Session(engine) as session:
        result_before = search_leaders(city="Nashik", pincode=None, session=session)
        assert result_before == []

        _seed(session, "New Corporator", "Nashik", "422001")
        session.commit()

        result_after = search_leaders(city="Nashik", pincode=None, session=session)

    assert [r.name for r in result_after] == ["New Corporator"]
