from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import PaperSet
router = APIRouter(prefix="/papers", tags=["papers"])

@router.get("")
def list_papers(db: Session = Depends(get_db)):
    return [{"id": r.id, "code": r.code, "title": r.title}
            for r in db.scalars(select(PaperSet).order_by(PaperSet.id)).all()]
