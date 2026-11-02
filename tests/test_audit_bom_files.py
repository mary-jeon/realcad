"""Assembly audit (B1 to B3), mass BOM, exported file checks, mesh cleanup, 7-view review, edit plans."""
from types import SimpleNamespace as NS

import numpy as np
import pytest
import build123d as bd
import trimesh

from realcad.verify.audit import audit
from realcad.export import asm_bom, filecheck
from realcad.geometry import meshfix


def _parts():
    shaft = bd.Cylinder(10, 100)                                       # 31.4 cm³ of SM45C
    two_pins = bd.Compound(children=[bd.Pos(-20, 0, 0) * bd.Cylinder(2, 10), bd.Pos(20, 0, 0) * bd.Cylinder(2, 10)])
    work = bd.Box(50, 50, 10)
    return [NS(no=1, name="축", spec="Ø20 × 100", qty=1, material="SM45C", solid=shaft),
            NS(no=2, name="핀", spec="Ø4 × 10", qty=2, material="SUJ2", solid=two_pins),
            NS(no=3, name="공작물(참조)", spec="", qty=1, material="", solid=work)]


def test_audit_passes_and_skips_reference_parts():
    ps = _parts()
    rows = [{"no": p.no} for p in ps]
    f = {x.code: x for x in audit(ps, rows)}
    assert f["B1"].ok and f["B2"].ok and f["B3"].ok


def test_audit_catches_missing_material_wrong_qty_and_bom_rows():
    ps = _parts()
    ps[0].material = ""
    ps[1].qty = 3                                                      # says 3, only 2 pins modelled
    f = {x.code: x for x in audit(ps, [{"no": 1}, {"no": 2}, {"no": 9}])}
    assert not f["B1"].ok and "1.축" in f["B1"].message
    assert not f["B2"].ok and f["B2"].severity == "HARD" and "실제 입체 2" in f["B2"].message
    assert not f["B3"].ok and "[3]" in f["B3"].message and "[9]" in f["B3"].message


def test_mass_bom_uses_measured_volume_and_typical_density(tmp_path):
    b = asm_bom.build(_parts())
    shaft = b["top"][0]
    assert abs(shaft["volume_cm3"] - np.pi * 1.0 * 10.0) < 0.05
    assert abs(shaft["mass_g"] - np.pi * 10.0 * 7.85) < 0.5
    pin = b["top"][1]
    assert pin["qty"] == 2 and abs(pin["mass_total_g"] - 2 * pin["mass_g"]) < 0.11
    assert b["top"][2]["reference"] and b["unknown_material"] == []
    assert abs(b["total_mass_g"] - (shaft["mass_total_g"] + pin["mass_total_g"])) < 0.11
    p = asm_bom.write_csv(b, tmp_path / "bom.csv")
    text = p.read_text(encoding="utf-8")
    assert "합계" in text and "SM45C" in text


def test_density_lookup():
    assert asm_bom.density("SCM435") == 7.85 and asm_bom.density("GC200") == 7.2
    assert asm_bom.density("pla") == 1.24 and asm_bom.density("PBC2") == 8.8
    assert asm_bom.density("unobtainium") is None and asm_bom.density("") is None


def test_filecheck_accepts_good_files_and_flags_bad_ones(tmp_path):
    from realcad.export import exporters as ex
    part = bd.Box(10, 20, 30)
    ex.to_step(part, tmp_path / "a.step"); ex.to_stl(part, tmp_path / "a_part.stl")
    (tmp_path / "empty.step").write_bytes(b"")
    (tmp_path / "junk.stl").write_bytes(b"solid x\nendsolid x\n")
    good = filecheck.check_downloads({"STEP": "a.step", "STL": "a_part.stl"}, tmp_path)
    assert all(c["ok"] for c in good) and len(good[0]["sha256"]) == 64
    assert "6.00 cm³" in good[0]["msg"]
    bad = filecheck.check_downloads({"STEP": "empty.step", "STL": "junk.stl", "PDF": "missing.pdf"}, tmp_path)
    assert not any(c["ok"] for c in bad)
    s = filecheck.summary(good + bad)
    assert not s["ok"] and len(s["failed"]) == 3


def test_meshfix_removes_defects_and_keeps_volume():
    m = trimesh.creation.box(extents=(10, 10, 10))
    vol = m.volume
    faces = np.vstack([m.faces, m.faces[:3], [[0, 0, 1]]])             # 3 duplicated triangles + 1 zero-area triangle
    faces[5] = faces[5][::-1]                                           # one triangle flipped
    dirty = trimesh.Trimesh(m.vertices, faces, process=False)
    clean, rep = meshfix.clean(dirty)
    assert rep["duplicate"] >= 3 and rep["degenerate"] >= 1 and rep["changed"]
    assert clean.is_watertight and abs(clean.volume - vol) < 1e-6
    assert "고침" in meshfix.note(rep)
    same, rep2 = meshfix.clean(m)
    assert not rep2["changed"] and meshfix.note(rep2) == ""


def test_review_renders_seven_standard_views(tmp_path):
    from realcad.agent import review
    from realcad.export import exporters as ex
    names = [v[0].split()[0] for v in review._VIEWS]
    assert names == ["FRONT", "BACK", "LEFT", "RIGHT", "TOP", "BOTTOM", "ISO"]
    ex.to_stl(bd.Box(30, 20, 10), tmp_path / "b.stl")
    p = review.render_views(tmp_path / "v.png", stl_path=tmp_path / "b.stl")
    from PIL import Image
    w, h = Image.open(p).size
    assert w > 1.8 * h                                                  # two rows of four
    assert "7 shaded renders" in review.REVIEW_SYSTEM and "BOTTOM" in review.REVIEW_SYSTEM


@pytest.fixture()
def app_tmp(tmp_path, monkeypatch):
    from realcad.web import app as A
    gen = tmp_path / "gen"; gen.mkdir()
    monkeypatch.setattr(A, "WEB", tmp_path)
    monkeypatch.setattr(A, "GEN", gen)
    monkeypatch.setattr(A, "_SESS_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(A, "SESSIONS", {})
    monkeypatch.setattr(A, "PLANS", {})
    return A


CODE = """from build123d import *
with BuildPart() as p:
    Box(60, 40, 5)
part = p.part
"""


def test_edit_plan_is_shown_first_and_applied_once(app_tmp, monkeypatch):
    A = app_tmp
    from realcad.agent import sandbox, codegen

    def fake_edit(prior, inst, stl, step, max_iters=3):
        code = prior.replace("Box(60, 40, 5)", "Box(60, 40, 8)")
        info = sandbox.execute_to_files(code, stl, step)
        return {"ok": True, "code": code, "info": info, "findings": codegen._findings(info), "iters": 0, "fixed": False}
    monkeypatch.setattr(A.editor, "design_edit_code", fake_edit)
    made = A.register_code_ep(A.RegisterCodeReq(code=CODE))
    sid = made["session"]
    assert made["files_ok"]["ok"]
    plan = A.edit_ep(A.EditReq(session=sid, instruction="두께 8", dry_run=True))
    assert plan["dry_run"] and plan["change"]["size_to"] == [60.0, 40.0, 8.0]
    assert any(l.startswith("+") and "Box(60, 40, 8)" in l for l in plan["diff"])
    assert A.SESSIONS[sid]["code"] == CODE                              # nothing applied yet
    out = A.apply_plan_ep(A.ApplyPlanReq(plan_id=plan["plan_id"]))
    assert out["plan_applied"] == plan["plan_id"] and out["stats"]["bbox_mm"] == [60.0, 40.0, 8.0]
    assert "Box(60, 40, 8)" in A.SESSIONS[sid]["code"]
    again = A.apply_plan_ep(A.ApplyPlanReq(plan_id=plan["plan_id"]))
    assert "error" in again


def test_stale_plan_is_refused(app_tmp, monkeypatch):
    A = app_tmp
    from realcad.agent import sandbox, codegen

    def fake_edit(prior, inst, stl, step, max_iters=3):
        code = prior.replace("Box(60, 40", "Box(70, 40")
        info = sandbox.execute_to_files(code, stl, step)
        return {"ok": True, "code": code, "info": info, "findings": codegen._findings(info), "iters": 0, "fixed": False}
    monkeypatch.setattr(A.editor, "design_edit_code", fake_edit)
    sid = A.register_code_ep(A.RegisterCodeReq(code=CODE))["session"]
    p1 = A.edit_ep(A.EditReq(session=sid, instruction="a", dry_run=True))
    p2 = A.edit_ep(A.EditReq(session=sid, instruction="b", dry_run=True))
    assert "plan_applied" in A.apply_plan_ep(A.ApplyPlanReq(plan_id=p1["plan_id"]))
    stale = A.apply_plan_ep(A.ApplyPlanReq(plan_id=p2["plan_id"]))
    assert "바뀌어서" in stale["error"]


def test_unknown_material_is_named_and_left_out_of_the_total():
    b = asm_bom.build([NS(no=1, name="x", spec="", qty=1, material="??", solid=bd.Box(100, 100, 100))])
    assert b["total_mass_g"] == 0.0 and b["unknown_material"] == ["x"] and not b["mass_complete"]


def test_mass_total_is_rounded_once():
    small = bd.Compound(children=[bd.Pos(10 * i, 0, 0) * bd.Box(1, 1, 1) for i in range(1000)])   # 1000 x 0.00785 g
    b = asm_bom.build([NS(no=1, name="pins", spec="", qty=1000, material="SS400", solid=small)])
    assert abs(b["total_mass_g"] - 7.85) <= 0.05            # was 0.0 when each 0.008 g pin was rounded first


def test_bom_row_numbers_twice_are_caught():
    f = {x.code: x for x in audit([NS(no=1, name="x", spec="s", qty=1, material="PLA", solid=bd.Box(1, 1, 1))],
                                  [{"no": 1}, {"no": 1}])}
    assert not f["B3"].ok and "두 번" in f["B3"].message


def test_csv_cells_never_start_a_formula(tmp_path):
    b = asm_bom.build([NS(no=1, name="=HYPERLINK(1)", spec="+x", qty=1, material="PLA", solid=bd.Box(1, 1, 1))])
    text = asm_bom.write_csv(b, tmp_path / "b.csv", "top").read_text(encoding="utf-8")
    assert "'=HYPERLINK" in text and ",=" not in text


def test_broken_pdf_and_dxf_fail(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"%PDF-broken")
    (tmp_path / "a.dxf").write_text("NOT A DXF\nEOF\n")
    out = filecheck.check_downloads({"PDF": "a.pdf", "Drawing": "a.dxf"}, tmp_path)
    assert not any(c["ok"] for c in out) and [c["kind"] for c in out] == ["PDF", "DXF"]


def test_meshfix_says_when_it_filled_a_gap():
    m = trimesh.creation.box(extents=(10, 10, 10))
    open_box = trimesh.Trimesh(m.vertices, m.faces[1:], process=False)
    clean, rep = meshfix.clean(open_box)
    assert rep["holes_filled"] and clean.is_watertight and "메웠" in meshfix.note(rep)


def test_contract_diff_sees_a_moved_hole():
    from realcad.agent import editor
    d = editor.diff_contract({"kind": "plate", "holes": [{"x": 0, "y": 0}]}, {"kind": "plate", "holes": [{"x": 20, "y": 0}]})
    assert any(c["field"] == "holes[1].x" and c["from"] == 0 and c["to"] == 20 for c in d)


def test_broken_download_is_taken_off_the_list(app_tmp):
    A = app_tmp
    (A.GEN / "ok.step").write_bytes(b"")                                # empty: fails the re-open
    d = A._with_checks({"downloads": {"STEP": "gen/ok.step"}})
    assert "STEP" not in d["downloads"] and d["downloads_failed"] == {"STEP": "gen/ok.step"}
