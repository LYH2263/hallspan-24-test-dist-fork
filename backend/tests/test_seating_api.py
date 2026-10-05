"""串行锁定：改距接口 -> 再排接口 -> 历史方案行读取，锁住新旧分岔。

数据设计（2 行 x 3 列，3 名考生，全部同一套卷）：
  min_manhattan=2 首排：贪心落位 (0,0)(0,2)(1,1)，两两距离恰为 2，全部座满、零违规；
  改距为 3 后再排：只能容下 (0,0)(1,2)（距离 3），第 3 人进未排——
  旧行里那三对「距离 2」在新距下本应判违规，但旧行全文必须一字不改。

所有关于数据库的断言都重新开一个 Session 回读，禁止只断言响应内存。
"""
import json

from sqlalchemy import func, select

from app.models.models import Candidate, Hall, PaperSet, SeatPlan
from app.services.seat_engine import (
    SeatAssign,
    Violation,
    find_violations,
    manhattan,
)


def _seed_hall(db_factory, code="H101", rows=2, cols=3, n_cands=3, min_dist=2):
    db = db_factory()
    paper = PaperSet(code=f"P-{code}", title=f"卷-{code}")
    hall = Hall(code=code, name=f"考室-{code}", rows=rows, cols=cols, min_manhattan=min_dist)
    db.add_all([paper, hall])
    db.flush()
    for i in range(n_cands):
        db.add(Candidate(hall_id=hall.id, name=f"{code}-考生{i+1}",
                         ticket_no=f"{code}-T{i+1}", paper_id=paper.id))
    db.commit()
    hid = hall.id
    db.close()
    return hid


def _plan_count(db_factory, hall_id):
    db = db_factory()
    try:
        return db.scalar(
            select(func.count()).select_from(SeatPlan).where(SeatPlan.hall_id == hall_id)
        )
    finally:
        db.close()


def _fetch_row(db_factory, plan_id):
    """新开 session 从库里读方案行（拿的是持久化快照，不是响应内存）。"""
    db = db_factory()
    try:
        return db.get(SeatPlan, plan_id)
    finally:
        db.close()


def _candidate_count(db_factory, hall_id):
    db = db_factory()
    try:
        return db.scalar(
            select(func.count()).select_from(Candidate).where(Candidate.hall_id == hall_id)
        )
    finally:
        db.close()


def _ids(entries):
    return {e.get("candidate_id", e.get("id")) for e in entries}


def test_change_distance_then_rerun_forks_plan_rows(client, db_factory):
    hid = _seed_hall(db_factory)
    room_total = _candidate_count(db_factory, hid)

    # ---- 首排（旧距 2），立刻从库里记下编号与全文 ----
    r1 = client.post(f"/api/seating/run?hall_id={hid}")
    assert r1.status_code == 200
    old_id = r1.json()["id"]
    assert _plan_count(db_factory, hid) == 1

    old_row = _fetch_row(db_factory, old_id)
    old_full_text = old_row.result_json           # 库里的原始字符串，存档
    old = json.loads(old_full_text)
    assert old["hall"]["min_manhattan"] == 2
    assert old["stats"]["seated"] == 3
    assert old["stats"]["unplaced"] == 0
    assert old["violations"] == []
    old_seated_ids = _ids(old["assignments"])

    # 已座编号 ∩ 未排编号 = ∅；已座人数 + 未排人数 = 该室考生数
    assert old_seated_ids.isdisjoint(_ids(old["unplaced"]))
    assert old["stats"]["seated"] + old["stats"]["unplaced"] == room_total

    # 旧行座位两两距离恰为 2：旧距下合法；若全表按新距 3 回刷则必出 3 条 distance 违规
    old_assigns = [SeatAssign(**a) for a in old["assignments"]]
    assert find_violations(2, 3, 2, old_assigns) == []
    rejudged_at_new = find_violations(2, 3, 3, old_assigns)
    assert len(rejudged_at_new) == 3
    assert all(v.kind == "distance" and "最小要求 3" in v.detail for v in rejudged_at_new)

    # ---- 改距接口：2 -> 3，只改考室当前参数（落库断言）----
    pu = client.put(f"/api/halls/{hid}/min-distance", json={"min_manhattan": 3})
    assert pu.status_code == 200
    assert pu.json()["min_manhattan"] == 3
    db = db_factory()
    assert db.get(Hall, hid).min_manhattan == 3
    db.close()

    # ---- 再排接口：方案表必须恰好多一行 ----
    r2 = client.post(f"/api/seating/run?hall_id={hid}")
    assert r2.status_code == 200
    new = r2.json()
    new_id = new["id"]
    assert new_id > old_id
    assert _plan_count(db_factory, hid) == 2       # 追加，而非覆盖/回刷

    # ---- 历史方案行：旧行全文一字不改（从库里按编号读回原始字符串）----
    reread_old_row = _fetch_row(db_factory, old_id)
    assert reread_old_row.hall_id == hid
    assert reread_old_row.result_json == old_full_text

    # 历史方案只读接口按编号取回的仍是旧快照（hall 块里仍嵌着旧距 2）
    g = client.get(f"/api/seating/{old_id}?hall_id={hid}")
    assert g.status_code == 200
    old_via_api = g.json()
    assert old_via_api["id"] == old_id
    old_via_api.pop("id")
    assert old_via_api == json.loads(old_full_text)
    assert old_via_api["hall"]["min_manhattan"] == 2

    # ---- 新行违规按新距：库里新行内嵌的违规清单 == 用新距 3 对新行座位重算 ----
    assert new["hall"]["min_manhattan"] == 3
    new_assigns = [SeatAssign(**a) for a in new["assignments"]]
    expected_viols = find_violations(2, 3, 3, new_assigns)
    assert [Violation(**v) for v in new["violations"]] == expected_viols

    # 新距确实更紧：2 座 + 1 未排，新行任意两座距离 >= 3
    assert new["stats"]["seated"] == 2
    assert new["stats"]["unplaced"] == 1
    for i, a in enumerate(new_assigns):
        for b in new_assigns[i + 1:]:
            assert manhattan((a.row, a.col), (b.row, b.col)) >= 3

    # 新行同样：编号不交集 + 人数守恒（对库中新行断言）
    new_stored = json.loads(_fetch_row(db_factory, new_id).result_json)
    assert _ids(new_stored["assignments"]).isdisjoint(_ids(new_stored["unplaced"]))
    assert new_stored["stats"]["seated"] + new_stored["stats"]["unplaced"] == room_total

    # 新旧已座集合必须真的分岔，否则再排没有按新距重算
    assert _ids(new_stored["assignments"]) != old_seated_ids

    # latest 指向新行；两行同在，旧行依旧原封不动 —— 禁止整表删光/全表回刷
    latest = client.get(f"/api/seating/latest?hall_id={hid}")
    assert latest.status_code == 200
    assert latest.json()["id"] == new_id
    assert _plan_count(db_factory, hid) == 2
    assert _fetch_row(db_factory, old_id).result_json == old_full_text


def test_latest_without_plan_is_readonly_404(client, db_factory):
    hid = _seed_hall(db_factory)
    assert _plan_count(db_factory, hid) == 0

    r = client.get(f"/api/seating/latest?hall_id={hid}")
    assert r.status_code == 404
    assert _plan_count(db_factory, hid) == 0       # 无方案时只读最新不得写入

    # 下游只读端点同样不得借 latest 隐式排座
    assert client.get(f"/api/seating/violations?hall_id={hid}").status_code == 404
    assert client.get(f"/api/seating/stats?hall_id={hid}").status_code == 404
    assert _plan_count(db_factory, hid) == 0


def test_run_and_read_nonexistent_hall_create_no_rows(client, db_factory):
    assert client.post("/api/seating/run?hall_id=9999").status_code == 404
    assert client.get("/api/seating/latest?hall_id=9999").status_code == 404

    db = db_factory()
    try:
        assert db.scalar(select(func.count()).select_from(SeatPlan)) == 0
    finally:
        db.close()


def test_read_nonexistent_or_other_room_plan_creates_no_row(client, db_factory):
    hid = _seed_hall(db_factory, code="H101")
    other = _seed_hall(db_factory, code="H202", n_cands=1)

    # 不存在的方案编号：404，且不增行
    assert client.get(f"/api/seating/424242?hall_id={hid}").status_code == 404
    assert _plan_count(db_factory, hid) == 0

    # 真实方案但属于别的考室：串室读取 404，不给本室凭空加行
    made = client.post(f"/api/seating/run?hall_id={other}").json()["id"]
    assert client.get(f"/api/seating/{made}?hall_id={hid}").status_code == 404
    assert _plan_count(db_factory, hid) == 0
    assert _plan_count(db_factory, other) == 1


def test_change_distance_rejects_invalid_and_keeps_history(client, db_factory):
    hid = _seed_hall(db_factory)
    client.post(f"/api/seating/run?hall_id={hid}")
    before = _plan_count(db_factory, hid)

    assert client.put(f"/api/halls/{hid}/min-distance", json={"min_manhattan": 0}).status_code == 422
    db = db_factory()
    assert db.get(Hall, hid).min_manhattan == 2    # 非法改距不落库
    db.close()

    assert client.put("/api/halls/9999/min-distance", json={"min_manhattan": 3}).status_code == 404
    assert _plan_count(db_factory, hid) == before  # 失败的改距不动方案表
