"""RealCAD web backend (FastAPI). Prompt -> Meta design -> verify/fix loop -> STEP/STL.

Run: PYTHONPATH=src .venv/bin/python -m uvicorn realcad.web.app:app --port 8750
"""
from __future__ import annotations
import json
import re
import uuid
from pathlib import Path

import base64
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..agent.planner import plan, plan_photo
from ..agent.clarify import clarify, augment
from ..agent.loop import run
from ..agent import codegen
from ..agent import product_spec
from ..agent import editor
from ..contract.schema import DesignContract
from ..fasteners.standards import resolve as _resolve_fastener
from ..geometry import builder as g
from ..export import exporters as ex

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "web"
GEN = WEB / "gen"
GEN.mkdir(parents=True, exist_ok=True)


def _prune_gen(keep: int = 300) -> None:
    """On startup keep only the latest keep outputs (grouped by token) so the output folder does not grow forever."""
    try:
        files = sorted(GEN.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        toks = []
        for f in files:
            t = f.name.split("_")[0].split(".")[0]
            if t not in toks:
                toks.append(t)
        old = set(toks[keep:])
        for f in files:
            if f.name.split("_")[0].split(".")[0] in old:
                f.unlink(missing_ok=True)
    except Exception:
        pass


_prune_gen()

import os as _os
# When exposed via a public tunnel etc.: if REALCAD_TOKEN is set, every /api/* request needs the X-RealCAD-Token header (or ?token=).
_TOKEN = _os.environ.get("REALCAD_TOKEN", "").strip()
app = FastAPI(title="RealCAD", docs_url=None, redoc_url=None, openapi_url=None)

MAX_UPLOAD = 60 * 1024 * 1024          # 60MB upload limit
_MESH_EXT = {"stl", "obj", "3mf", "ply", "step", "stp"}
_IMG_MIME = {"image/jpeg", "image/png", "image/webp"}


def _safe_err(e: Exception) -> str:
    """Strip absolute server paths from exception messages (minimize client exposure)."""
    return f"{type(e).__name__}: {e}".replace(str(ROOT), "<realcad>")


def _ext(filename: str | None, allowed: set[str]) -> str:
    name = (filename or "").lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if not re.fullmatch(r"[a-z0-9]{1,5}", ext) or ext not in allowed:
        raise ValueError(f"지원하지 않는 파일 형식: .{ext or '?'} (허용: {', '.join(sorted(allowed))})")
    return ext


async def _read_limited(up: UploadFile, limit: int = MAX_UPLOAD) -> bytes:
    data = await up.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"파일이 너무 큽니다(최대 {limit // 1024 // 1024}MB)")
    return data


@app.middleware("http")
async def _auth_mw(request, call_next):
    if _TOKEN and request.url.path.startswith("/api/"):
        tok = request.headers.get("x-realcad-token") or request.query_params.get("token")
        if tok != _TOKEN:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "인증 필요(X-RealCAD-Token)"}, status_code=401)
    return await call_next(request)

# Interactive edit session state (process memory). sid -> {"mode":"code","code":str}
#                                           or {"mode":"param","contract":dict}
SESSIONS: dict[str, dict] = {}
_SESS_MAX = 200
# Persist sessions to disk so parts on screen stay editable after a server restart (memory only meant "session expired" and a new design).
_SESS_FILE = ROOT / "out" / "sessions.json"   # outside web/: not served statically and not subject to output cleanup (out/ is gitignored)
_SESS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _sess_load() -> None:
    try:
        import json as _j
        SESSIONS.update(_j.loads(_SESS_FILE.read_text()))
    except Exception:
        pass


def _sess_save() -> None:
    try:
        import json as _j
        keep = dict(list(SESSIONS.items())[-_SESS_MAX:])
        tmp = _SESS_FILE.with_suffix(".tmp")
        tmp.write_text(_j.dumps(keep, ensure_ascii=False, default=str))
        tmp.replace(_SESS_FILE)
    except Exception:
        pass


_sess_load()


def _new_sid() -> str:
    sid = uuid.uuid4().hex[:12]
    if len(SESSIONS) > _SESS_MAX:          # drop the oldest first to avoid leaking memory
        for k in list(SESSIONS)[: len(SESSIONS) - _SESS_MAX]:
            SESSIONS.pop(k, None)
    return sid


class ClarifyReq(BaseModel):
    prompt: str


class PrintSettings(BaseModel):
    """Left sidebar values (Printer -> Filament -> Process). Feed checks M1 (nozzle), H3 (material k), P1 (hole compensation) and the build volume."""
    material: str | None = None       # pla | petg | abs | tpu | steel | aluminum
    nozzle: float | None = None       # mm
    hole_comp: float | None = None    # mm
    build: list[float] | None = None  # [x, y, z] mm
    iters: int | None = None          # max auto-fix attempts (0 = off)


def _apply_settings(c, st: "PrintSettings | None"):
    if not st:
        return c
    # Material: if the prompt names a metal (planner wrote steel/aluminum), do not overwrite it with the sidebar plastic value
    if st.material and str(getattr(c, "material", "pla") or "pla").lower() in ("pla", "petg", "abs", "tpu", "plastic", ""):
        try: c.material = str(st.material).lower()
        except Exception: pass
    if st.nozzle:
        try: setattr(c, "nozzle", max(0.1, min(float(st.nozzle), 2.0)))
        except Exception: pass
    if st.hole_comp is not None and hasattr(c, "hole_comp"):
        try: c.hole_comp = max(0.0, min(float(st.hole_comp), 1.0))
        except Exception: pass
    return c


def _settings_note(st: "PrintSettings | None") -> str:
    """The code path has no contract, so append manufacturing conditions to the prompt as one line (the model applies them to walls and holes)."""
    if not st:
        return ""
    bits = []
    if st.material: bits.append(f"material {st.material}")
    if st.nozzle: bits.append(f"FDM nozzle {st.nozzle} mm (min wall {round(st.nozzle*2,2)} mm)")
    if st.hole_comp is not None: bits.append(f"add {st.hole_comp} mm to hole diameters for FDM shrink")
    if st.build and len(st.build) == 3: bits.append(f"must fit build volume {int(st.build[0])}x{int(st.build[1])}x{int(st.build[2])} mm")
    return (" (" + ", ".join(bits) + ")") if bits else ""


class DesignReq(BaseModel):
    prompt: str
    answers: dict | None = None
    settings: PrintSettings | None = None
    concept: bool | None = None       # False: build a figure directly, without drawing a reference sheet first


@app.post("/api/clarify")
def clarify_ep(req: ClarifyReq):
    qs, _usage = clarify(req.prompt)
    return {"questions": qs}


FREEFORM_MSG = "이 모양은 아직 바로 만들지 못했어요. 크기나 생김새를 조금 더 자세히 말해 주세요."


def _finding(f) -> dict:
    return {"code": f.code, "severity": f.severity, "ok": f.ok,
            "message": f.message, "actual": f.actual, "required": f.required,
            "standard": f.standard, "suggestion": f.suggestion}


@app.post("/api/design")
def design(req: DesignReq):
    try:
        return _design(req)
    except Exception as e:
        return {"error": _safe_err(e)}


def _design(req: DesignReq):
    contract, _usage, _raw = plan(augment(req.prompt, req.answers))
    _apply_settings(contract, getattr(req, "settings", None))
    if contract.kind == "retrieve":
        # Organic (freeform) shapes: build surfaces with local code generation (loft/ellipsoid/sweep/fillet), no external API.
        # Only on failure suggest retrieval. Generated with organic techniques, not forced into a box.
        r = contract.retrieve
        if _wants_concept(req, str(r.note or "")):
            return _draw_concept(req.prompt)
        tok = uuid.uuid4().hex[:8]
        stl_path = GEN / f"{tok}_part.stl"; step_path = GEN / f"{tok}.step"
        cr = codegen.design_code(req.prompt + _settings_note(getattr(req, "settings", None)), stl_path, step_path, max_iters=3)
        if cr["ok"]:
            out = _emit_code(tok, stl_path, step_path, cr, _new_sid())
            if str(r.note or "").startswith("code:"):
                out["route"] = "code"            # did not fit a template, so built via code
                out["route_note"] = str(r.note)[5:].strip()
            else:
                out["organic"] = True
            return out
        return {"error": cr.get("error") or FREEFORM_MSG, "diag": cr.get("diag") or [], "mode": "code"}
    _it = getattr(req, "settings", None) and req.settings.iters
    return _respond(run(contract, max_iters=(3 if _it is None else max(0, min(int(_it), 5)))))


_CONCEPT_ON = _os.environ.get("REALCAD_CONCEPT", "1") != "0"
_TOK = re.compile(r"^[0-9a-f]{8}$")


def _wants_concept(req, note: str) -> bool:
    """Figures, animals and characters have no fixed dimensions: draw a reference sheet first."""
    if not _CONCEPT_ON or req.concept is False:
        return False
    p = req.prompt
    return (not note.startswith("code:")) or codegen._is_organic(p) or codegen._is_mecha(p) or codegen._is_character(p)


def _draw_concept(prompt: str) -> dict:
    from ..agent import concept
    tok = uuid.uuid4().hex[:8]
    concept.draw(prompt, GEN / f"{tok}_concept.png")
    return {"kind": "concept", "token": tok, "image": f"gen/{tok}_concept.png", "prompt": prompt}


class ConceptReq(BaseModel):
    prompt: str
    token: str | None = None
    settings: PrintSettings | None = None


@app.post("/api/concept")
def concept_ep(req: ConceptReq):
    """Draw (or redraw) the front + side reference sheet with Meta Muse Image. Nothing is built yet."""
    try:
        return _draw_concept(req.prompt)
    except Exception as e:
        return {"error": _safe_err(e)}


@app.post("/api/design_concept")
def design_concept_ep(req: ConceptReq):
    """Build the part from a confirmed reference sheet: Muse Spark looks at it, the engine checks it,
    and the outline of the result is measured against the sheet."""
    try:
        if not req.token or not _TOK.match(req.token):
            return {"error": "그림 번호가 올바르지 않아요."}
        sheet = GEN / f"{req.token}_concept.png"
        if not sheet.exists():
            return {"error": "그림을 찾지 못했어요. 다시 그려 주세요."}
        tok = uuid.uuid4().hex[:8]
        stl_path = GEN / f"{tok}_part.stl"; step_path = GEN / f"{tok}.step"
        cr = codegen.design_code_concept(req.prompt + _settings_note(req.settings), sheet, stl_path, step_path, max_iters=3)
        if not cr["ok"]:
            return {"error": cr.get("error") or FREEFORM_MSG, "diag": cr.get("diag") or [], "mode": "code",
                    "concept": f"gen/{req.token}_concept.png"}
        out = _emit_code(tok, stl_path, step_path, cr, _new_sid())
        out["organic"] = True
        out["concept"] = f"gen/{req.token}_concept.png"
        return out
    except Exception as e:
        return {"error": _safe_err(e), "mode": "code"}


def _mesh_stats(tm) -> dict:
    """For the summary at the top of the screen: dimensions (mm), volume (cm^3), surface area (cm^2), PLA weight estimate (100% infill, 1.24 g/cm^3), rough pre-slicer figures.
    Only values computable without slicing (the slicer decides print time)."""
    try:
        ext = tm.bounding_box.extents
        vol = float(abs(tm.volume)) / 1000.0            # mm³ → cm³
        area = float(tm.area) / 100.0                   # mm² → cm²
        return {
            "bbox_mm": [round(float(x), 1) for x in ext],
            "volume_cm3": round(vol, 2),
            "area_cm2": round(area, 1),
            "pla_g_solid": round(vol * 1.24, 1),        # 100% infill
            "pla_g_20pct": round((min(area * 0.12, vol) + max(vol - area * 0.12, 0) * 0.2) * 1.24, 1),  # assume two 1.2mm walls + 20% infill
            "faces": int(len(tm.faces)),
            "watertight": bool(tm.is_watertight),
        }
    except Exception as e:  # pragma: no cover
        return {"error": f"{type(e).__name__}"}


def _respond(r, sid: str | None = None):
    c, part = r["contract"], r["part"]

    bolts = None
    fastener_name = "-"
    hole_dia = None
    if c.kind == "plate":
        f, _exact, _note = _resolve_fastener(c.fastener)
        fastener_name = f.name if _exact else f"{f.name} (요청 {c.fastener!r} 미지원)"
        if getattr(c, "hole_type", "through") == "tapped":
            hole_dia = round(c.hole_dia or (f.nominal_dia_mm - 1.0825 * f.pitch_mm), 2)
        else:
            hole_dia = round(c.hole_dia or f.clearance(c.fit), 2)
        grip = c.plate.thickness + 5          # pass through the plate and stick out slightly (clean render)
        for h in c.holes:
            b = g.place(g.hex_bolt_solid(f, grip), h.x, h.y)
            bolts = b if bolts is None else bolts + b

    tok = uuid.uuid4().hex[:8]
    stl_path = GEN / f"{tok}_part.stl"
    # Assembly: with exploded spacing, display and export use the spread state; checks and drawings use the assembled state
    asm = getattr(part, "_rc_asm", None) if c.kind == "assembly" else None
    disp = part
    parts_out, mates, layout, asm_bom = None, None, None, None
    if asm is not None:
        gap = float(getattr(c.assembly, "exploded", 0.0) or 0.0)
        disp = asm.exploded(gap) if gap > 0 else part
        parts_out = []
        for i, (pi, solid) in enumerate(asm.part_solids(gap)):
            ex.to_stl(solid, GEN / f"{tok}_p{i}.stl")
            parts_out.append({"no": pi.no, "name": pi.name, "spec": pi.spec, "qty": pi.qty, "material": pi.material,
                              "color": pi.color, "url": f"gen/{tok}_p{i}.stl"})
        mates, layout, asm_bom = asm.mates, asm.layout, asm.bom
        import csv as _csv
        with (GEN / f"{tok}_bom.csv").open("w", newline="", encoding="utf-8") as fp:
            w = _csv.DictWriter(fp, fieldnames=["no", "item", "spec", "qty", "material"]); w.writeheader()
            for row in asm_bom: w.writerow(row)
    ex.to_stl(disp, stl_path)
    ex.to_step(disp, GEN / f"{tok}.step")
    # Export formats: STL (engine), 3MF and OBJ (trimesh conversion), STEP
    import trimesh
    tm = trimesh.load(str(stl_path))
    (GEN / f"{tok}.obj").write_text(tm.export(file_type="obj"))
    (GEN / f"{tok}.3mf").write_bytes(tm.export(file_type="3mf"))
    bolts_url = None
    bom = []
    if bolts is not None:
        ex.to_stl(bolts, GEN / f"{tok}_bolts.stl")
        bolts_url = f"gen/{tok}_bolts.stl"
    dxf_url = None
    from ..export.drawing import write_drawing
    _z = (-c.plate.thickness / 2 if c.kind == "plate" else (layout["z_axis"] if layout else None))   # assemblies: section through the axis (assembly drawing)
    if write_drawing(part, GEN / f"{tok}.dxf", z=_z, contract=c, fastener=(f if c.kind == "plate" else None),
                     title=(f"RealCAD {c.kind}" if c.kind != "assembly" else "RealCAD power train assembly, section through shaft axis")) \
            or ex.to_dxf(part, GEN / f"{tok}.dxf", z=_z):
        dxf_url = f"gen/{tok}.dxf"
    pdf_url = None                                        # three-view + isometric shop drawing (PDF)
    try:
        from ..export.views import write_views_pdf
        if write_views_pdf(part, GEN / f"{tok}.pdf", title=f"RealCAD {c.kind}",
                           part_number=tok[:8].upper(), material=getattr(c, "material", "")):
            pdf_url = f"gen/{tok}.pdf"
    except Exception:
        pdf_url = None
    dfam = None                                          # measured wall thickness + orientation recommendation
    try:
        from ..verify import dfam as _dfam
        dfam = _dfam.measure(part)
    except Exception:
        dfam = None
    if asm_bom:
        bom = asm_bom
    if c.kind == "plate":
        from ..export.bom import make_bom, write_bom_csv
        _eng = next((x.actual for x in r["findings"] if x.code == "H3"), None)
        bom = make_bom(c, f, r["hole_dia"] if r.get("hole_dia") else hole_dia or 0.0, _eng)
        write_bom_csv(bom, GEN / f"{tok}_bom.csv")

    # Store the current contract in the edit session (seed for follow-up edits like "bigger" or "add a hole")
    sid = sid or _new_sid()
    SESSIONS[sid] = {"mode": "param", "contract": c.to_dict()}
    _sess_save()

    return {
        "passed": r["summary"]["passed"],
        "iters": r["iters"],
        "fixed": r["fixed"],
        "kind": c.kind,
        "fastener": fastener_name,
        "hole_dia": hole_dia,
        "findings": [_finding(x) for x in r["findings"]],
        "contract": c.to_dict(),
        "session": sid,
        "part_url": f"gen/{tok}_part.stl",
        "bolts_url": bolts_url,
        "bom": bom,
        **({"parts": parts_out, "mates": mates, "layout": layout} if parts_out else {}),
        "stats": _mesh_stats(tm),
        **({"dfam": dfam} if dfam else {}),
        "downloads": {
            "STL": f"gen/{tok}_part.stl",
            "3MF": f"gen/{tok}.3mf",
            "STEP": f"gen/{tok}.step",
            "OBJ": f"gen/{tok}.obj",
            **({"BOM": f"gen/{tok}_bom.csv"} if bom else {}),
            **({"DXF": dxf_url} if dxf_url else {}),
            **({"PDF": pdf_url} if pdf_url else {}),
        },
    }


class DesignCodeReq(BaseModel):
    prompt: str
    answers: dict | None = None
    settings: PrintSettings | None = None
    spec_text: str | None = None      # authoritative dimension block returned by /api/spec_lookup (SPEC, KEEP CLEAR)


class SpecLookupReq(BaseModel):
    prompt: str


@app.post("/api/spec_lookup")
def spec_lookup_ep(req: SpecLookupReq):
    """Commercial product spec lookup: find outer dimensions of off-the-shelf products named in the prompt, first in official spec tables, then from Meta's memory (with confidence),
    and return a confirmed / estimated / unknown table plus up to 3 questions about mating object dimensions no model knows. Front end of the general CAD path."""
    try:
        card = product_spec.lookup(req.prompt)
        d = card.to_dict()
        d["usage"] = {k: v for k, v in (card.usage or {}).items() if k in ("prompt_tokens", "completion_tokens", "error")}
        return d
    except Exception as e:
        return {"products": [], "questions": [], "counterpart": "", "spec_text": "", "error": _safe_err(e)}


def _emit_code(tok: str, stl_path: Path, step_path: Path, r: dict, sid: str) -> dict:
    """Successful code generation/edit result (r) -> web response. sandbox already wrote STL/STEP; convert to OBJ/3MF."""
    ex._clean_degenerate(stl_path)              # clean pole degenerate faces (watertight)
    import trimesh
    tm = trimesh.load(str(stl_path))
    (GEN / f"{tok}.obj").write_text(tm.export(file_type="obj"))
    (GEN / f"{tok}.3mf").write_bytes(tm.export(file_type="3mf"))
    # Keep code as the seed for follow-up edits + push undo history (previous success, last 20)
    _prev = SESSIONS.get(sid)
    _hist = (_prev.get("hist") if _prev else None) or []
    if _prev and _prev.get("mode") == "code" and _prev.get("code") and not r.get("_norecord"):
        _hist = (_hist + [_prev["code"]])[-20:]
    # Amount of change: compare volume and size with the previous version, to confirm something actually changed before saying "fixed".
    _vol = float(tm.volume) if tm.is_volume else None
    _ext = [round(float(x), 2) for x in tm.extents]
    _change = None
    if _prev and _prev.get("vol") is not None and _vol is not None:
        _dv = _vol - _prev["vol"]
        _change = {"dv_mm3": round(_dv, 1), "dv_pct": round(100 * _dv / max(_prev["vol"], 1e-6), 2),
                   "size_from": _prev.get("ext"), "size_to": _ext}
        _change["visible"] = abs(_dv) >= 1.0 or any(abs(a - b) >= 0.2 for a, b in zip(_prev.get("ext") or _ext, _ext))
    SESSIONS[sid] = {"mode": "code", "code": r["code"], "hist": _hist, "step": str(step_path), "vol": _vol, "ext": _ext}
    _sess_save()
    _hard = [f for f in (r.get("findings") or []) if f.get("severity") == "HARD"]
    _dxf = None
    try:
        from build123d import import_step
        from ..export.drawing import write_drawing
        _p = import_step(str(step_path))
        if write_drawing(_p, GEN / f"{tok}.dxf", title="RealCAD part") or ex.to_dxf(_p, GEN / f"{tok}.dxf"):
            _dxf = f"gen/{tok}.dxf"
    except Exception:
        _dxf = None
    _pdf = None                                          # three-view + isometric shop drawing (PDF)
    try:
        from build123d import import_step as _imp
        from ..export.views import write_views_pdf
        if write_views_pdf(_imp(str(step_path)), GEN / f"{tok}.pdf",
                           title="RealCAD part", part_number=tok[:8].upper()):
            _pdf = f"gen/{tok}.pdf"
    except Exception:
        _pdf = None
    _dfam = None                                         # measured wall thickness + orientation recommendation
    try:
        from build123d import import_step as _imp2
        from ..verify import dfam as _dfammod
        _dfam = _dfammod.measure(_imp2(str(step_path)))
    except Exception:
        _dfam = None
    _faces_url = _view_url = None
    try:                                         # B-rep face map so the screen can pick real faces
        from ..export import facemap
        if facemap.build(step_path, GEN / f"{tok}_view.stl", GEN / f"{tok}_faces.json"):
            _faces_url, _view_url = f"gen/{tok}_faces.json", f"gen/{tok}_view.stl"
    except Exception as _e:
        print(f"[facemap] skipped: {type(_e).__name__}: {_e}", flush=True)
    _rv = r.get("review")
    if isinstance(_rv, dict):                         # so the image Meta saw can be opened on screen too
        _rv = {**_rv, "images": [f"gen/{n}" for n in _rv.get("images") or []]}
    return {
        "review": _rv,
        "diag": r.get("diag") or [],
        "faces_url": _faces_url,
        "view_url": _view_url,
        "passed": all(f.get("ok") for f in _hard),
        "iters": r["iters"],
        "fixed": r["fixed"],
        "kind": "code",
        "mode": "code",
        "fastener": "-",
        "hole_dia": None,
        "findings": r["findings"],
        "code": r["code"],
        "info": r["info"],
        "measure": r.get("measure"),
        "stats": _mesh_stats(tm),
        **({"dfam": _dfam} if _dfam else {}),
        "change": _change,
        "session": sid,
        "part_url": f"gen/{tok}_part.stl",
        "bolts_url": None,
        "downloads": {
            "STL": f"gen/{tok}_part.stl",
            "3MF": f"gen/{tok}.3mf",
            "STEP": f"gen/{tok}.step",
            "OBJ": f"gen/{tok}.obj",
            **({"DXF": _dxf} if _dxf else {}),
            **({"PDF": _pdf} if _pdf else {}),
        },
    }


@app.post("/api/design_code")
def design_code_ep(req: DesignCodeReq):
    """Code-generation CAD: the AI writes build123d code directly to make arbitrary mechanical parts (sandboxed, auto-fix).

    The "anything" path for what the template menu cannot do.
    """
    try:
        prompt = req.prompt + _settings_note(getattr(req, "settings", None))
        if req.spec_text:
            prompt += "\n\n" + req.spec_text.strip()
        meas = product_spec.answers_text(req.answers)
        prompt += ("\n\n" + meas) if meas else ""
        tok = uuid.uuid4().hex[:8]
        stl_path = GEN / f"{tok}_part.stl"
        step_path = GEN / f"{tok}.step"
        r = codegen.design_code(prompt, stl_path, step_path, max_iters=3)
        if not r["ok"]:
            return {"error": r["error"], "code": r.get("code", ""), "diag": r.get("diag") or [],
                    "iters": r.get("iters", 0), "mode": "code"}
        return _emit_code(tok, stl_path, step_path, r, _new_sid())
    except Exception as e:
        return {"error": _safe_err(e), "mode": "code"}


class RegisterCodeReq(BaseModel):
    code: str


@app.post("/api/register_code")
def register_code_ep(req: RegisterCodeReq):
    """Run externally written build123d code in the sandbox and register it as a session (editable/undoable afterwards).
    The UI calls it via URL ?code=gen/file.py. The code must pass the same AST/sandbox rules as design_code."""
    try:
        tok = uuid.uuid4().hex[:8]
        stl_path = GEN / f"{tok}_part.stl"
        step_path = GEN / f"{tok}.step"
        from ..agent import sandbox
        info = sandbox.execute_to_files(req.code, stl_path, step_path)
        r = {"ok": True, "code": req.code, "info": info, "findings": codegen._findings(info), "iters": 0, "fixed": False}
        return _emit_code(tok, stl_path, step_path, r, _new_sid())
    except Exception as e:
        return {"error": _safe_err(e), "mode": "code"}


_WHISPER_MODEL = _os.environ.get("REALCAD_WHISPER_MODEL", str(Path.home() / ".cache/whisper/ggml-small.bin"))
# Giving whisper an example sentence (--prompt) makes it emit that sentence verbatim on noise or unclear audio (it once auto-ran
# "set the hole diameter to 5mm"). So no example sentence is used, and old example sentences are discarded if they show up.
# Descriptive sentence, not a command (cannot execute if it leaks, and is filtered by the list below). A word list would invite comma-list transcription.
_WHISPER_PROMPT = {"ko": "부품의 턱과 홀이 몇 밀리미터로 뚫려 있는지, 옆 벽 높이와 두께에 관한 대화입니다.",
                   "en": "A conversation about a part's ledges, holes, wall height and thickness in millimeters."}
_WHISPER_PROMPT_LEAK = ("부품의 턱과 홀이 몇 밀리미터로 뚫려 있는지", "옆 벽 높이와 두께에 관한 대화입니다", "관한 대화", "대화입니다", "엔터라고 하면", "바로 보냅니다",
                        "A conversation about a part", "구멍 지름을 5mm로 해줘", "홀이 몇 mm로 뚫려 있어", "이 턱 두 면을 옆 벽 높이까지 올려줘",
                        "부품 설계 프로그램에 말하는 명령입니다", "RealCAD 설계 명령", "face, wall, floor")
# Common sentences whisper hallucinates on silence or noise (artifacts of YouTube caption training)
_WHISPER_JUNK = re.compile(r"(이 영상은|영상의 정보|정보를 포함하고|시청해\s*주셔서|구독|좋아요\s*(와|,)\s*구독|알림\s*설정|MBC|KBS|자막|thank(s| you) for watching|subscribe)", re.I)


@app.post("/api/transcribe")
async def transcribe_ep(audio: UploadFile = File(...), lang: str = Form("ko")):
    """Conversation mode speech -> text. The browser sends each utterance as 16 kHz WAV and local whisper.cpp transcribes it.
    Does not rely on the browser's built-in speech recognition (external servers), so it behaves the same in Safari and Chrome."""
    import shutil, subprocess, tempfile
    try:
        data = await _read_limited(audio, 8 * 1024 * 1024)
        if len(data) < 3200:                      # under 0.1 s
            return {"text": ""}
        exe = shutil.which("whisper-cli")
        if not exe or not Path(_WHISPER_MODEL).exists():
            return {"error": "whisper-cli 또는 모델이 없어요(brew install whisper-cpp, ~/.cache/whisper/ggml-small.bin)"}
        lg = "en" if str(lang).lower().startswith("en") else "ko"
        with tempfile.TemporaryDirectory() as td:
            wav = Path(td) / "a.wav"
            wav.write_bytes(data)
            out = subprocess.run([exe, "-m", _WHISPER_MODEL, "-l", lg, "-nt", "-np", "-t", "6", "-sns",
                                  "--prompt", _WHISPER_PROMPT[lg], "-f", str(wav)],
                                 capture_output=True, text=True, timeout=60)
        text = " ".join(out.stdout.split()).strip().lstrip("-–~ ").strip()
        core = re.sub(r"[\W_]+", "", text)
        short_ok = core in ("응", "네", "예", "아니", "아뇨", "좋아", "그래", "ok", "OK", "yes", "no")
        _flat = re.sub(r"[\W_]+", "", text)
        if any(re.sub(r"[\W_]+", "", k) in _flat or (len(_flat) >= 8 and _flat in re.sub(r"[\W_]+", "", k)) for k in _WHISPER_PROMPT_LEAK):
            print(f"[voice] dropped prompt leak: {text!r}", flush=True)
            return {"text": "", "dropped": text}
        if _WHISPER_JUNK.search(text) or (len(core) < 2 and not short_ok) or core in ("끝", "음", "어", "감사합니다", "고맙습니다", "안녕하세요"):
            print(f"[voice] dropped: {text!r} ({len(data)} B)", flush=True)
            return {"text": "", "dropped": text}
        print(f"[voice] heard: {text!r} ({len(data)} B)", flush=True)
        return {"text": text}
    except Exception as e:
        return {"error": _safe_err(e)}


class EditReq(BaseModel):
    session: str
    instruction: str
    settings: PrintSettings | None = None
    faces: list[dict] | None = None     # faces picked on screen [{point, normal, center, area}] -> push/pull
    face_text: str | None = None        # face description for the model when it is not a push/pull


@app.post("/api/edit")
def edit_ep(req: EditReq):
    """Interactive edit: minimally modify the session's current design (code or contract) per a follow-up instruction (not a full regeneration).

    e.g. code: "make a remote" (design_code) -> "add 5 buttons" (edit)
         contract: "make a tumbler" (design) -> "bigger, 3mm thick" (edit)
    """
    inst = (req.instruction or "").strip()
    if not inst:
        return {"error": "수정 내용을 입력하세요."}
    st = SESSIONS.get(req.session)
    if not st:
        return {"error": "세션이 만료됐어요. 먼저 설계를 새로 생성한 뒤 수정하세요.",
                "expired": True}
    try:
        if st["mode"] == "code" and req.faces:
            fo = _face_op(st, req, inst)
            if fo is not None:
                return fo
        if req.face_text:
            measured = ""
            if st.get("mode") == "code" and req.faces:
                try:
                    measured = _face_dims_text(st, req.faces)
                except Exception as _e:
                    print(f"[face dims] {type(_e).__name__}: {_e}", flush=True)
            inst = (req.face_text.strip() + measured +
                    " Change the design PARAMETERS that define these faces (not a patch on top), so features attached to them "
                    "(walls, ledges, rims around them) move and resize with them, like a parametric CAD history. "
                    "Do not change anything else: same hole sizes, same feet, same fillets. ") + inst
        if st["mode"] == "code":
            tok = uuid.uuid4().hex[:8]
            stl_path = GEN / f"{tok}_part.stl"
            step_path = GEN / f"{tok}.step"
            # Do not append sidebar manufacturing conditions (hole +0.2 etc.) on edits: otherwise holes grew by 0.2 on every edit
            r = editor.design_edit_code(st["code"], inst, stl_path, step_path, max_iters=3)
            if not r["ok"]:
                # Edit failed: session code keeps the previous success (so it can be undone)
                return {"error": r["error"], "code": r.get("code", ""),
                        "iters": r.get("iters", 0), "mode": "code",
                        "session": req.session, "edited": True}
            out = _emit_code(tok, stl_path, step_path, r, req.session)
            out["edited"] = True
            return out
        # Parametric contract edit
        prior = st["contract"]
        new_c, _u, _raw = editor.edit_contract(prior, inst)
        _apply_settings(new_c, getattr(req, "settings", None))
        if new_c.kind == "retrieve":
            return {"error": "이 수정은 치수만 바꿔서는 할 수 없어요. 원하는 모양을 새로 말해 주세요.",
                    "session": req.session, "edited": True}
        out = _respond(run(new_c, max_iters=3), sid=req.session)
        out["edited"] = True
        out["diff"] = editor.diff_contract(prior, new_c.to_dict())
        return out
    except Exception as e:
        return {"error": _safe_err(e), "session": req.session}


def _face_dims_text(st: dict, faces: list[dict]) -> str:
    """Real dimensions (kernel) of the picked face: width x height for planes, diameter for cylinders. Helps the model find which variable to change."""
    from build123d import import_step
    from ..agent import faceops
    step = st.get("step")
    if not step or not Path(step).exists():
        return ""
    shape = import_step(step)
    out = []
    for k, fd in enumerate(faces[:8]):
        pt, nm = fd.get("point") or fd.get("center"), fd.get("normal")
        f = faceops._match(shape, pt, nm) if pt and nm else None
        if f is None:
            continue
        bb = f.bounding_box()
        out.append(f"face {k+1}: plane at level {round(faceops._vec(nm).normalized().dot(f.center()), 2)} mm, "
                   f"extent X {bb.min.X:.1f}..{bb.max.X:.1f} ({bb.size.X:.1f} mm), Y {bb.min.Y:.1f}..{bb.max.Y:.1f} ({bb.size.Y:.1f} mm), "
                   f"Z {bb.min.Z:.1f}..{bb.max.Z:.1f}, area {f.area:.0f} mm2")
    return (" Measured by the CAD kernel: " + "; ".join(out) + ".") if out else ""


def _face_op(st: dict, req: "EditReq", inst: str):
    """Push/pull the picked face. The kernel finds the face and rules (Meta if ambiguous) set only the distance. None if not applicable (falls back to a normal edit)."""
    from ..agent import faceops, sandbox
    import tempfile
    step = st.get("step")
    if not step or not Path(step).exists():
        td = Path(tempfile.mkdtemp())
        sandbox.execute_to_files(st["code"], td / "p.stl", td / "p.step")
        step = str(td / "p.step")
    info = faceops.analyze(step, req.faces[:8])
    p = faceops.plan(inst, info)
    if p.get("op") == "ask":
        return {"ask": p["question"], "session": req.session, "mode": "code"}
    if p.get("op") == "noop":
        return {"error": p["how"] + ". 몇 mm 올릴지 말해 주세요(예: 3mm 올려).", "session": req.session, "edited": True, "mode": "code"}
    if p.get("op") not in ("push", "cut"):
        return None
    dists = faceops.distances(p, info)
    if not any(abs(d) > 1e-3 for d in dists):
        return {"error": f"이미 그 높이예요({p.get('how', '')}). 바뀔 게 없어요.", "session": req.session, "edited": True, "mode": "code"}
    code = faceops.append_code(st["code"], info, dists, p.get("how", ""), flush="to_level" in p)
    tok = uuid.uuid4().hex[:8]
    stl_path = GEN / f"{tok}_part.stl"
    step_path = GEN / f"{tok}.step"
    try:
        sinfo = sandbox.execute_to_files(code, stl_path, step_path)
    except sandbox.SandboxError as e:
        return {"error": "면 밀고 당기기 실패: " + _safe_err(e), "session": req.session, "edited": True, "mode": "code"}
    r = {"ok": True, "code": code, "info": sinfo, "findings": codegen._findings(sinfo), "iters": 0, "fixed": False}
    out = _emit_code(tok, stl_path, step_path, r, req.session)
    n_ok = sum(1 for i in info if i.get("ok"))
    out["edited"] = True
    out["face_op"] = {"op": p["op"], "how": p.get("how", ""), "faces": n_ok, "missed": len(info) - n_ok,
                      "moves": [round(d, 2) for d in dists],
                      "from": [i["level"] for i in info if i.get("ok")]}
    return out


class BriefReq(BaseModel):
    history: list[dict]                 # [{"role":"user"|"assistant","text":...}]
    mode: str | None = None             # "cad" | "printer"
    spec_text: str | None = None        # off-the-shelf product dimensions found by /api/spec_lookup (use as is, do not ask)


_BRIEF = """You are RealCAD's design consultant (a CAD tool that builds real, printable mechanical parts).
The user describes what they want, often loosely. Your job: talk with them BEFORE anything is built, until the
request is clear enough to build exactly what they mean. Speak Korean, short and friendly, like to a high-school student.

Rules:
- Ask ONE question at a time, at most 3 questions in the whole conversation. Ask only what truly changes the shape
  (what it is for, the key size the user cares about, how it attaches or what fits into it). Never ask about things
  you can choose sensibly yourself (wall thickness, fillets, bottom thickness): choose them and list them as defaults.
- If a number is ambiguous (for example "길이 40센치" on a cup holder could be total height or an arm length), ask which.
- Give 2 to 4 short answer options the user can tap. Include one option that lets you decide (예: "알아서 정해줘").
- If the user says 알아서, 아무거나, 그냥 만들어, 바로, or the request is already clear, stop asking and finish.
- When finishing, write a complete build prompt in Korean that contains EVERY dimension in mm and every feature,
  plus the sensible defaults you chose, so a CAD model can build it without guessing.
- Units: 파이/Ø/지름 = diameter in mm, 센치/cm = x10 mm.

Reply JSON only, one of:
{"type":"ask","question":"<one short Korean question>","options":["..","..",".."]}
{"type":"ready","summary":"<1-3 short Korean lines: what will be built with key numbers>","defaults":["<chosen default 1>","..."],"prompt":"<complete Korean build prompt with all mm values>"}
"""


@app.post("/api/brief")
def brief_ep(req: BriefReq):
    """Pre-build consultation: Meta asks one question at a time to narrow things down, and when enough is known returns a summary and a finished design sentence (built once the user OKs it)."""
    from ..agent.meta_client import chat
    hist = [h for h in (req.history or []) if isinstance(h, dict) and h.get("text")][-14:]
    if not hist:
        return {"type": "ask", "question": "무엇을 만들어 드릴까요?", "options": []}
    asked = sum(1 for h in hist if h.get("role") == "assistant")
    convo = "\n".join(("사용자: " if h.get("role") == "user" else "RealCAD: ") + str(h["text"])[:600] for h in hist)
    extra = f"\n(Questions already asked: {asked}. " + ("You MUST finish now with type ready." if asked >= 3 else "") + ")"
    if req.spec_text:
        extra += ("\n(Known product dimensions, already looked up. Do NOT ask the user for these; use them as given. "
                  "Ask only about the other object the part attaches to, how it attaches, and orientation if it matters.)\n" + req.spec_text[:1500])
    if req.mode == "printer":
        extra += "\n(The user prints on an FDM 3D printer: keep walls >= 1.2 mm and avoid unsupported overhangs.)"
    try:
        content, _u = chat([{"role": "system", "content": _BRIEF}, {"role": "user", "content": convo + extra}],
                           json_mode=True, temperature=0.2, max_tokens=3000)
        d = json.loads(re.search(r"\{.*\}", content, re.S).group(0))
    except Exception as e:
        return {"type": "error", "error": _safe_err(e)}
    if d.get("type") == "ready" and d.get("prompt"):
        return {"type": "ready", "summary": str(d.get("summary") or "")[:600], "defaults": [str(x)[:120] for x in (d.get("defaults") or [])][:8],
                "prompt": str(d["prompt"])[:2000]}
    return {"type": "ask", "question": str(d.get("question") or "어떤 걸 만들까요?")[:300],
            "options": [str(x)[:60] for x in (d.get("options") or [])][:4]}


class AskReq(BaseModel):
    question: str
    session: str | None = None
    face_text: str | None = None


@app.post("/api/ask")
def ask_ep(req: AskReq):
    """Answer a question only (the part is not changed). e.g. "how big is that circle?", "what is the total height?".
    Gives the Meta model the current part code, kernel measurements (size, volume) and the picked face description, and asks for a short answer."""
    from ..agent.meta_client import chat
    q = (req.question or "").strip()
    if not q:
        return {"error": "질문이 비었어요."}
    st = SESSIONS.get(req.session or "") or {}
    ctx = []
    if st.get("ext"):
        ctx.append(f"Measured bounding box (mm, X x Y x Z): {st['ext']}; volume mm3: {round(st.get('vol') or 0)}")
    if st.get("mode") == "code" and st.get("code"):
        ctx.append("Current build123d source of the part (numbers here are the true dimensions):\n" + st["code"][:9000])
    elif st.get("contract"):
        ctx.append("Current design contract JSON:\n" + json.dumps(st["contract"], ensure_ascii=False)[:6000])
    if req.face_text:
        ctx.append("Faces the user has selected on screen: " + req.face_text[:1500])
    msg = ("You are RealCAD's assistant. The user is asking a QUESTION about the current part; do NOT design or change anything.\n"
           + ("\n\n".join(ctx) if ctx else "There is no part on screen yet.")
           + f"\n\nQuestion: {q}\n\nAnswer ONLY what was asked, in Korean, as short as possible (usually one sentence). "
           "Do not add any other dimensions, areas, volumes, tips or follow-up offers that were not asked for. "
           "If the question is not about the part (small talk, checking you are listening), reply in a few words and mention no numbers. "
           "For a size question give the exact mm number from the source or measurements (say diameter or radius). "
           "If 'that circle' is ambiguous, list only the circles with their diameters in one sentence. If you cannot tell, say so. "
           "No markdown, no middle dots, no dashes.")
    try:
        content, _u = chat([{"role": "user", "content": msg}], temperature=0.0, max_tokens=2500)
        return {"answer": content.strip()}
    except Exception as e:
        return {"error": _safe_err(e)}


class SketchReq(BaseModel):
    session: str | None = None
    plane: dict                         # {origin:[x,y,z], x_dir:[..], normal:[..]}
    loops: list[dict]                   # [{type:rect,cx,cy,w,h} | {type:circle,cx,cy,r} | {type:poly,pts:[[u,v],..]}]
    op: str = "boss"                    # boss | cut
    depth: float = 10.0
    end: str = "blind"                  # blind | mid | through
    reverse: bool = False
    base_step: str | None = None        # for parts without code (built from a template), use the current shape's STEP (gen/xxx.step) as the starting shape


@app.post("/api/sketch_feature")
def sketch_ep(req: SketchReq):
    """SolidWorks style: sketch on a plane/face -> extrude or cut. Appended to the part code, so undo works as usual."""
    import shutil
    from ..agent import sketchops, sandbox
    try:
        st = SESSIONS.get(req.session or "")
        code, base = None, None
        if st and st.get("mode") == "code":
            code = st["code"]
        elif req.base_step:
            if not re.fullmatch(r"gen/[A-Za-z0-9_.-]{1,80}\.step", req.base_step):
                return {"error": "시작 형상 경로가 이상해요"}
            src = (WEB / req.base_step).resolve()
            if src.parent != GEN.resolve() or not src.exists():
                return {"error": "시작 형상 파일을 못 찾았어요"}
            base = uuid.uuid4().hex[:12] + ".step"
            shutil.copyfile(src, sandbox.BASES_DIR / base)
        new = sketchops.apply(code, req.model_dump(), base)
        tok = uuid.uuid4().hex[:8]
        stl_path, step_path = GEN / f"{tok}_part.stl", GEN / f"{tok}.step"
        try:
            sinfo = sandbox.execute_to_files(new, stl_path, step_path)
        except sandbox.SandboxError as e:
            return {"error": "스케치로 만들기 실패: " + _safe_err(e), "mode": "code", "session": req.session}
        r = {"ok": True, "code": new, "info": sinfo, "findings": codegen._findings(sinfo), "iters": 0, "fixed": False}
        sid = req.session if st else _new_sid()
        out = _emit_code(tok, stl_path, step_path, r, sid)
        out["edited"] = bool(st)
        out["sketch"] = {"op": req.op, "end": req.end, "depth": req.depth, "loops": len(req.loops)}
        return out
    except ValueError as e:
        return {"error": str(e), "mode": "code", "session": req.session}
    except Exception as e:
        return {"error": _safe_err(e), "mode": "code", "session": req.session}


class UndoReq(BaseModel):
    session: str


@app.post("/api/undo")
def undo_ep(req: UndoReq):
    """Undo: restore the session's previous version (code).

    Plain undo (branching): editing after an undo discards later versions. Code mode only.
    """
    from ..agent import sandbox
    st = SESSIONS.get(req.session)
    if not st:
        return {"error": "세션이 만료됐어요. 먼저 설계를 새로 생성하세요.", "expired": True}
    if st.get("mode") != "code":
        return {"no_history": True, "msg": "이 설계는 되돌리기를 지원하지 않아요(코드 생성/수정만 가능)."}
    hist = list(st.get("hist") or [])
    if not hist:
        return {"no_history": True, "msg": "더 되돌릴 게 없어요. 첫 버전이에요."}
    prev_code = hist.pop()                       # make the previous version current
    try:
        tok = uuid.uuid4().hex[:8]
        stl_path = GEN / f"{tok}_part.stl"
        step_path = GEN / f"{tok}.step"
        info = sandbox.execute_to_files(prev_code, stl_path, step_path)
        r = {"code": prev_code, "info": info, "findings": codegen._findings(info),
             "iters": 0, "fixed": False, "_norecord": True}
        out = _emit_code(tok, stl_path, step_path, r, req.session)
        SESSIONS[req.session]["hist"] = hist     # remove the undone version from history (one step back)
        _sess_save()
        out["edited"] = True
        out["undone"] = True
        out["remaining"] = len(hist)
        return out
    except Exception as e:
        return {"error": f"되돌리기 실패: {_safe_err(e)}", "session": req.session}


@app.post("/api/design_photo")
async def design_photo(image: UploadFile = File(...), note: str = Form("")):
    try:
        mime = image.content_type or "image/jpeg"
        if mime not in _IMG_MIME:
            return {"error": "이미지는 JPEG/PNG/WebP만 받아요."}
        data = await _read_limited(image, 20 * 1024 * 1024)
        url = f"data:{mime};base64," + base64.b64encode(data).decode()
        contract, _u, _r = plan_photo(url, note)
        r = contract.retrieve if contract.kind == "retrieve" else None
        tok = uuid.uuid4().hex[:8]
        stl_path = GEN / f"{tok}_part.stl"; step_path = GEN / f"{tok}.step"
        cr = codegen.design_code_photo(url, note or (r.query if r else ""), stl_path, step_path, max_iters=3)
        if cr["ok"]:
            return _emit_code(tok, stl_path, step_path, cr, _new_sid())
        # if code generation fails, build with the template the planner chose
        if contract.kind != "retrieve":
            return _respond(run(contract, max_iters=3))
        return {"error": cr.get("error") or FREEFORM_MSG, "diag": cr.get("diag") or [], "mode": "code"}
    except Exception as e:
        return {"error": _safe_err(e)}


@app.post("/api/wrap")
async def wrap_ep(model: UploadFile = File(...), clearance: float = Form(2.0),
                  wall: float = Form(2.0), base: float = Form(2.0), top_gap: float = Form(5.0)):
    """Take an external reference (STEP/STL etc.), measure it and build an enclosure around it (assembly)."""
    try:
        import trimesh
        from ..verify import checks as v
        ext = _ext(model.filename, _MESH_EXT)
        data = await _read_limited(model)
        tok = uuid.uuid4().hex[:8]
        raw = GEN / f"{tok}_raw.{ext}"
        raw.write_bytes(data)
        ref_stl = GEN / f"{tok}_ref.stl"

        mounts = []
        standoff_h = 0.0
        if ext in ("step", "stp"):
            from build123d import import_step, export_stl, Pos as _Pos
            from ..geometry.analyze import detect_mount_holes
            part = import_step(str(raw))
            b = part.bounding_box()
            size = (b.size.X, b.size.Y, b.size.Z)
            cx, cy = (b.min.X + b.max.X) / 2, (b.min.Y + b.max.Y) / 2
            holes = detect_mount_holes(part)
            mounts = [(hx - cx, hy - cy) for (hx, hy, _r) in holes]
            standoff_h = 4.0 if mounts else 0.0
            # Seat the board on the bosses
            export_stl(_Pos(-cx, -cy, base + standoff_h - b.min.Z) * part, str(ref_stl))
        else:
            m = trimesh.load(str(raw), force="mesh")
            bb = m.bounds
            size = tuple(float(x) for x in (bb[1] - bb[0]))
            ctr = (bb[0] + bb[1]) / 2
            m.apply_translation([-ctr[0], -ctr[1], base - bb[0][2]])
            m.export(str(ref_stl))

        lid_url = None
        if mounts:   # board holes detected -> sealed type (body + lid + corner screws + gasket + port map)
            is_pi = len(mounts) == 4  # Pi-like boards (58x49 pattern) -> apply port map
            pcuts = g.pi_port_cuts(mounts, size, base, standoff_h, size[2], clearance, wall) if is_pi else None
            case, lid = g.build_case_with_lid(
                size[0], size[1], size[2], clearance=clearance, wall=wall, base=base,
                standoff_h=standoff_h, mounts=mounts, screw="M2.5",
                ports=(not pcuts), port_cuts=pcuts)
            ex.to_stl(lid, GEN / f"{tok}_lid.stl")
            ex.to_step(lid, GEN / f"{tok}_lid.step")
            lid_url = f"gen/{tok}_lid.stl"
        else:
            case = g.build_wrap_case(size[0], size[1], size[2], clearance, wall, base, top_gap)
        ex.to_stl(case, GEN / f"{tok}_case.stl")
        ex.to_step(case, GEN / f"{tok}_case.step")
        tm = trimesh.load(str(GEN / f"{tok}_case.stl"))
        (GEN / f"{tok}_case.obj").write_text(tm.export(file_type="obj"))
        (GEN / f"{tok}_case.3mf").write_bytes(tm.export(file_type="3mf"))

        findings = []
        if mounts:
            dxs = [m2[0] for m2 in mounts]; dys = [m2[1] for m2 in mounts]
            span = f"{max(dxs)-min(dxs):.0f}×{max(dys)-min(dys):.0f}mm"
            findings.append(v.Finding("A1", "SOFT", True,
                f"보드 나사구멍 {len(mounts)}개 감지 → 기둥 정렬 / {len(mounts)} board holes detected",
                standard=f"{span} 패턴"))
        findings += [v.m_min_wall(wall, label="케이스 벽 / wall"), v.m_manifold(case)]
        return {
            "ref_url": f"gen/{tok}_ref.stl",
            "case_url": f"gen/{tok}_case.stl",
            "lid_url": lid_url,
            "sealed": bool(mounts),
            "size": [round(x, 1) for x in size],
            "clearance": clearance,
            "mounts": len(mounts),
            "findings": [_finding(x) for x in findings],
            "passed": all(f.ok for f in findings if f.severity == "HARD"),
            "downloads": {"STL": f"gen/{tok}_case.stl", "3MF": f"gen/{tok}_case.3mf",
                          "STEP": f"gen/{tok}_case.step", "OBJ": f"gen/{tok}_case.obj"},
        }
    except Exception as e:
        return {"error": _safe_err(e)}


@app.post("/api/split_upload")
async def split_upload(model: UploadFile = File(...),
                       bx: float = Form(256.0), by: float = Form(256.0), bz: float = Form(256.0),
                       target_max: float = Form(0.0), method: str = Form("smart"),
                       dowels: bool = Form(True)):
    """Split a large imported mesh (STL/OBJ/3MF/PLY) to fit the build volume, plus alignment pins and verification.

    method="smart" (default: detach joints and protrusions first, then size-split) / "chopper" (fewest pieces) / "grid" (axis grid).
    """
    try:
        import trimesh
        from ..printing.mesh_split import grid_split, verify
        from ..printing.chopper import partition, smart_partition
        ext = _ext(model.filename, _MESH_EXT)
        data = await _read_limited(model)
        tok = uuid.uuid4().hex[:8]
        raw = GEN / f"{tok}_in.{ext}"
        raw.write_bytes(data)
        m = trimesh.load(str(raw), force="mesh")
        build = (bx, by, bz)
        tm = (target_max or None)
        # smart = detach joints/protrusions first (natural seams) / chopper = fewest pieces / grid = axis-aligned grid
        if method == "grid":
            r = grid_split(m, build=build, target_max=tm, dowels=dowels)
        elif method == "chopper":
            r = partition(m, build=build, target_max=tm, dowels=dowels)
        else:
            r = smart_partition(m, build=build, target_max=tm, dowels=dowels)
        v = verify(r, build=build)

        urls = []
        for i, p in enumerate(r["pieces"]):
            p.export(str(GEN / f"{tok}_p{i}.stl"))      # write trimesh meshes directly
            urls.append(f"gen/{tok}_p{i}.stl")
        pin_url = None
        if r["pins"]:
            allpins = trimesh.util.concatenate(r["pins"])
            allpins.export(str(GEN / f"{tok}_pins.stl"))
            pin_url = f"gen/{tok}_pins.stl"
        zip_url = None                                       # ZIP with all piece files at once
        if len(urls) > 1:
            import zipfile
            zp = GEN / f"{tok}_pieces.zip"
            with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
                for i in range(len(urls)):
                    z.write(GEN / f"{tok}_p{i}.stl", f"piece_{i + 1}.stl")
                if pin_url:
                    z.write(GEN / f"{tok}_pins.stl", "pins.stl")
                n_pins = int(v.get("pins") or 0)
                note = [f"RealCAD 조각 {len(urls)}개 / {len(urls)} pieces, 판 크기 / bed {bx:g} x {by:g} x {bz:g} mm", ""]
                for i, pc in enumerate(v.get("pieces") or []):
                    sz = pc.get("size") if isinstance(pc, dict) else None
                    note.append(f"piece_{i + 1}.stl" + (f"  {' x '.join(f'{s:g}' for s in sz)} mm" if sz else ""))
                note += ["", "조립 / How to assemble:",
                         f"1. 조각을 각각 뽑아요 (자른 면이 판에 닿게 놓으면 서포트가 적어요). Print each piece, cut face down for fewer supports.",
                         f"2. pins.stl 의 맞춤 핀 {n_pins}개를 한쪽 구멍에 끼우고 맞은편 조각을 눌러 맞춰요. Push the {n_pins} pin{'s' if n_pins != 1 else ''} into one side, then press the other piece on.",
                         "3. 빡빡하면 핀을 사포로 살짝, 헐거우면 순간접착제 한 방울. Sand the pins if tight, a drop of glue if loose."]
                z.writestr("조립방법_assembly.txt", "\n".join(note))
            zip_url = f"gen/{tok}_pieces.zip"
        return {
            "zip_url": zip_url,
            "fits": r["fits"], "method": method, "n": r.get("n"), "cuts": r.get("cuts", []),
            "size": [round(x, 1) for x in r["size"]],
            "build": list(build), "n_pieces": v["n_pieces"], "all_fit": v["all_fit"],
            "pins": v["pins"], "volume_orig_cm3": v["volume_orig_cm3"],
            "volume_pieces_cm3": v["volume_pieces_cm3"], "volume_err_pct": v["volume_err_pct"],
            "pieces": v["pieces"], "piece_urls": urls, "pins_url": pin_url,
        }
    except Exception as e:
        return {"error": _safe_err(e)}


class DfamReq(BaseModel):
    url: str                      # current part file under gen/ (STL or STEP)


@app.post("/api/dfam")
def dfam_ep(req: DfamReq):
    """Measured printability of the part on screen: thinnest wall + orientation with the least support (verify/dfam.py)."""
    try:
        name = Path(str(req.url)).name                      # reject paths outside gen/
        p = (GEN / name).resolve()
        if p.parent != GEN.resolve() or not p.exists() or p.suffix.lower() not in (".stl", ".step", ".stp"):
            return {"error": "부품 파일을 찾지 못했어요"}
        from ..verify import dfam as _dfam
        if p.suffix.lower() == ".stl":
            import trimesh
            m = trimesh.load(str(p), force="mesh")
            return {"wall": _dfam._wall_from_mesh(m), "orientation": _dfam._orient_from_mesh(m)}
        from build123d import import_step
        return _dfam.measure(import_step(str(p)))
    except Exception as e:
        return {"error": _safe_err(e)}


class DrawingReq(BaseModel):
    url: str                      # current part STEP under gen/


@app.post("/api/drawing")
def drawing_ep(req: DrawingReq):
    """Build a three-view shop drawing PDF of the current part on the spot (export/views.py). Needs STEP (B-rep) to draw hidden lines."""
    try:
        name = Path(str(req.url)).name
        p = (GEN / name).resolve()
        if p.parent != GEN.resolve() or not p.exists() or p.suffix.lower() not in (".step", ".stp"):
            return {"error": "도면은 STEP 이 있는 부품에서만 만들 수 있어요"}
        from build123d import import_step
        from ..export.views import write_views_pdf
        out = GEN / (p.stem + "_drawing.pdf")
        if not out.exists():
            if not write_views_pdf(import_step(str(p)), out, title="RealCAD part", part_number=p.stem[:8].upper()):
                return {"error": "도면을 그리지 못했어요"}
        return {"pdf_url": f"gen/{out.name}"}
    except Exception as e:
        return {"error": _safe_err(e)}


# Mount the static frontend (index.html etc.) at /. Must come after the API routes
app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")
