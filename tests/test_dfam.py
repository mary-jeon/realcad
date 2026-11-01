"""verify/dfam.py: measured wall thickness + print orientation recommendation (trimesh raycast)."""
from build123d import Box, Cylinder
from realcad.verify import dfam


def test_wall_finds_thin_shell():
    box = Box(40, 40, 20) - Box(36, 36, 20)        # hollow box with 2mm walls
    w = dfam.wall_thickness(box)
    assert w is not None
    assert abs(w["p05_mm"] - 2.0) < 0.3            # real minimum wall ~ 2mm
    assert w["bodies"] == 1


def test_wall_plate_thickness():
    plate = Box(60, 40, 6) - Cylinder(4, 6)        # 6mm plate with a center hole
    w = dfam.wall_thickness(plate)
    assert abs(w["p05_mm"] - 6.0) < 0.3


def test_orientation_prefers_flat_over_tall():
    part = Box(80, 50, 6)                            # lying flat: zero support
    o = dfam.orientation_advice(part)
    assert o is not None
    flat = next(c for c in o["candidates"] if c["orientation"].startswith("그대로"))
    assert flat["support_area_mm2"] < 1.0
    assert o["best"].startswith("그대로")


def test_measure_single_tessellation_returns_both():
    d = dfam.measure(Box(30, 30, 10))
    assert d["wall"] is not None and d["orientation"] is not None


def test_bad_part_returns_none():
    class Bogus:
        pass
    assert dfam.wall_thickness(Bogus()) is None
    assert dfam.orientation_advice(Bogus()) is None
