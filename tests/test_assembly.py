"""Power transmission assembly: standard tables, assembly build, checks (A1 to A6, M2), seeded error detection."""
import pytest
from build123d import Pos
from realcad.contract.schema import DesignContract as D
from realcad.pipeline import build_and_verify
from realcad.mech import standards as S
from realcad.mech.power_train import build_power_train, gear_solid
from realcad.verify import assembly as VA


def _asm(**kw):
    return D.from_dict({"kind": "assembly", "assembly": kw})


def _run(**kw):
    part, f, dia, findings, summ = build_and_verify(_asm(**kw))
    return part, summ, {x.code: x for x in findings}


# ── Standard tables ─────────────────────────────────────────────────
def test_parallel_key_table_ks_b_1311():
    k = S.parallel_key(20)
    assert (k.b, k.h, k.t1, k.t2) == (6, 6, 3.5, 2.8) and k.top_clearance == pytest.approx(0.3)
    assert S.parallel_key(25).name == "8x7" and S.parallel_key(12).name == "4x4"
    with pytest.raises(ValueError):
        S.parallel_key(90)


def test_bearing_6204_nsk_values_and_shaft_pick():
    b = S.bearing("6204")
    assert (b.d, b.D, b.B) == (20, 47, 14) and b.da_min == 25.0 and b.da_max == 26.5 and b.Da_max == 42.0
    assert S.bearing_for_shaft(25).code == "6205"
    with pytest.raises(ValueError):
        S.bearing("9999")


def test_ring_seal_pulley_gear_tables():
    r = S.retaining_ring(20)
    assert r.d2 == 19.0 and r.m == 1.35 and r.groove_depth == pytest.approx(0.5)
    assert S.oil_seal(20).name == "20x35x7"
    g = S.vpulley_groove("A", 100)
    assert g.alpha == 34 and g.od == pytest.approx(109.0) and S.vpulley_groove("A", 110).alpha == 36
    assert S.gear_dims(2, 30).da == 64 and S.center_distance(2, 30, 18) == 48.0


# ── Contract ────────────────────────────────────────────────────────
def test_contract_roundtrip_and_clamps():
    c = _asm(bearing="6204", gear={"module": 2, "teeth": 30}, pulley={"type": "none"}, pinion_teeth=999, exploded=0)
    a = c.assembly
    assert a.pulley_type == "none" and a.pinion_teeth == 200 and a.exploded == 0.0 and a.gear_width == 0.0
    assert D.from_dict(c.to_dict()).to_dict() == c.to_dict()


# ── Assembly build + checks ─────────────────────────────────────────
def test_default_power_train_assembles_and_passes():
    part, summ, fd = _run(bearing="6204", gear={"module": 2, "teeth": 30}, pulley={"type": "A", "dp": 100})
    assert summ["passed"], summ["hard_fail"]
    asm = part._rc_asm
    assert len(asm.parts) == 17 and fd["A1"].ok and fd["A2"].ok and fd["M2"].ok
    names = [p.name for p in asm.parts]
    for n in ("본체", "축", "스퍼기어", "평행키(기어)", "볼베어링", "멈춤링(C형)", "V벨트 풀리", "오일실", "커버(왼)", "커버(오른)"):
        assert n in names
    L = asm.layout
    assert L["shoulder_d"] == 25.0 and L["key_gear"] == "8x7" and L["key_pulley"] == "6x6" and L["seal"] == "25x40x7"
    assert min(p.solid.bounding_box().min.Z for p in asm.parts) >= -1e-6          # no part goes below the mounting face
    assert {m["id"] for m in asm.mates} >= {"M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8"}


def test_gear_pair_second_shaft_center_distance_measured():
    part, summ, fd = _run(bearing="6204", gear={"module": 2, "teeth": 30}, pulley={"type": "A", "dp": 100}, pinion_teeth=18)
    assert summ["passed"], summ["hard_fail"]
    assert fd["A5"].ok and "48.00" in fd["A5"].message and part._rc_asm.layout["center_distance"] == 48.0
    assert any(m["id"] == "M9" for m in part._rc_asm.mates)
    # z18 on a 25 mm seat: the pinion keyway would cut through the tooth root (rim -0.3 mm), so the teeth are cut on the shaft
    pin = part._rc_asm.layout["pinion"]
    assert pin["integral"] and pin["rim_under_keyway"] < pin["rim_min"]
    ps = part._rc_asm.by_name("피니언 축(일체)")
    assert ps is not None and len(ps.solid.solids()) == 1 and part._rc_asm.by_name("평행키(피니언)") is None
    assert fd["B2"].ok


def test_large_pinion_keeps_its_key():
    part, summ, fd = _run(bearing="6204", gear={"module": 2, "teeth": 30}, pinion_teeth=30)
    assert summ["passed"], summ["hard_fail"]
    assert not part._rc_asm.layout["pinion"]["integral"]
    assert part._rc_asm.by_name("평행키(피니언)") is not None


def test_no_pulley_variant_and_other_bearing():
    part, summ, fd = _run(bearing="6205", gear={"module": 3, "teeth": 24}, pulley={"type": "none"})
    assert summ["passed"], summ["hard_fail"]
    assert part._rc_asm.layout["key_gear"] == "8x7" and part._rc_asm.layout["pulley"] is None


def test_exploded_view_moves_parts_but_checks_run_on_assembled():
    c = _asm(bearing="6204", gear={"module": 2, "teeth": 30}, pulley={"type": "A", "dp": 100}, exploded=20)
    part, f, dia, findings, summ = build_and_verify(c)
    assert summ["passed"]
    asm = part._rc_asm
    bb0 = asm.compound.bounding_box().size.X
    bb1 = asm.exploded(20).bounding_box().size.X
    assert bb1 > bb0 + 50


# ── Seeded errors ───────────────────────────────────────────────────
def test_seeded_missing_rings_fails_axial_chain():
    part, summ, fd = _run(bearing="6204", gear={"module": 2, "teeth": 30}, pulley={"type": "A", "dp": 100}, rings=False)
    assert not summ["passed"] and "A3" in summ["hard_fail"] and fd["A1"].ok


def test_seeded_shifted_gear_is_caught_as_interference():
    asm = build_power_train(_asm(bearing="6204", gear={"module": 2, "teeth": 30}, pulley={"type": "A", "dp": 100}).assembly)
    g = next(p for p in asm.parts if p.name == "스퍼기어")
    g.solid = Pos(3.0, 0, 0) * g.solid                     # push the gear 3 mm so it overlaps the spacer
    f = VA.a1_interference(asm.parts)
    assert not f.ok and "스퍼기어" in f.message


def test_seeded_wrong_bore_is_caught_by_fit_measurement():
    asm = build_power_train(_asm(bearing="6204", gear={"module": 2, "teeth": 30}, pulley={"type": "A", "dp": 100}).assembly)
    L = asm.layout
    g = next(p for p in asm.parts if p.name == "스퍼기어")
    xc = L["x"]["x_gear"] + L["gear"]["width"] / 2
    g.solid = gear_solid(30, 2, L["gear"]["width"], 26.0, xc, 0.0, L["z_axis"], 90.0)   # bore diameter 26 != seat diameter 25
    f = VA.a2_fits(asm)
    assert not f.ok and "기어 보어" in f.message


# ── Eccentric reciprocator (second preset) ──────────────────────────
def _ecc(**kw):
    kw.setdefault("preset", "eccentric_slider")
    return _asm(**kw)


def test_eccentric_default_assembles_moves_and_passes():
    part, f, dia, findings, summ = build_and_verify(_ecc(bearing="6204", pulley={"type": "A", "dp": 100}, eccentricity=8))
    fd = {x.code: x for x in findings}
    assert summ["passed"], summ["hard_fail"]
    asm = part._rc_asm
    names = [p.name for p in asm.parts]
    for n in ("본체", "편심축", "링크(크랭크)", "슬라이더", "핀", "간격링", "가이드부시", "커버(상부)", "V벨트 풀리", "오일실"):
        assert n in names
    assert fd["A7"].ok and "16.00" in fd["A7"].message and asm.layout["stroke"] == 16.0
    assert any(m["id"] == "M9" for m in asm.mates)
    assert min(p.solid.bounding_box().min.Z for p in asm.parts) >= -1e-6


def test_eccentric_kinematics_stroke_is_twice_e():
    from realcad.mech.eccentric import layout_eccentric, kinematics
    L = layout_eccentric(_ecc(eccentricity=10, link_length=60).assembly)
    zs = [kinematics(L, th)["z_pin"] for th in range(0, 360, 15)]
    assert max(zs) - min(zs) == pytest.approx(20.0, abs=1e-6)
    assert abs(kinematics(L, 0)["phi_deg"]) == pytest.approx(math.degrees(math.asin(10 / 60)), abs=1e-6)


def test_eccentric_bigger_slider_grows_cavity_and_passes():
    part, f, dia, findings, summ = build_and_verify(_ecc(bearing="6205", pulley={"type": "none"}, eccentricity=12, link_length=60, slider_d=25))
    assert summ["passed"], summ["hard_fail"]


def test_seeded_motion_interference_is_caught_by_a7():
    from realcad.mech.eccentric import build_eccentric
    asm = build_eccentric(_ecc(eccentricity=8).assembly)
    orig = asm.motion
    def bad_motion(th):
        mv = orig(th); mv["링크(크랭크)"] = Pos(0, 3.0, 0) * mv["링크(크랭크)"]; return mv   # push the link 3 mm sideways so it overlaps the journal
    asm.motion = bad_motion
    f = VA.a7_motion(asm, angles=(0, 90))
    assert not f.ok and "링크" in f.message


import math


# ── Gear pump (third preset) ────────────────────────────────────────
def test_gear_pump_exam_example_passes_with_pair_and_motion_checks():
    part, f, dia, findings, summ = build_and_verify(_asm(preset="gear_pump", gear={"module": 1.5, "teeth": 24, "width": 29}))
    fd = {x.code: x for x in findings}
    assert summ["passed"], summ["hard_fail"]
    asm = part._rc_asm
    L = asm.layout
    assert L["center_distance"] == 36.0 and L["pocket"] == [39.0, 28.0] and L["journal_d"] == 12 and L["seal"] == "12x22x7"
    assert fd["A5"].ok and "36.00" in fd["A5"].message and fd["A7"].ok and fd["A8"].ok
    assert [p.name for p in asm.parts].count("부시") == 4


def test_gear_pump_seeded_shallow_pocket_fails_a8():
    from realcad.mech.gear_pump import build_gear_pump
    asm = build_gear_pump(_asm(preset="gear_pump", gear={"module": 1.5, "teeth": 24, "width": 29}).assembly)
    asm.layout["extra_checks"][0]["ok"] = (27.0 + 1.0 >= 29.0)        # simulate the pocket depth changing to 27
    f = VA.a8_extra(asm)[0]
    assert not f.ok and f.code == "A8"


# ── Drill jig (fourth preset) ───────────────────────────────────────
def test_drill_jig_from_workpiece_and_hole_pattern():
    part, f, dia, findings, summ = build_and_verify(_asm(preset="drill_jig", work={"length": 80, "width": 50, "thickness": 15}, drill_d=10, holes=[[-20, 0], [20, 0]]))
    fd = {x.code: x for x in findings}
    assert summ["passed"], summ["hard_fail"]
    asm = part._rc_asm
    assert asm.layout["bush"] == {"d1": 10.0, "d2": 15, "l": 20} and fd["A9"].ok and fd["A10"].ok
    assert [p.name for p in asm.parts].count("고정부시") == 2 and "공작물(참조)" in [p.name for p in asm.parts]


def test_drill_jig_seeded_wrong_bush_position_fails_a10():
    from realcad.mech.drill_jig import build_drill_jig
    asm = build_drill_jig(_asm(preset="drill_jig", drill_d=10, holes=[[-20, 0], [20, 0]]).assembly)
    b = next(p for p in asm.parts if p.name == "고정부시")
    b.solid = Pos(0.5, 0, 0) * b.solid                      # offset one bushing by 0.5 mm
    f = VA.a10_hole_pattern(asm)
    assert not f.ok and "-20" in f.message


def test_drill_bush_table_din179():
    assert (S.drill_bush(10).d2, S.drill_bush(10).length_for(20)) == (15, 20)
    assert S.drill_bush(6.5).d2 == 12 and S.drill_bush(12).lengths == (12, 20, 25)
    with pytest.raises(ValueError):
        S.drill_bush(25)


# ── Bench vise (fifth preset) ───────────────────────────────────────
def test_vise_opens_to_max_without_interference():
    part, f, dia, findings, summ = build_and_verify(_asm(preset="vise", jaw_w=80, open_max=60, screw_d=16))
    fd = {x.code: x for x in findings}
    assert summ["passed"], summ["hard_fail"]
    asm = part._rc_asm
    assert fd["A7"].ok and fd["A11"].ok and len(asm.layout["triangle"]["posts"]) == 2
    names = [p.name for p in asm.parts]
    for n in ("본체(고정조)", "이동조", "리드나사축", "너트", "가이드 포스트", "가이드부시(좌)", "핸들", "멈춤링(C형)"):
        assert n in names
    mv = asm.motion(60.0)
    assert mv["이동조"].bounding_box().max.X == pytest.approx(asm.by_name("이동조").solid.bounding_box().max.X - 60.0)


def test_vise_seeded_short_post_fails_a11():
    from realcad.mech.vise import build_vise
    asm = build_vise(_asm(preset="vise", open_max=60).assembly)
    asm.layout["extra_checks"][0]["ok"] = False          # posts too short: they leave the bushings at maximum opening
    assert not VA.a8_extra(asm)[0].ok


# ── Cam clamp (sixth preset) ────────────────────────────────────────
def test_cam_clamp_locks_on_workpiece_and_moves_clear():
    part, f, dia, findings, summ = build_and_verify(_asm(preset="cam_clamp", work_d=30, cam_lift=4))
    fd = {x.code: x for x in findings}
    assert summ["passed"], summ["hard_fail"]
    asm = part._rc_asm
    assert fd["A12"].ok and fd["A7"].ok and asm.layout["stroke"] == 8.0
    from realcad.mech.cam_clamp import strap_z_top, STRAP_T
    L = asm.layout
    import realcad.mech.cam_clamp as cc
    lay = cc.layout_cam_clamp(_asm(preset="cam_clamp", work_d=30, cam_lift=4).assembly)
    assert strap_z_top(lay, 180.0) - STRAP_T == pytest.approx(lay["z_wtop"], abs=1e-6)
    assert strap_z_top(lay, 0.0) - strap_z_top(lay, 180.0) == pytest.approx(8.0, abs=1e-6)


def test_cam_clamp_seeded_lever_pointing_down_hits_strap():
    from realcad.mech.cam_clamp import build_cam_clamp
    asm = build_cam_clamp(_asm(preset="cam_clamp").assembly)
    orig = asm.motion
    def bad(th):
        mv = orig(th); mv["캠 손잡이"] = Pos(0, 0, -30.0) * mv["캠 손잡이"]; return mv
    asm.motion = bad
    assert not VA.a7_motion(asm, angles=(0, 90)).ok


def test_pinion_smaller_than_its_shaft_is_refused():
    # z12 m2 on a 6204 shaft: root circle Ø19 is inside the Ø25 seat, no gear can be cut there
    with pytest.raises(ValueError, match="이뿌리 지름"):
        S_layout = __import__("realcad.mech.power_train", fromlist=["layout_power_train"]).layout_power_train
        S_layout(_asm(bearing="6204", gear={"module": 2, "teeth": 30}, pinion_teeth=12).assembly)


def test_failed_overlap_is_not_reported_as_no_overlap(monkeypatch):
    from types import SimpleNamespace as NS
    from build123d import Box
    monkeypatch.setattr(VA, "_intersection_volume", lambda a, b: None)
    f = VA.a1_interference([NS(name="a", solid=Box(10, 10, 10)), NS(name="b", solid=Box(10, 10, 10))])
    assert not f.ok and "확인 못함" in f.message
