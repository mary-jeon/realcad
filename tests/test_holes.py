"""A hole counts only if it can be used: measured by firing rays along it."""
import trimesh
from build123d import Box, Cylinder, Pos

from realcad.verify.holes import blocked_holes, finding


def _mesh(part, tmp_path):
    p = tmp_path / "p.stl"
    part.export_stl(str(p)) if hasattr(part, "export_stl") else __import__("build123d").export_stl(part, str(p))
    return trimesh.load(str(p), force="mesh")


def _plate():
    return Pos(0, 0, 2) * Box(60, 60, 4)


def _hole(x=0, y=0, d=3.4, h=10):
    return Pos(x, y, 2) * Cylinder(radius=d / 2, height=h)


def test_open_through_hole_is_fine(tmp_path):
    part = _plate() - _hole()
    assert blocked_holes(part, _mesh(part, tmp_path)) == []


def test_rib_over_part_of_the_mouth_is_caught(tmp_path):
    part = (_plate() - _hole()) + Pos(4.0 + 0.7, 0, 10) * Box(8, 30, 12)      # the rib covers x >= 0.7 of a hole of radius 1.7
    b = blocked_holes(part, _mesh(part, tmp_path))
    assert len(b) == 1 and b[0]["dia"] == 3.4 and 0 < b[0]["stopped"] < 8
    assert finding(b)["severity"] == "HARD" and not finding(b)["ok"]
    assert "partly covered" in b[0]["en"]


def test_blind_hole_is_fine(tmp_path):
    part = _plate() - Pos(0, 0, 3) * Cylinder(radius=1.7, height=2.01)
    assert blocked_holes(part, _mesh(part, tmp_path)) == []


def test_counterbore_step_is_fine(tmp_path):
    part = _plate() - _hole(d=3.4) - Pos(0, 0, 3.5) * Cylinder(radius=3.2, height=3.01)
    assert blocked_holes(part, _mesh(part, tmp_path)) == []


def test_hole_closed_at_both_ends_is_caught(tmp_path):
    cap = Pos(0, 0, 8) * Box(20, 20, 3)
    wall = Pos(11, 0, 5) * Box(2, 20, 8)
    part = (_plate() - _hole(h=4.01)) + cap + wall + Pos(0, 0, -3) * Box(20, 20, 3) + Pos(11, 0, -1) * Box(2, 20, 2)
    b = blocked_holes(part, _mesh(part, tmp_path))
    assert any(x["sealed"] and "closed off" in x["en"] for x in b)
    assert finding([x for x in b if x["sealed"]])["severity"] == "SOFT"      # a warning: a figure may hide a void


def test_pin_is_not_a_hole(tmp_path):
    part = _plate() + Pos(0, 0, 8) * Cylinder(radius=2, height=10)
    assert blocked_holes(part, _mesh(part, tmp_path)) == []


def test_finding_says_when_not_measured():
    f = finding([], checked=False)
    assert f["code"] == "H7" and f["severity"] == "HARD" and f["ok"] is False
