"""Sketch -> extrude/cut: new part, hole through a face, loop inside a loop = hole, symmetric both sides, sketch on a starting shape (BASE)."""
from pathlib import Path

import pytest

from realcad.agent import sketchops, sandbox

TOP = {"origin": [0, 0, 0], "x_dir": [1, 0, 0], "normal": [0, 0, 1]}


def run(code, tmp_path, name="a"):
    return sandbox.execute_to_files(code, tmp_path / f"{name}.stl", tmp_path / f"{name}.step")


def test_new_part_from_rectangle_boss(tmp_path):
    code = sketchops.apply(None, {"plane": TOP, "loops": [{"type": "rect", "cx": 0, "cy": 0, "w": 40, "h": 20}], "op": "boss", "depth": 10})
    r = run(code, tmp_path)
    assert r["bbox"] == pytest.approx([40, 20, 10], abs=0.01)
    assert r["volume"] == pytest.approx(8000, rel=1e-3)


def test_inner_loop_is_hole_and_cut_through(tmp_path):
    loops = [{"type": "rect", "cx": 0, "cy": 0, "w": 40, "h": 40}, {"type": "circle", "cx": 0, "cy": 0, "r": 5}]
    code = sketchops.apply(None, {"plane": TOP, "loops": loops, "op": "boss", "depth": 10})
    r = run(code, tmp_path)
    assert r["volume"] == pytest.approx(40 * 40 * 10 - 3.14159265 * 25 * 10, rel=1e-3)
    # draw a circle on the top face (z=10) and cut all the way through
    face = {"origin": [10, 10, 10], "x_dir": [1, 0, 0], "normal": [0, 0, 1]}
    code2 = sketchops.apply(code, {"plane": face, "loops": [{"type": "circle", "cx": 0, "cy": 0, "r": 3}], "op": "cut", "end": "through"})
    r2 = run(code2, tmp_path, "b")
    assert r2["volume"] == pytest.approx(r["volume"] - 3.14159265 * 9 * 10, rel=1e-3)


def test_blind_cut_goes_into_material_and_mid_plane(tmp_path):
    code = sketchops.apply(None, {"plane": TOP, "loops": [{"type": "rect", "cx": 0, "cy": 0, "w": 30, "h": 30}], "op": "boss", "depth": 10, "end": "mid"})
    r = run(code, tmp_path)
    assert r["bbox"][2] == pytest.approx(10, abs=0.01)          # symmetric both sides, 10 total
    face = {"origin": [0, 0, 5], "x_dir": [1, 0, 0], "normal": [0, 0, 1]}
    code2 = sketchops.apply(code, {"plane": face, "loops": [{"type": "poly", "pts": [[-5, -5], [5, -5], [5, 5], [-5, 5], [-5, -5]]}], "op": "cut", "depth": 3})
    r2 = run(code2, tmp_path, "b")
    assert r2["volume"] == pytest.approx(r["volume"] - 10 * 10 * 3, rel=1e-3)   # 3 mm pocket into the face


def test_open_or_empty_sketch_rejected():
    with pytest.raises(ValueError):
        sketchops.apply(None, {"plane": TOP, "loops": [{"type": "poly", "pts": [[0, 0], [5, 0]]}], "op": "boss", "depth": 5})


def test_sketch_on_base_step(tmp_path):
    base = "from build123d import *\npart = Box(20, 20, 20)\n"
    run(base, tmp_path, "base")
    name = "pytestbase01.step"
    (sandbox.BASES_DIR / name).write_bytes((tmp_path / "base.step").read_bytes())
    try:
        face = {"origin": [0, 0, 10], "x_dir": [1, 0, 0], "normal": [0, 0, 1]}
        code = sketchops.apply(None, {"plane": face, "loops": [{"type": "circle", "cx": 0, "cy": 0, "r": 4}], "op": "boss", "depth": 6}, name)
        r = run(code, tmp_path, "c")
        assert r["bbox"][2] == pytest.approx(26, abs=0.01)
    finally:
        (sandbox.BASES_DIR / name).unlink(missing_ok=True)


def test_straight_slot_is_exact(tmp_path):
    loops = [{"type": "rect", "cx": 0, "cy": 0, "w": 60, "h": 30}, {"type": "slot", "x1": -10, "y1": 0, "x2": 20, "y2": 0, "w": 8}]
    code = sketchops.apply(None, {"plane": TOP, "loops": loops, "op": "boss", "depth": 5})
    r = run(code, tmp_path)
    assert r["volume"] == pytest.approx((60 * 30 - (30 * 8 + 3.14159265 * 16)) * 5, rel=1e-4)


def test_closed_path_with_arc(tmp_path):
    segs = [{"t": "line", "a": [0, 0], "b": [40, 0]}, {"t": "line", "a": [40, 0], "b": [40, 20]},
            {"t": "arc", "a": [40, 20], "m": [20, 40], "b": [0, 20]}, {"t": "line", "a": [0, 20], "b": [0, 0]}]
    code = sketchops.apply(None, {"plane": TOP, "loops": [{"type": "path", "segs": segs}], "op": "boss", "depth": 3})
    r = run(code, tmp_path)
    assert r["volume"] == pytest.approx((40 * 20 + 3.14159265 * 400 / 2) * 3, rel=1e-4)
