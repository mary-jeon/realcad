"""Visual review and engine diagnostics. Meta calls are faked, so the flow is tested without credits."""
import os
from pathlib import Path

import pytest

from realcad.agent import codegen, review, sandbox

BOX = "from build123d import *\npart = Box(20, 20, 10) + Pos(0, 0, 8) * Box(8, 8, 8)\n"
BIGGER = "from build123d import *\npart = Box(40, 20, 10) + Pos(0, 0, 8) * Box(8, 8, 8)\n"
FLOAT = ("from build123d import *\nbase = Box(40, 40, 5)\npost = Pos(0, 0, 10) * Box(6, 6, 20)\n"
         "cup = Pos(0, 0, 22) * Cylinder(radius=8, height=6)\nhandle = Pos(20, 0, 22) * Box(4, 4, 4)\n"
         "part = base + post + cup + handle\n")


def test_diagnose_names_the_floating_part():
    d = sandbox.diagnose(FLOAT)
    assert d and d["kind"] == "SEPARATE" and d["part"] == "handle"
    assert "handle" in d["en"] and "handle" in d["ko"]


def test_diagnose_ok_and_unparsable():
    ok = "from build123d import *\npart = Box(10,10,10) + Pos(0,0,6)*Box(5,5,5) + Pos(0,0,10)*Cylinder(radius=2, height=6)\n"
    assert sandbox.diagnose(ok)["kind"] == "OK"
    assert sandbox.diagnose("part = ((") is None
    assert sandbox.diagnose("from build123d import *\npart = Box(1,1,1)\n") is None   # no union line


def test_diag_note_appends_only_for_geometry_errors():
    diags = []
    out = codegen._diag_note(FLOAT, "공중에 뜬 분리 솔리드가 있습니다 (solid1)", diags)
    assert "RealCAD engine diagnosis" in out and diags and "handle" in diags[0]
    assert codegen._diag_note(FLOAT, "NameError: name 'x' is not defined", []) == "NameError: name 'x' is not defined"


def _make(tmp_path, code):
    stl, step = tmp_path / "ab12cd34_part.stl", tmp_path / "ab12cd34.step"
    info = sandbox.execute_to_files(code, stl, step)
    return stl, step, info


def test_render_views_makes_png(tmp_path):
    stl, step, _ = _make(tmp_path, BOX)
    p = review.render_views(tmp_path / "r.png", step_path=step, stl_path=stl, title="box")
    assert p and p.exists() and p.stat().st_size > 8000


def test_visual_review_fixes_then_confirms(tmp_path, monkeypatch):
    stl, step, info = _make(tmp_path, BOX)
    calls = iter([{"matches": False, "problems": ["너무 짧음"], "fix": "make it 40 long"},
                  {"matches": True, "problems": [], "fix": ""}])
    monkeypatch.setattr(review, "review_once", lambda *a, **k: next(calls))
    monkeypatch.setattr(codegen, "generate_code", lambda *a, **k: (BIGGER, {}))
    code, info2, rv = codegen._visual_review("box 40 long", BOX, info, stl, step)
    assert rv["fixed"] and len(rv["rounds"]) == 2 and rv["rounds"][1]["matches"]
    assert code == BIGGER and info2["bbox"][0] == pytest.approx(40, abs=0.1)
    assert len(rv["images"]) == 2 and all((tmp_path / n).exists() for n in rv["images"])
    assert not list(tmp_path.glob("*rvfix*")) and not list(tmp_path.glob("*rvorig*"))   # clean up temp files


def test_visual_review_reverts_when_worse(tmp_path, monkeypatch):
    stl, step, info = _make(tmp_path, BOX)
    before = stl.read_bytes()
    calls = iter([{"matches": False, "problems": ["a"], "fix": ""},
                  {"matches": False, "problems": ["a", "b", "c"], "fix": ""}])
    monkeypatch.setattr(review, "review_once", lambda *a, **k: next(calls))
    monkeypatch.setattr(codegen, "generate_code", lambda *a, **k: (BIGGER, {}))
    code, _i, rv = codegen._visual_review("box", BOX, info, stl, step)
    assert rv.get("reverted") and not rv["fixed"] and code == BOX and stl.read_bytes() == before


def test_visual_review_keeps_first_when_fix_fails(tmp_path, monkeypatch):
    stl, step, info = _make(tmp_path, BOX)
    monkeypatch.setattr(review, "review_once", lambda *a, **k: {"matches": False, "problems": ["x"], "fix": ""})
    monkeypatch.setattr(codegen, "generate_code", lambda *a, **k: ("from build123d import *\npart = None\n", {}))
    code, _i, rv = codegen._visual_review("box", BOX, info, stl, step)
    assert rv.get("fix_error") and code == BOX and not rv["fixed"]


def test_visual_review_can_be_turned_off(tmp_path, monkeypatch):
    stl, step, info = _make(tmp_path, BOX)
    monkeypatch.setenv("REALCAD_VISUAL_REVIEW", "0")
    assert codegen._visual_review("box", BOX, info, stl, step)[2] is None


def test_review_parse_is_forgiving():
    assert review._parse('{"matches": true, "problems": []}')["matches"] is True
    r = review._parse('noise {"matches": false, "problems": ["눈이 없음"], "fix": "add eyes"} tail')
    assert r["matches"] is False and r["problems"] == ["눈이 없음"]
    bad = review._parse("not json")                        # unreadable: reported as not reviewed, never as "looks fine"
    assert bad["matches"] is False and bad["unknown"] and bad["problems"] == []   # no problems, so no fix attempt
