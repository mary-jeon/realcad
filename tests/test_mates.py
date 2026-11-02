"""Mate assembly: features read from the B-rep, solver placement, measured mates, conflicts, planner retry."""
import math

import numpy as np
import pytest
import build123d as bd

from realcad.geometry import mates as M
from realcad import mate_assembly as MA

HOLES = [(-20, -12), (20, -12), (-20, 12), (20, 12)]


def base_with_posts():
    """60x40x3 base with four 6 mm posts, 8 mm tall, each with a 2.5 mm pilot hole."""
    base = bd.Box(60, 40, 3, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    for x, y in HOLES:
        post = bd.Pos(x, y, 3) * bd.Cylinder(3, 8, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        base = base + post - bd.Pos(x, y, 6) * bd.Cylinder(1.25, 5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return base


def board(spacing=(40, 24)):
    b = bd.Box(50, 30, 1.6, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    sx, sy = spacing[0] / 2, spacing[1] / 2
    for x, y in ((-sx, -sy), (sx, -sy), (-sx, sy), (sx, sy)):
        b = b - bd.Pos(x, y, 0) * bd.Cylinder(1.4, 1.6, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    b = b + bd.Pos(10, 0, 1.6) * bd.Box(12, 8, 6, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))  # a chip on top
    return b


def _board_mates():
    return [{"type": "concentric", "a": {"part": "base", "hole": [-20, -12], "dia": 2.5}, "b": {"part": "board", "hole": [-20, -12], "dia": 2.8}},
            {"type": "concentric", "a": {"part": "base", "hole": [20, 12], "dia": 2.5}, "b": {"part": "board", "hole": [20, 12], "dia": 2.8}},
            {"type": "coincident", "a": {"part": "base", "face": "+Z", "near": [-20, -12, 11]}, "b": {"part": "board", "face": "-Z"}}]


def test_features_find_holes_bosses_and_faces():
    f = M.features(base_with_posts())
    holes = [a for a in f["axes"] if a["kind"] == "hole"]
    bosses = [a for a in f["axes"] if a["kind"] == "boss"]
    assert len(holes) == 4 and all(abs(2 * a["r"] - 2.5) < 1e-6 for a in holes)
    assert len(bosses) == 4 and all(abs(2 * a["r"] - 6) < 1e-6 for a in bosses)
    tops = [p for p in f["planes"] if p["normal"][2] > 0.999 and abs(p["point"][2] - 11) < 1e-6]
    assert len(tops) == 4                                            # the four post tops
    t = M.feature_table(f)
    assert t["axes"][0]["id"].startswith("H") and t["planes"][0]["id"] == "P1"


def test_board_lands_on_posts_from_a_wrong_start():
    b = bd.Rot(0, 0, 90) * bd.Pos(30, -70, 25) * board()           # start far away and turned 90 degrees
    # selectors are in the part's own (moved) coordinates: map the two board holes through the same move
    def T(x, y):
        return [-(y - 70), x + 30]
    parts = [M.MatePart("base", base_with_posts(), 1), M.MatePart("board", b, 2)]
    mates = _board_mates()
    mates[0]["b"]["hole"] = T(-20, -12)
    mates[1]["b"]["hole"] = T(20, 12)
    r = M.solve(parts, mates)
    assert all(m["ok"] for m in r["mates"]) and r["unplaced"] == []
    placed = M.placed_shape(parts[1])
    want = bd.Pos(0, 0, 11) * board()
    bb, wb = placed.bounding_box(), want.bounding_box()
    assert np.allclose([bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z],
                       [wb.min.X, wb.min.Y, wb.min.Z, wb.max.X, wb.max.Y, wb.max.Z], atol=1e-6)
    assert (placed - want).volume < 1e-3                               # the same solid in the same place
    assert parts[1].dof == {"move_free": 0, "turn_free": 0}


def test_pipeline_checks_pass_and_files_write(tmp_path):
    parts = [M.MatePart("base", base_with_posts(), 1, spec="base", material="PLA"),
             M.MatePart("board", bd.Pos(5, 5, 30) * board(), 2, spec="board", material="FR4")]
    mates = _board_mates()
    mates[0]["b"]["hole"] = [-15, -7]; mates[1]["b"]["hole"] = [25, 17]
    res = MA.run(parts, mates=mates)
    codes = {f.code: f for f in res["findings"]}
    assert res["passed"] and codes["J1"].ok and codes["J2"].ok and codes["A1"].ok and codes["B1"].ok and codes["B2"].ok
    files = MA.write(res, tmp_path, "abcd1234")
    assert (tmp_path / "abcd1234.step").stat().st_size > 1000
    assert len(files["parts"]) == 2 and files["total_mass_g"] > 0
    back = bd.import_step(str(tmp_path / "abcd1234.step"))
    assert len(back.solids()) == 2


def test_hole_pattern_that_does_not_match_is_reported():
    parts = [M.MatePart("base", base_with_posts(), 1, spec="b", material="PLA"),
             M.MatePart("board", board(spacing=(44, 24)), 2, spec="c", material="FR4")]   # 44 mm apart, posts are 40
    mates = _board_mates()
    mates[0]["b"]["hole"] = [-22, -12]; mates[1]["b"]["hole"] = [22, 12]
    res = MA.run(parts, mates=mates)
    j1 = next(f for f in res["findings"] if f.code == "J1")
    assert not j1.ok and not res["passed"]
    assert max(m["error_mm"] for m in res["measured"]) > 1.0          # about 2 mm off on each hole


def test_board_pushed_into_posts_is_caught_as_interference():
    parts = [M.MatePart("base", base_with_posts(), 1, spec="b", material="PLA"),
             M.MatePart("board", board(), 2, spec="c", material="FR4")]
    mates = _board_mates()[:2] + [{"type": "distance", "a": {"part": "base", "face": "+Z", "near": [-20, -12, 11]},
                                   "b": {"part": "board", "face": "-Z"}, "value": -3}]
    res = MA.run(parts, mates=mates)
    a1 = next(f for f in res["findings"] if f.code == "A1")
    assert not a1.ok


def test_distance_flip_and_aligned():
    a = bd.Box(20, 20, 10, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    b = bd.Box(10, 10, 4)
    parts = [M.MatePart("a", a, 1), M.MatePart("b", b, 2)]
    r = M.solve(parts, [{"type": "distance", "a": "a:top", "b": "b:bottom", "value": 2.5}])
    assert r["mates"][0]["ok"]
    bb = M.placed_shape(parts[1]).bounding_box()
    assert abs(bb.min.Z - 12.5) < 1e-6
    assert parts[1].dof["move_free"] == 2 and parts[1].dof["turn_free"] == 1      # slides and spins on the face
    parts = [M.MatePart("a", a, 1), M.MatePart("b", b, 2)]
    r = M.solve(parts, [{"type": "coincident", "a": "a:+X", "b": "b:+X", "aligned": True}])
    bb = M.placed_shape(parts[1]).bounding_box()
    assert r["mates"][0]["ok"] and abs(bb.max.X - 10) < 1e-6           # flush with the right face


def test_pin_in_hole_concentric_with_flip():
    plate = bd.Box(30, 30, 5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)) - bd.Cylinder(3, 5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    pin = bd.Cylinder(3, 20, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)) + bd.Pos(0, 0, 20) * bd.Cylinder(5, 3, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    pin = bd.Pos(40, 10, 0) * bd.Rot(90, 0, 0) * pin                    # lying on its side somewhere else
    parts = [M.MatePart("plate", plate, 1), M.MatePart("pin", pin, 2)]
    head = M.features(pin)
    shoulder = next(p for p in head["planes"] if abs(p["area"] - math.pi * (25 - 9)) < 0.5)
    r = M.solve(parts, [{"type": "concentric", "a": "plate:H1", "b": {"part": "pin", "boss": None, "dia": 6}},
                        {"type": "coincident", "a": "plate:top", "b": "pin:" + shoulder["id"]}])
    assert all(m["ok"] for m in r["mates"])
    bb = M.placed_shape(parts[1]).bounding_box()
    assert abs(bb.min.Z - (5 - 20)) < 1e-6 and abs(bb.max.Z - 8) < 1e-6  # shaft goes down through the hole, head sits on top


def test_bad_mates_are_refused_with_a_reason():
    parts = [M.MatePart("a", bd.Box(10, 10, 10), 1), M.MatePart("b", bd.Box(5, 5, 5), 2)]
    with pytest.raises(M.MateError):
        M.solve(parts, [{"type": "concentric", "a": "a:top", "b": "b:bottom"}])
    with pytest.raises(M.MateError):
        M.solve(parts, [{"type": "coincident", "a": "a:P99", "b": "b:bottom"}])
    with pytest.raises(M.MateError):
        M.solve(parts, [{"type": "glue", "a": "a:top", "b": "b:bottom"}])


def test_instruction_retries_once_with_measurements(monkeypatch):
    from realcad.agent import mate_planner
    good = _board_mates()
    bad = [{"type": "concentric", "a": "base:H1", "b": "board:H4"},          # wrong corner: pattern does not line up
           {"type": "concentric", "a": "base:H4", "b": "board:H4"},
           {"type": "coincident", "a": {"part": "base", "face": "+Z", "near": [-20, -12, 11]}, "b": {"part": "board", "face": "-Z"}}]
    seen = []

    def fake(instruction, tables, feedback=""):
        seen.append(feedback)
        return {"mates": bad if len(seen) == 1 else good, "why": "보드를 기둥 위에"}
    monkeypatch.setattr(mate_planner, "plan", fake)
    parts = [M.MatePart("base", base_with_posts(), 1, spec="b", material="PLA"), M.MatePart("board", board(), 2, spec="c", material="FR4")]
    res = MA.run(parts, instruction="보드를 기둥에 올려")
    assert res["tries"] == 2 and res["passed"] and "error" in seen[1]


def _three(c_far=True):
    a = bd.Box(100, 100, 10)
    b = bd.Box(20, 20, 5)
    c = bd.Pos(300, 0, 0) * bd.Box(10, 10, 10)
    return a, b, c


def test_unconnected_part_fails_and_is_not_called_fully_defined():
    a, b, c = _three()
    parts = [M.MatePart("a", a, 1, spec="s", material="PLA"), M.MatePart("b", b, 2, spec="s", material="PLA"),
             M.MatePart("c", c, 3, spec="s", material="PLA")]
    res = MA.run(parts, mates=[{"type": "coincident", "a": "a:top", "b": "b:bottom"},
                               {"type": "coincident", "a": "a:+X", "b": "b:+X", "aligned": True},
                               {"type": "coincident", "a": "a:+Y", "b": "b:+Y", "aligned": True}])
    j3 = next(f for f in res["findings"] if f.code == "J3")
    assert not j3.ok and j3.severity == "HARD" and not res["passed"] and res["unplaced"] == ["c"]
    assert M.dof_text(parts[2].dof).startswith("메이트 없음")


def test_same_concentric_twice_does_not_lock_the_spin():
    parts = [M.MatePart("a", bd.Cylinder(5, 20), 1), M.MatePart("b", bd.Pos(50, 0, 0) * bd.Cylinder(5, 10), 2)]
    r = M.solve(parts, [{"type": "concentric", "a": "a:B1", "b": "b:B1"}, {"type": "concentric", "a": "a:B1", "b": "b:B1"},
                        {"type": "coincident", "a": "a:top", "b": "b:bottom"}])
    assert all(m["ok"] for m in r["mates"]) and r["mates"][1].get("duplicate")
    assert parts[1].dof == {"move_free": 0, "turn_free": 1}           # still spins on its axis


def test_only_one_fixed_part():
    parts = [M.MatePart("a", bd.Box(10, 10, 10), 1, fixed=True), M.MatePart("b", bd.Box(5, 5, 5), 2, fixed=True)]
    with pytest.raises(M.MateError, match="하나만"):
        M.solve(parts, [{"type": "coincident", "a": "a:top", "b": "b:bottom"}])


def test_part_that_hangs_on_two_others_waits_for_both():
    # b sits on a and is pushed against c; c is fully placed on a. In the order a, b, c the solver must place c first.
    a, b, c = _three()
    parts = [M.MatePart("a", a, 1), M.MatePart("b", b, 2), M.MatePart("c", c, 3)]
    mates = [{"type": "coincident", "a": "a:top", "b": "b:bottom"},
             {"type": "coincident", "a": "c:-X", "b": "b:+X"},
             {"type": "coincident", "a": "c:+Y", "b": "b:+Y", "aligned": True},
             {"type": "coincident", "a": "a:top", "b": "c:bottom"},
             {"type": "coincident", "a": "a:+X", "b": "c:+X", "aligned": True},
             {"type": "coincident", "a": "a:+Y", "b": "c:+Y", "aligned": True}]
    r = M.solve(parts, mates)
    assert all(m["ok"] for m in r["mates"]), r["mates"]
    bb, cb = M.placed_shape(parts[1]).bounding_box(), M.placed_shape(parts[2]).bounding_box()
    assert abs(bb.max.X - cb.min.X) < 1e-6 and abs(bb.max.Y - cb.max.Y) < 1e-6
    assert parts[1].dof == {"move_free": 0, "turn_free": 0}


def test_planner_answer_without_a_b_gets_another_try(monkeypatch):
    from realcad.agent import mate_planner
    with pytest.raises(ValueError):
        mate_planner._parse('{"mates": [{}]}')
    seen = []

    def fake(instruction, tables, feedback=""):
        seen.append(feedback)
        if len(seen) == 1:
            raise ValueError("메이트 1번에 type, a, b 가 다 있어야 해요")
        return {"mates": _board_mates(), "why": "ok"}
    monkeypatch.setattr(mate_planner, "plan", fake)
    parts = [M.MatePart("base", base_with_posts(), 1, spec="b", material="PLA"), M.MatePart("board", board(), 2, spec="c", material="FR4")]
    res = MA.run(parts, instruction="보드를 기둥에 올려")
    assert res["tries"] == 2 and res["passed"] and "refused" in seen[1]
