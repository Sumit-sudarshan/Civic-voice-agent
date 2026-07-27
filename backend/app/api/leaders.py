from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select
from sqlalchemy import func

from app.db.session import get_session
from app.models.db_models import Leader

router = APIRouter(prefix="/leaders", tags=["Leaders"])


class LeaderOut(BaseModel):
    id: str
    name: str
    city: str
    pincode: str


@router.get("", response_model=List[LeaderOut])
def search_leaders(
    city: Optional[str] = None,
    pincode: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """
    FR9 concerned-person dropdown: leaders whose jurisdiction matches the
    citizen-entered city/pincode. City match is case-insensitive; when a
    pincode is also given, an exact match within that city is preferred, but
    if nothing matches exactly the city-level results are returned instead
    of an empty list — no automated ward-matching (out of scope), just a
    reasonable starting set for the citizen to pick from. Results are sorted
    alphabetically by name (case-insensitive) so the list reads predictably
    regardless of how many leaders match — the frontend dropdown is also
    searchable, but a stable, alphabetical base order matters even then.
    """
    statement = select(Leader).order_by(func.lower(Leader.name))
    if city:
        statement = statement.where(Leader.city.ilike(f"%{city.strip()}%"))
    leaders = session.exec(statement).all()

    if pincode and pincode.strip():
        exact = [l for l in leaders if l.pincode == pincode.strip()]
        if exact:
            leaders = exact

    return [LeaderOut(id=str(l.id), name=l.name, city=l.city, pincode=l.pincode) for l in leaders]
