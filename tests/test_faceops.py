"""Face push/pull: only the picked face moves, neighboring wall height is measured on the kernel, and instruction rules branch correctly."""
from pathlib import Path

import pytest

from realcad.agent import faceops, sandbox

# Base plate (40x30x5) with a wall (height 15, top edge fillet 1) on the left half only + one hole in the right plate
CODE = """from build123d import *
plate = Box(40, 30, 5, align=(Align.MIN, Align.MIN, Align.MIN))
wall = Pos(0, 0, 5) * Box(20, 30, 10, align=(Align.MIN, Align.MIN, Align.MIN))
body = plate + wall
body = fillet(body.edges().filter_by(lambda e: abs(e.center().Z - 15) < 1e-3 and e.length > 25), 1.0)
body -= Pos(30, 15, 0) * Cylinder(3, 20)
part = body
"""
FACE = [{"point": [26.0, 5.0, 5.0], "normal": [0, 0, 1]}]


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    d = tmp_path_factory.mktemp("fo")
    sandbox.execute_to_files(CODE, d / "a.stl", d / "a.step")
    return d


def test_analyze_finds_face_and_wall_top_through_fillet(base):
    info = faceops.analyze(base / "a.step", FACE)
    assert info[0]["ok"] and info[0]["level"] == pytest.approx(5.0)
    assert info[0]["beside"] == [15.0]          # the wall face ends at 14 but snaps to the top plane at 15


@pytest.mark.parametrize("text,op,move", [
    ("옆 벽 높이까지 올려줘", "push", 10.0),
    ("3mm 올려줘", "push", 3.0),
    ("2 mm 파줘", "cut", -2.0),
    ("높이 12까지 올려", "push", 7.0),
])
def test_plan_rules(base, text, op, move):
    info = faceops.analyze(base / "a.step", FACE)
    p = faceops.plan(text, info)
    assert p["op"] == op
    assert faceops.distances(p, info)[0] == pytest.approx(move)


def test_hole_words_skip_rules(base, monkeypatch):
    info = faceops.analyze(base / "a.step", FACE)
    monkeypatch.setattr(faceops, "_plan_llm", lambda t, ok: {"op": "none", "how": "llm"})
    assert faceops.plan("지름 5 구멍 파줘", info)["how"] == "llm"


def test_push_moves_only_that_face_and_keeps_hole(base):
    info = faceops.analyze(base / "a.step", FACE)
    p = faceops.plan("옆 벽 높이까지 올려줘", info)
    code = faceops.append_code(CODE, info, faceops.distances(p, info), p["how"])
    r = sandbox.execute_to_files(code, base / "b.stl", base / "b.step")
    assert r["bbox"] == pytest.approx([40.0, 30.0, 15.0], abs=0.05)
    # The hole (diameter 6) must stay open through the raised part: volume = 40x30x15 - fillet - hole column
    full = 40 * 30 * 15 - 3.14159 * 9 * 15
    assert r["volume"] == pytest.approx(full, rel=0.01)


def test_flush_request_when_no_higher_wall_is_noop(tmp_path):
    code = "from build123d import *\npart = Box(20, 20, 5)\n"
    sandbox.execute_to_files(code, tmp_path / "a.stl", tmp_path / "a.step")
    info = faceops.analyze(tmp_path / "a.step", [{"point": [0, 0, 2.5], "normal": [0, 0, 1]}])
    assert faceops.plan("옆 벽 높이까지 올려줘", info)["op"] == "noop"


def test_ledge_inside_counterbore_goes_to_surrounding_level(tmp_path):
    """If no attached wall rises above (like a ledge inside a hole), snap to the nearest higher face around it (plate top)."""
    code = ("from build123d import *\n"
            "b = Box(30, 30, 5, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
            "b -= Pos(0, 0, 3.5) * Cylinder(5.5, 3)\n"          # counterbore (floor z=2)
            "b += Pos(0, 0, 2.5) * Cylinder(3, 1)\n"            # ledge (top z=3)
            "b -= Cylinder(1.5, 20)\n"
            "part = b\n")
    sandbox.execute_to_files(code, tmp_path / "a.stl", tmp_path / "a.step")
    info = faceops.analyze(tmp_path / "a.step", [{"point": [2.2, 0, 3], "normal": [0, 0, 1]}])
    assert info[0]["ok"] and info[0]["level"] == pytest.approx(3.0)
    p = faceops.plan("턱을 옆 높이까지 올려줘", info)
    assert p["op"] == "push" and faceops.distances(p, info)[0] == pytest.approx(2.0)


def test_flush_push_fills_fillet_seam(base):
    """Even with a rounded top edge on the neighboring wall (fillet 1), no seam groove remains after snapping."""
    import trimesh
    info = faceops.analyze(base / "a.step", FACE)
    p = faceops.plan("옆 벽 높이까지 올려줘", info)
    code = faceops.append_code(CODE, info, faceops.distances(p, info), p["how"], flush=True)
    sandbox.execute_to_files(code, base / "c.stl", base / "c.step")
    m = trimesh.load(base / "c.stl")
    for x in (19.0, 19.5, 20.0, 20.5, 21.0):           # seam between the wall (x<20) and the raised face (x>20)
        loc, _, _ = m.ray.intersects_location([[x, 25.0, 50]], [[0, 0, -1]])
        assert max(loc[:, 2]) == pytest.approx(15.0, abs=0.02)


def test_push_is_inserted_before_trailing_fillet(tmp_path):
    """If the code ends with a fillet step, insert before it so the raised face's outer edge gets the same R and there is no seam."""
    import trimesh
    code = ("from build123d import *\n"
            "body = Box(40, 30, 5, align=(Align.MIN, Align.MIN, Align.MIN))\n"
            "body += Pos(0, 0, 5) * Box(20, 30, 10, align=(Align.MIN, Align.MIN, Align.MIN))\n"
            "try: body = fillet(body.edges().filter_by(lambda e: abs(e.center().Z - 15) < 1e-3), 1.0)\n"
            "except Exception: pass\n"
            "part = body\n")
    assert faceops._trailing_round(code) == (3, "body")
    sandbox.execute_to_files(code, tmp_path / "a.stl", tmp_path / "a.step")
    info = faceops.analyze(tmp_path / "a.step", [{"point": [30.0, 15.0, 5.0], "normal": [0, 0, 1]}])
    p = faceops.plan("옆 벽 높이까지 올려줘", info)
    new = faceops.append_code(code, info, faceops.distances(p, info), p["how"], flush=True)
    assert new.index("_pp_items") < new.index("try: body = fillet(")
    r = sandbox.execute_to_files(new, tmp_path / "b.stl", tmp_path / "b.step")
    assert r["bbox"] == pytest.approx([40.0, 30.0, 15.0], abs=0.05)
    m = trimesh.load(tmp_path / "b.stl")
    for x in (19.0, 20.0, 21.0):                        # seam between old wall and raised face: flat
        loc, _, _ = m.ray.intersects_location([[x, 15.0, 50]], [[0, 0, -1]])
        assert max(loc[:, 2]) == pytest.approx(15.0, abs=0.02)
    loc, _, _ = m.ray.intersects_location([[39.8, 15.0, 50]], [[0, 0, -1]])   # raised face outer edge is also R1
    assert max(loc[:, 2]) < 14.95
