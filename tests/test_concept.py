"""Reference sheet flow: outline masks, outline match, mesh-mode union, and the build loop (Meta calls are faked)."""
import numpy as np
import pytest
from PIL import Image, ImageDraw
from pathlib import Path

from realcad.agent import codegen, concept, review, sandbox

BOX = "from build123d import *\npart = Box(20, 10, 40, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
FIXTURE = Path(__file__).parent / "fixtures" / "robot_kernel_fail.py"


def _sheet(path, front=(20, 40), side=(10, 40), scale=6):
    """White sheet with a black front outline on the left and a side outline on the right."""
    W, H = 600, 400
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    fw, fh = front[0] * scale // 2, front[1] * scale // 2
    sw, sh = side[0] * scale // 2, side[1] * scale // 2
    d.rectangle([150 - fw // 2, 200 - fh // 2, 150 + fw // 2, 200 + fh // 2], fill="black")
    d.rectangle([450 - sw // 2, 200 - sh // 2, 450 + sw // 2, 200 + sh // 2], fill="black")
    im.save(path)
    return path


def test_sheet_masks_split_front_and_side(tmp_path):
    f, s = concept.sheet_masks(_sheet(tmp_path / "s.png"))
    assert f.any() and s.any() and f.shape[1] > s.shape[1]


def test_iou_identical_mirrored_and_different():
    a = np.zeros((50, 30), bool); a[5:45, 5:20] = True
    assert concept.iou(a, a) == pytest.approx(1.0)
    assert concept.iou(a, a[:, ::-1]) == pytest.approx(1.0)
    b = np.zeros((50, 50), bool); b[5:45, 2:48] = True
    assert concept.iou(a, b) < 0.6


def test_score_box_against_matching_and_wrong_sheet(tmp_path):
    stl, step = tmp_path / "ab12cd34_part.stl", tmp_path / "ab12cd34.step"
    sandbox.execute_to_files(BOX, stl, step)
    good = concept.score(_sheet(tmp_path / "good.png"), stl)
    bad = concept.score(_sheet(tmp_path / "bad.png", front=(40, 20), side=(40, 20)), stl)
    assert good["front"] > 0.9 and good["side"] > 0.9
    assert concept.low(bad) and not concept.low(good)


def test_draw_saves_the_generated_image(tmp_path, monkeypatch):
    monkeypatch.setattr(concept.meta_client, "image", lambda prompt, **k: b"PNGDATA" if "front" in prompt.lower() else b"")
    assert concept.draw("고양이", tmp_path / "c.png").read_bytes() == b"PNGDATA"


def test_kernel_failure_is_rebuilt_as_mesh(tmp_path):
    info = sandbox.execute_to_files(FIXTURE.read_text(), tmp_path / "r_part.stl", tmp_path / "r.step")
    assert info["mesh"] and info["bodies"] == 1 and info["watertight"]
    assert info["bbox"][2] == pytest.approx(180, abs=0.5)
    assert (tmp_path / "r.step").stat().st_size > 1000


def test_diagnose_ignores_pieces_joined_later():
    late = ("from build123d import *\nlegL = Pos(-10,0,10)*Box(6,6,20)\nlegR = Pos(10,0,10)*Box(6,6,20)\n"
            "hip = Pos(0,0,22)*Box(30,8,6)\npart = legL + legR + hip\n")
    assert sandbox.diagnose(late)["kind"] == "OK"


def test_design_from_sheet_reports_outline(tmp_path, monkeypatch):
    sheet = _sheet(tmp_path / "ref.png")
    monkeypatch.setattr(codegen, "generate_code_photo", lambda *a, **k: (BOX, {}))
    monkeypatch.setattr(review, "review_once", lambda *a, **k: {"matches": True, "problems": [], "fix": ""})
    r = codegen.design_code_concept("box figure", sheet, tmp_path / "ab12cd34_part.stl", tmp_path / "ab12cd34.step")
    assert r["ok"] and r["review"]["iou"][0]["front"] > 0.9 and not r["review"]["fixed"]


def test_low_outline_overrides_a_lenient_review(tmp_path, monkeypatch):
    sheet = _sheet(tmp_path / "ref.png", front=(40, 40), side=(40, 40))
    wide = "from build123d import *\npart = Box(40, 40, 40, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
    monkeypatch.setattr(codegen, "generate_code_photo", lambda *a, **k: (BOX, {}))
    monkeypatch.setattr(codegen, "generate_code", lambda *a, **k: (wide, {}))
    monkeypatch.setattr(review, "review_once", lambda *a, **k: {"matches": True, "problems": [], "fix": ""})
    r = codegen.design_code_concept("cube figure", sheet, tmp_path / "ab12cd34_part.stl", tmp_path / "ab12cd34.step")
    rv = r["review"]
    assert any("윤곽" in p for p in rv["rounds"][0]["problems"])
    assert rv["fixed"] and len(rv["iou"]) == 2 and rv["iou"][1]["front"] > rv["iou"][0]["front"]


def test_endpoints_draw_then_build(tmp_path, monkeypatch):
    from realcad.web import app as web
    monkeypatch.setattr(web, "GEN", tmp_path)
    monkeypatch.setattr(concept, "draw", lambda prompt, out: _sheet(out))
    d = web.concept_ep(web.ConceptReq(prompt="cat figure"))
    assert d["kind"] == "concept" and (tmp_path / f"{d['token']}_concept.png").exists()
    assert "error" in web.design_concept_ep(web.ConceptReq(prompt="x", token="../../etc"))
    monkeypatch.setattr(codegen, "generate_code_photo", lambda *a, **k: (BOX, {}))
    monkeypatch.setattr(review, "review_once", lambda *a, **k: {"matches": True, "problems": [], "fix": ""})
    out = web.design_concept_ep(web.ConceptReq(prompt="cat figure", token=d["token"]))
    assert out.get("concept", "").endswith("_concept.png") and out["review"]["iou"] and out["downloads"]["STEP"]


def test_figure_requests_go_to_the_sheet(monkeypatch):
    from realcad.web import app as web
    req = web.DesignReq(prompt="고양이 피규어 만들어줘")
    assert web._wants_concept(req, "organic")
    assert not web._wants_concept(web.DesignReq(prompt="고양이 피규어", concept=False), "organic")
    assert not web._wants_concept(web.DesignReq(prompt="M3 bracket with slots"), "code: no template fits")


def test_floating_bits_on_a_many_solid_compound_are_rejected(tmp_path):
    code = ("from build123d import *\nbody = Box(40, 40, 40, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
            "bumps = [Pos(-15 + 3 * i, 0, 40) * Sphere(radius=2) for i in range(11)]\n"
            "dot = Pos(0, 0, 60) * Sphere(radius=1.5)\n"
            "part = Compound(children=[body, *bumps, dot])\n")
    with pytest.raises(sandbox.SandboxError, match="공중에 뜬"):
        sandbox.execute_to_files(code, tmp_path / "f_part.stl", tmp_path / "f.step")
    ok = code.replace("dot = Pos(0, 0, 60)", "dot = Pos(0, 0, 41)")
    sandbox.execute_to_files(ok, tmp_path / "g_part.stl", tmp_path / "g.step")


def test_sheet_split_when_the_drawings_almost_touch(tmp_path):
    im = Image.new("RGB", (1000, 600), "white"); d = ImageDraw.Draw(im)
    d.rectangle([100, 100, 495, 500], fill="black"); d.rectangle([505, 150, 900, 500], fill="black")   # 9 px apart
    im.save(tmp_path / "close.png")
    assert concept.sheet_masks(tmp_path / "close.png") is not None


def test_outline_overlay_and_widths(tmp_path):
    stl, step = tmp_path / "ab12cd34_part.stl", tmp_path / "ab12cd34.step"
    sandbox.execute_to_files(BOX, stl, step)
    sheet = _sheet(tmp_path / "wide.png", front=(40, 40), side=(10, 40))
    assert concept.diff_png(sheet, stl, tmp_path / "d.png").exists()
    prof = concept.profile_text(sheet, stl)
    assert "FRONT" in prof and "too narrow" in prof and "SIDE" not in prof


def test_review_rounds_stop_when_a_fix_does_not_help(tmp_path, monkeypatch):
    sheet = _sheet(tmp_path / "ref.png", front=(40, 40), side=(40, 40))
    worse = "from build123d import *\npart = Box(10, 10, 40, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
    monkeypatch.setattr(codegen, "generate_code_photo", lambda *a, **k: (BOX, {}))
    seen = []
    monkeypatch.setattr(codegen, "generate_code", lambda *a, **k: (seen.append(k.get("image_url")), (worse, {}))[1])
    monkeypatch.setattr(review, "review_once", lambda *a, **k: {"matches": True, "problems": [], "fix": ""})
    r = codegen.design_code_concept("cube figure", sheet, tmp_path / "ab12cd34_part.stl", tmp_path / "ab12cd34.step")
    rv = r["review"]
    assert r["code"] == BOX and not rv["fixed"] and rv["tries"] == 1 and rv["rejected"] == 1
    assert isinstance(seen[0], list) and len(seen[0]) == 2          # the sheet and the outline overlay
    assert not list(tmp_path.glob("*try*"))
