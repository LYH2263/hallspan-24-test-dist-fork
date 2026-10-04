"""Exam seating: min Manhattan distance; same paper_id cannot be 4-neighbor adjacent."""
from __future__ import annotations
from dataclasses import asdict, dataclass

@dataclass
class SeatAssign:
    candidate_id: int
    name: str
    ticket_no: str
    paper_id: int
    row: int
    col: int

@dataclass
class Violation:
    kind: str
    a_id: int
    b_id: int
    detail: str

def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def neighbors4(r: int, c: int, rows: int, cols: int) -> list[tuple[int, int]]:
    out = []
    for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            out.append((nr, nc))
    return out

def place_candidates(rows: int, cols: int, min_dist: int, candidates: list[dict]) -> tuple[list[SeatAssign], list[dict]]:
    """Greedy: try seats row-major; accept if manhattan >= min_dist to all placed AND no same paper 4-neigh."""
    occupied: dict[tuple[int, int], SeatAssign] = {}
    unplaced: list[dict] = []
    for cand in candidates:
        placed = False
        for r in range(rows):
            for c in range(cols):
                if (r, c) in occupied:
                    continue
                ok = True
                for pos, other in occupied.items():
                    if manhattan((r, c), pos) < min_dist:
                        ok = False
                        break
                    if other.paper_id == cand["paper_id"] and (r, c) in neighbors4(pos[0], pos[1], rows, cols):
                        ok = False
                        break
                if not ok:
                    continue
                # also check 4-neigh same paper against current neighbors
                for nr, nc in neighbors4(r, c, rows, cols):
                    if (nr, nc) in occupied and occupied[(nr, nc)].paper_id == cand["paper_id"]:
                        ok = False
                        break
                if not ok:
                    continue
                assign = SeatAssign(cand["id"], cand["name"], cand["ticket_no"], cand["paper_id"], r, c)
                occupied[(r, c)] = assign
                placed = True
                break
            if placed:
                break
        if not placed:
            unplaced.append(cand)
    return list(occupied.values()), unplaced

def find_violations(rows: int, cols: int, min_dist: int, assigns: list[SeatAssign]) -> list[Violation]:
    viols: list[Violation] = []
    by_pos = {(a.row, a.col): a for a in assigns}
    for i, a in enumerate(assigns):
        for b in assigns[i + 1:]:
            d = manhattan((a.row, a.col), (b.row, b.col))
            if d < min_dist:
                viols.append(Violation("distance", a.candidate_id, b.candidate_id,
                                       f"曼哈顿距离 {d} < 最小要求 {min_dist}"))
            if a.paper_id == b.paper_id and (b.row, b.col) in neighbors4(a.row, a.col, rows, cols):
                viols.append(Violation("same_paper_adjacent", a.candidate_id, b.candidate_id,
                                       f"同试卷套 {a.paper_id} 四邻相邻"))
    return viols

def plan_to_dict(assigns: list[SeatAssign], unplaced: list[dict], viols: list[Violation], rows: int, cols: int) -> dict:
    return {
        "rows": rows,
        "cols": cols,
        "assignments": [asdict(a) for a in assigns],
        "unplaced": unplaced,
        "violations": [asdict(v) for v in viols],
        "stats": {
            "seated": len(assigns),
            "unplaced": len(unplaced),
            "violations": len(viols),
            "capacity": rows * cols,
        },
    }
