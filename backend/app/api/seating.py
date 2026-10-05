import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Candidate, Hall, SeatPlan
from app.services.seat_engine import find_violations, place_candidates, plan_to_dict

router = APIRouter(prefix="/seating", tags=["seating"])


def _run_and_persist(hall: Hall, cands: list[dict], db: Session) -> dict:
    assigns, unplaced = place_candidates(hall.rows, hall.cols, hall.min_manhattan, cands)
    viols = find_violations(hall.rows, hall.cols, hall.min_manhattan, assigns)
    result = plan_to_dict(assigns, unplaced, viols, hall.rows, hall.cols)
    result["hall"] = {"id": hall.id, "name": hall.name, "min_manhattan": hall.min_manhattan}
    plan = SeatPlan(hall_id=hall.id, created_at=datetime.utcnow(),
                    result_json=json.dumps(result, ensure_ascii=False))
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return {"id": plan.id, **result}


@router.post("/run")
def run_seating(hall_id: int = 1, db: Session = Depends(get_db)):
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    cands = [{"id": c.id, "name": c.name, "ticket_no": c.ticket_no, "paper_id": c.paper_id}
             for c in db.scalars(select(Candidate).where(Candidate.hall_id == hall_id)).all()]
    return _run_and_persist(hall, cands, db)


@router.get("/latest")
def latest(hall_id: int = 1, db: Session = Depends(get_db)):
    """只读最新方案。无方案时返回 404，绝不隐式排座写库。"""
    plan = db.scalars(
        select(SeatPlan).where(SeatPlan.hall_id == hall_id).order_by(SeatPlan.id.desc())
    ).first()
    if not plan:
        raise HTTPException(404, "该考室暂无排座方案")
    data = json.loads(plan.result_json)
    return {"id": plan.id, **data}


@router.get("/violations")
def violations(hall_id: int = 1, db: Session = Depends(get_db)):
    data = latest(hall_id=hall_id, db=db)
    return {"hall_id": hall_id, "violations": data.get("violations", []), "unplaced": data.get("unplaced", [])}


@router.get("/stats")
def stats(hall_id: int = 1, db: Session = Depends(get_db)):
    data = latest(hall_id=hall_id, db=db)
    return {"hall_id": hall_id, **data.get("stats", {})}


@router.get("/{plan_id}")
def get_plan(plan_id: int, hall_id: int = 1, db: Session = Depends(get_db)):
    """按编号只读历史方案行；不存在（或不属于该考室）一律 404，不新增任何方案行。"""
    plan = db.get(SeatPlan, plan_id)
    if not plan or plan.hall_id != hall_id:
        raise HTTPException(404, "方案不存在")
    data = json.loads(plan.result_json)
    return {"id": plan.id, **data}
