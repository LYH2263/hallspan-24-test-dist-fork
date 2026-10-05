"""改距 → 再排 → 历史方案行：锁住新旧分岔。

串三处：PATCH /halls/{id}（改距接口）、POST /seating/run（再排接口）、
seat_plans 表与 GET /seating/latest（历史方案行）。

纪律：所有库断言都开独立会话直查 seat_plans；不删任何行、不整表清空；
每个测例用全新 sqlite 库文件做隔离，而不是删表装绿。
"""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.models import Candidate, Hall, PaperSet, SeatPlan

MISSING_HALL_ID = 999999


class Env:
    def __init__(self, session_factory, client):
        self.Session = session_factory
        self.client = client


@pytest.fixture()
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield Env(TestSession, TestClient(app))
    app.dependency_overrides.clear()
    engine.dispose()


def make_hall(env, *, rows, cols, min_manhattan, n_candidates, n_papers=2):
    """直接落库造考室+试卷+考生（不经被测接口），返回 hall_id。"""
    with env.Session() as db:
        hall = Hall(code="H-T", name="测试考室", rows=rows, cols=cols,
                    min_manhattan=min_manhattan)
        db.add(hall)
        db.flush()
        paper_ids = []
        for i in range(n_papers):
            p = PaperSet(code=f"PS-{i}", title=f"试卷{i}")
            db.add(p)
            db.flush()
            paper_ids.append(p.id)
        for i in range(n_candidates):
            db.add(Candidate(hall_id=hall.id, name=f"考生{i:02d}",
                             ticket_no=f"T{i:04d}",
                             paper_id=paper_ids[i % n_papers]))
        db.commit()
        return hall.id


def plan_rows(env, hall_id):
    """独立会话直查 seat_plans，按 id 升序返回 [(id, result_json), ...]。"""
    with env.Session() as db:
        return [(p.id, p.result_json) for p in db.scalars(
            select(SeatPlan).where(SeatPlan.hall_id == hall_id)
            .order_by(SeatPlan.id)).all()]


def plan_count(env, hall_id=None):
    with env.Session() as db:
        q = select(func.count()).select_from(SeatPlan)
        if hall_id is not None:
            q = q.where(SeatPlan.hall_id == hall_id)
        return db.scalar(q)


def hall_candidate_ids(env, hall_id):
    with env.Session() as db:
        return set(db.scalars(
            select(Candidate.id).where(Candidate.hall_id == hall_id)).all())


def manhattan(a, b):
    return abs(a["row"] - b["row"]) + abs(a["col"] - b["col"])


def pairs(assigns):
    for i, a in enumerate(assigns):
        for b in assigns[i + 1:]:
            yield a, b


def recompute_violations(rows, cols, min_dist, assigns):
    """按引擎同一套规则独立重算违规（含文案与顺序），用于比对库中快照。"""
    out = []
    for a, b in pairs(assigns):
        d = manhattan(a, b)
        if d < min_dist:
            out.append({"kind": "distance",
                        "a_id": a["candidate_id"], "b_id": b["candidate_id"],
                        "detail": f"曼哈顿距离 {d} < 最小要求 {min_dist}"})
        if a["paper_id"] == b["paper_id"] and d == 1:
            out.append({"kind": "same_paper_adjacent",
                        "a_id": a["candidate_id"], "b_id": b["candidate_id"],
                        "detail": f"同试卷套 {a['paper_id']} 四邻相邻"})
    return out


def test_change_distance_then_rerun_forks_history(env):
    """改距→再排→历史行：方案表恰多一行，新行按新距，旧行一字不改。"""
    hall_id = make_hall(env, rows=4, cols=4, min_manhattan=1, n_candidates=6)

    # 1) 先排一版，记下编号与全文（全文取库中原文，不是接口返回）
    r1 = env.client.post("/api/seating/run", params={"hall_id": hall_id})
    assert r1.status_code == 200
    plan1_id = r1.json()["id"]
    rows1 = plan_rows(env, hall_id)
    assert [pid for pid, _ in rows1] == [plan1_id]
    plan1_text = rows1[0][1]
    plan1 = json.loads(plan1_text)
    assert plan1["hall"]["min_manhattan"] == 1
    # 接口返回必须与库中全文一致（不允许只改内存不落库）
    assert plan1 == {k: v for k, v in r1.json().items() if k != "id"}
    assert plan1["violations"] == recompute_violations(4, 4, 1, plan1["assignments"])
    # 旧距下必存在距离 <3 的相邻对——否则“旧行未被新距回刷”无从验证
    assert any(manhattan(a, b) < 3 for a, b in pairs(plan1["assignments"]))

    # 2) 改距接口：最小距 1 → 3。改距本身不得新增方案行、不得回刷旧行
    r = env.client.patch(f"/api/halls/{hall_id}", json={"min_manhattan": 3})
    assert r.status_code == 200 and r.json()["min_manhattan"] == 3
    halls = env.client.get("/api/halls").json()
    assert [h for h in halls if h["id"] == hall_id][0]["min_manhattan"] == 3
    assert plan_rows(env, hall_id) == rows1

    # 3) 再排接口
    r2 = env.client.post("/api/seating/run", params={"hall_id": hall_id})
    assert r2.status_code == 200
    plan2_id = r2.json()["id"]
    assert plan2_id != plan1_id

    # 4) 历史方案行：必须恰好多一行，且新行 id 更大
    rows2 = plan_rows(env, hall_id)
    assert [pid for pid, _ in rows2] == [plan1_id, plan2_id]

    # 5) 旧行全文一字不改——锁死「改距只动最新」，与「全表按新距回刷」互斥
    assert rows2[0][1] == plan1_text
    # 正向证伪回刷：旧行座位若按新距重算违规，结果必非空，与库中旧值不同
    assert recompute_violations(4, 4, 3, plan1["assignments"]) != plan1["violations"]

    # 6) 新行按新距：快照记新距、座位两两满足新距、违规与按新距重算一致
    plan2 = json.loads(rows2[1][1])
    assert plan2["hall"]["min_manhattan"] == 3
    assert plan2 == {k: v for k, v in r2.json().items() if k != "id"}
    assert all(manhattan(a, b) >= 3 for a, b in pairs(plan2["assignments"]))
    assert plan2["violations"] == recompute_violations(4, 4, 3, plan2["assignments"])

    # 7) 只读最新应读到新行，且与库中新行全文一致
    latest = env.client.get("/api/seating/latest", params={"hall_id": hall_id})
    assert latest.status_code == 200
    assert latest.json()["id"] == plan2_id
    assert {k: v for k, v in latest.json().items() if k != "id"} == plan2


def test_seated_and_unplaced_partition_candidates(env):
    """已座编号与未排编号无交集；已座数+未排数 == 该室考生数。"""
    hall_id = make_hall(env, rows=4, cols=4, min_manhattan=3, n_candidates=6)
    r = env.client.post("/api/seating/run", params={"hall_id": hall_id})
    assert r.status_code == 200
    rows = plan_rows(env, hall_id)
    assert [pid for pid, _ in rows] == [r.json()["id"]]
    plan = json.loads(rows[0][1])

    seated_ids = {a["candidate_id"] for a in plan["assignments"]}
    unplaced_ids = {u["id"] for u in plan["unplaced"]}
    db_ids = hall_candidate_ids(env, hall_id)

    # 数据必须真的盖住“有人未排上”分支，否则划分断言形同虚设
    assert seated_ids and unplaced_ids
    # 已座与未排不得有交集
    assert seated_ids.isdisjoint(unplaced_ids)
    # 已座人数 + 未排人数 == 该室考生数，且编号并集恰为该室考生全集
    assert len(seated_ids) + len(unplaced_ids) == len(db_ids)
    assert seated_ids | unplaced_ids == db_ids
    # 统计口径与名单一致
    assert plan["stats"]["seated"] == len(seated_ids)
    assert plan["stats"]["unplaced"] == len(unplaced_ids)


def test_missing_hall_never_adds_plan_rows(env):
    """不存在的考室：排座或读取都 404，且方案表不得增加任何行。"""
    hall_id = make_hall(env, rows=3, cols=3, min_manhattan=1, n_candidates=3)
    assert env.client.post("/api/seating/run", params={"hall_id": hall_id}).status_code == 200
    before_total = plan_count(env)
    assert before_total > 0  # 表非空时断言才有力，防“空表恒绿”
    assert plan_count(env, MISSING_HALL_ID) == 0

    # 必须断言 detail 文案：路由不存在的 404 是 "Not Found"，不能混为一谈
    r = env.client.post("/api/seating/run", params={"hall_id": MISSING_HALL_ID})
    assert r.status_code == 404 and r.json()["detail"] == "考室不存在"
    r = env.client.get("/api/seating/latest", params={"hall_id": MISSING_HALL_ID})
    assert r.status_code == 404 and r.json()["detail"] == "考室不存在"
    r = env.client.get("/api/seating/violations", params={"hall_id": MISSING_HALL_ID})
    assert r.status_code == 404 and r.json()["detail"] == "考室不存在"
    r = env.client.get("/api/seating/stats", params={"hall_id": MISSING_HALL_ID})
    assert r.status_code == 404 and r.json()["detail"] == "考室不存在"
    r = env.client.patch(f"/api/halls/{MISSING_HALL_ID}", json={"min_manhattan": 2})
    assert r.status_code == 404 and r.json()["detail"] == "考室不存在"

    assert plan_count(env) == before_total
    assert plan_count(env, MISSING_HALL_ID) == 0


def test_latest_without_plan_is_readonly(env):
    """无方案时只读最新不得写入：重复读仍 404，方案表保持 0 行。"""
    hall_id = make_hall(env, rows=3, cols=3, min_manhattan=1, n_candidates=3)
    assert plan_count(env, hall_id) == 0

    for _ in range(2):  # 重复只读，幂等且不写入
        # detail 必须是“暂无排座方案”，而不是路由不存在的 "Not Found"
        r = env.client.get("/api/seating/latest", params={"hall_id": hall_id})
        assert r.status_code == 404 and r.json()["detail"] == "暂无排座方案"
        r = env.client.get("/api/seating/violations", params={"hall_id": hall_id})
        assert r.status_code == 404 and r.json()["detail"] == "暂无排座方案"
        r = env.client.get("/api/seating/stats", params={"hall_id": hall_id})
        assert r.status_code == 404 and r.json()["detail"] == "暂无排座方案"
        assert plan_count(env, hall_id) == 0
        assert plan_count(env) == 0
