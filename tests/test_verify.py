"""Verification regression: what should fail fails (seeded errors), what should pass passes."""
from realcad.contract.schema import DesignContract as D
from realcad.pipeline import build_and_verify

BASE = {"kind": "plate", "plate": {"length": 80, "width": 40, "thickness": 5},
        "fastener": "1/4-20", "fit": "normal", "holes": [{"x": -25, "y": 0}, {"x": 25, "y": 0}]}


def _run(d):
    part, f, dia, findings, summ = build_and_verify(D.from_dict(d))
    return summ, {x.code: x for x in findings if not x.ok}


def test_good_plate_passes():
    summ, bad = _run(BASE)
    assert summ["passed"] and not summ["soft_warn"], bad


def test_seeded_small_hole_fails_h2_by_measurement():
    summ, bad = _run({**BASE, "hole_dia": 6.0})          # drilled smaller than the standard 7.14
    assert not summ["passed"] and "H2" in summ["hard_fail"]
    assert abs(bad["H2"].actual - 6.0) < 0.05 and abs(bad["H2"].required - 7.14) < 0.05


def test_hole_near_edge_fails_h4():
    summ, _ = _run({**BASE, "holes": [{"x": -36, "y": 0}, {"x": 25, "y": 0}]})
    assert "H4" in summ["hard_fail"]


def test_bolts_too_close_warns_s2_and_heads_collide_h1():
    summ, _ = _run({**BASE, "holes": [{"x": -5, "y": 0}, {"x": 5, "y": 0}]})
    assert "H1" in summ["hard_fail"] and "S2" in summ["soft_warn"]


def test_wall_collision_fails_h1():
    summ, _ = _run({**BASE, "wall": {"x": 20, "height": 25, "thickness": 4}})
    assert "H1" in summ["hard_fail"]


def test_unknown_fastener_reports_f0_not_silent():
    summ, bad = _run({**BASE, "fastener": "M20"})
    assert "F0" in summ["hard_fail"] and "M12" in bad["F0"].message


def test_unf_accepted():
    summ, _ = _run({**BASE, "fastener": "1/4-28"})
    assert summ["passed"]


def test_container_and_gear_pass_manifold():
    for d in ({"kind": "container", "container": {"shape": "round", "outer_d": 80, "height": 100, "wall": 2.4, "base": 2.4}},
              {"kind": "gear", "gear": {"teeth": 20, "module": 2, "thickness": 6, "bore": 6}}):
        summ, bad = _run(d)
        assert summ["passed"], bad


def test_tapped_thin_plate_fails_h3_and_thick_passes():
    thin = {**BASE, "plate": {"length": 80, "width": 40, "thickness": 3}, "fastener": "1/2-13", "hole_type": "tapped", "material": "pla"}
    summ, bad = _run(thin)
    assert "H3" in summ["hard_fail"] and bad["H3"].required > 20     # k=2.0 × 12.7
    thick = {**BASE, "plate": {"length": 80, "width": 40, "thickness": 10}, "fastener": "M4", "hole_type": "tapped", "material": "pla"}
    summ, bad = _run(thick)
    assert summ["passed"], bad                                         # 10 ≥ 2.0×4


def test_bom_through_and_tapped():
    from realcad.export.bom import make_bom
    from realcad.fasteners.standards import get
    c = D.from_dict({**BASE, "mate_thickness": 10, "washer": True, "nut": True})
    rows = make_bom(c, get("1/4-20"), 7.14)
    bolt = rows[0]
    assert bolt["qty"] == 2 and bolt["length_mm"] >= bolt["required_mm"] >= 5 + 10 + 1.65 + 5.7
    assert {r["item"] for r in rows} == {"bolt", "hex nut", "flat washer"}
    c = D.from_dict({**BASE, "hole_type": "tapped", "fastener": "M4", "mate_thickness": 6})
    rows = make_bom(c, get("M4"), 3.3, engage_mm=8.0)
    assert rows[0]["length_mm"] == 16 and len(rows) == 1              # 6 + 8 = 14 → 16 mm


def test_heat_set_insert_depth_rule():
    ok = {**BASE, "plate": {"length": 60, "width": 40, "thickness": 9}, "fastener": "M3", "hole_type": "insert"}
    summ, bad = _run(ok); assert summ["passed"], bad                      # 5.7 + 1 ≤ 9 − 1
    thin = {**ok, "plate": {"length": 60, "width": 40, "thickness": 4}}
    summ, bad = _run(thin); assert "I1" in summ["hard_fail"]


def test_counterbore_head_sits_flush():
    summ, bad = _run({**BASE, "plate": {"length": 80, "width": 40, "thickness": 10}, "fastener": "M5", "hole_style": "counterbore"})
    assert summ["passed"], bad


def test_tool_access_h5_catches_wall_inside_socket_radius():
    from realcad.fasteners.standards import get
    f = get("1/4-20")
    x_wall = -25 + f.head_across_corners_mm / 2 + 2.0 + 0.3          # the head clears but the socket (diameter 16.5) hits
    summ, bad = _run({**BASE, "wall": {"x": x_wall, "height": 25, "thickness": 4}})
    assert "H5" in summ["hard_fail"] and "H1" not in summ["hard_fail"]


def test_overhang_warning_on_t_shape():
    from realcad.verify.checks import m3_overhang
    from build123d import Box, Pos
    t = Box(10, 10, 40) + Pos(0, 0, 25) * Box(60, 60, 10)             # mushroom shape: everything under the top plate is overhang
    f = m3_overhang(t); assert not f.ok and f.actual > 10
    assert m3_overhang(Box(30, 30, 30)).ok
