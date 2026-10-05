from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Hall

router = APIRouter(prefix="/halls", tags=["halls"])


class MinDistanceUpdate(BaseModel):
    min_manhattan: int


@router.get("")
def list_halls(db: Session = Depends(get_db)):
    return [{"id": r.id, "code": r.code, "name": r.name, "rows": r.rows, "cols": r.cols, "min_manhattan": r.min_manhattan}
            for r in db.scalars(select(Hall).order_by(Hall.id)).all()]


@router.put("/{hall_id}/min-distance")
def update_min_distance(hall_id: int, payload: MinDistanceUpdate, db: Session = Depends(get_db)):
    """改距只影响此后新排的方案；历史方案行快照一律不回刷。"""
    if payload.min_manhattan < 1:
        raise HTTPException(422, "最小曼哈顿距离必须 >= 1")
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    hall.min_manhattan = payload.min_manhattan
    db.commit()
    db.refresh(hall)
    return {"id": hall.id, "code": hall.code, "name": hall.name,
            "rows": hall.rows, "cols": hall.cols, "min_manhattan": hall.min_manhattan}
