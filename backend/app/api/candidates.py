from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Candidate
router = APIRouter(prefix="/candidates", tags=["candidates"])

@router.get("")
def list_candidates(db: Session = Depends(get_db)):
    return [{"id": r.id, "hall_id": r.hall_id, "name": r.name, "ticket_no": r.ticket_no, "paper_id": r.paper_id}
            for r in db.scalars(select(Candidate).order_by(Candidate.id)).all()]
