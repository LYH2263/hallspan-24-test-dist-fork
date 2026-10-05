from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Hall
router = APIRouter(prefix="/halls", tags=["halls"])

class HallUpdate(BaseModel):
    min_manhattan: int | None = Field(default=None, ge=1)

def hall_dict(h: Hall) -> dict:
    return {"id": h.id, "code": h.code, "name": h.name, "rows": h.rows, "cols": h.cols, "min_manhattan": h.min_manhattan}

@router.get("")
def list_halls(db: Session = Depends(get_db)):
    return [hall_dict(r) for r in db.scalars(select(Hall).order_by(Hall.id)).all()]

@router.patch("/{hall_id}")
def update_hall(hall_id: int, payload: HallUpdate, db: Session = Depends(get_db)):
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    if payload.min_manhattan is not None:
        hall.min_manhattan = payload.min_manhattan
    db.commit()
    db.refresh(hall)
    return hall_dict(hall)
