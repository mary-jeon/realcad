"""RealCAD 웹 백엔드 (FastAPI). 프롬프트 → 메타 설계 → 검증·수정 루프 → STEP/STL.

실행: PYTHONPATH=src .venv/bin/python -m uvicorn realcad.web.app:app --port 8750
"""
from __future__ import annotations
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
from ..agent import editor
from ..contract.schema import DesignContract
from ..printing.split import plan_split
from ..retrieval.library import search_models, generate_3d, generation_status
from ..fasteners.standards import resolve as _resolve_fastener
from ..geometry import builder as g
from ..export import exporters as ex

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "web"
GEN = WEB / "gen"
GEN.mkdir(parents=True, exist_ok=True)


def _prune_gen(keep: int = 300) -> None:
    """생성물 폴더가 끝없이 커지지 않게 시작 시 최근 keep 개(토큰 묶음 기준)만 남긴다."""
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
# 공개 터널 등에 노출할 때: REALCAD_TOKEN 환경변수를 주면 모든 /api/* 요청에 X-RealCAD-Token 헤더(또는 ?token=)를 요구한다.
_TOKEN = _os.environ.get("REALCAD_TOKEN", "").strip()
app = FastAPI(title="RealCAD", docs_url=None, redoc_url=None, openapi_url=None)

MAX_UPLOAD = 60 * 1024 * 1024          # 업로드 60MB 상한
_MESH_EXT = {"stl", "obj", "3mf", "ply", "step", "stp"}
_IMG_MIME = {"image/jpeg", "image/png", "image/webp"}


def _safe_err(e: Exception) -> str:
    """예외 메시지에서 서버 절대경로를 지운다(클라이언트 노출 최소화)."""
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

# 대화형 편집용 세션 상태(프로세스 메모리). sid → {"mode":"code","code":str}
#                                           또는 {"mode":"param","contract":dict}
SESSIONS: dict[str, dict] = {}
_SESS_MAX = 200


def _new_sid() -> str:
    sid = uuid.uuid4().hex[:12]
    if len(SESSIONS) > _SESS_MAX:          # 오래된 것부터 버려 메모리 누수 방지
        for k in list(SESSIONS)[: len(SESSIONS) - _SESS_MAX]:
            SESSIONS.pop(k, None)
    return sid


class ClarifyReq(BaseModel):
    prompt: str


class PrintSettings(BaseModel):
    """왼쪽 사이드바(Printer → Filament → Process) 값. 검사 M1(노즐), H3(재료 k), P1(구멍 보정), 빌드볼륨에 들어간다."""
    material: str | None = None       # pla | petg | abs | tpu | steel | aluminum
    nozzle: float | None = None       # mm
    hole_comp: float | None = None    # mm
    build: list[float] | None = None  # [x, y, z] mm
    iters: int | None = None          # 자동 수정 최대 횟수(0=끄기)


def _apply_settings(c, st: "PrintSettings | None"):
    if not st:
        return c
    # 재료: 프롬프트가 금속을 명시했으면(기획자가 steel/aluminum 으로 적음) 사이드바 플라스틱 값으로 덮지 않는다
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
    """코드 경로는 계약이 없으니 프롬프트 끝에 제조 조건을 한 줄로 붙인다(모델이 벽두께·구멍에 반영)."""
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


@app.post("/api/clarify")
def clarify_ep(req: ClarifyReq):
    qs, _usage = clarify(req.prompt)
    return {"questions": qs}


class SplitReq(BaseModel):
    contract: dict
    build: list[float] = [220.0, 220.0, 250.0]


@app.post("/api/split")
def split_ep(req: SplitReq):
    try:
        c = DesignContract.from_dict(req.contract)
        part, _f, _d = g.build_from_contract(c)
        res = plan_split(part, tuple(req.build))
        tok = uuid.uuid4().hex[:8]
        urls = []
        for i, p in enumerate(res["pieces"]):
            ex.to_stl(p, GEN / f"{tok}_s{i}.stl")
            urls.append(f"gen/{tok}_s{i}.stl")
        return {"fits": res["fits"], "axis": res["axis"], "n": res["n"],
                "dowel": res["dowel"], "size": [round(x, 1) for x in res["size"]],
                "build": req.build, "pieces": urls}
    except Exception as e:
        return {"error": _safe_err(e)}


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
        # 유기형(자유곡면) → 외부 API 없이 로컬 코드생성으로 곡면 제작(loft/타원체/스윕/필렛).
        # 실패하면 그때만 리트리벌 안내. 박스로 억지 변환이 아니라 '유기형 기법'으로 생성.
        r = contract.retrieve
        tok = uuid.uuid4().hex[:8]
        stl_path = GEN / f"{tok}_part.stl"; step_path = GEN / f"{tok}.step"
        cr = codegen.design_code(req.prompt + _settings_note(getattr(req, "settings", None)), stl_path, step_path, max_iters=3)
        if cr["ok"]:
            out = _emit_code(tok, stl_path, step_path, cr, _new_sid())
            out["organic"] = True
            return out
        hint = ("자유곡면을 로컬로 못 만들었어요 — 외부 모델 검색(/api/retrieve)으로 받으세요." if not r.parts
                else f"{len(r.parts)}개 부품으로 분해했어요. 각 부품을 /api/retrieve 또는 /api/generate3d 로.")
        return {"kind": "retrieve", "query": r.query, "note": r.note,
                "parts": r.parts, "hint": hint}
    _it = getattr(req, "settings", None) and req.settings.iters
    return _respond(run(contract, max_iters=(3 if _it is None else max(0, min(int(_it), 5)))))


def _mesh_stats(tm) -> dict:
    """화면 상단 요약용: 치수(mm)·부피(cm³)·표면적(cm²)·PLA 무게 추정(100% 채움, 1.24 g/cm³)·슬라이서 전 대략치.
    슬라이싱 없이 계산 가능한 값만 준다(출력 시간은 슬라이서가 정한다)."""
    try:
        import numpy as _np
        ext = tm.bounding_box.extents
        vol = float(abs(tm.volume)) / 1000.0            # mm³ → cm³
        area = float(tm.area) / 100.0                   # mm² → cm²
        return {
            "bbox_mm": [round(float(x), 1) for x in ext],
            "volume_cm3": round(vol, 2),
            "area_cm2": round(area, 1),
            "pla_g_solid": round(vol * 1.24, 1),        # 100% 채움
            "pla_g_20pct": round((min(area * 0.12, vol) + max(vol - area * 0.12, 0) * 0.2) * 1.24, 1),  # 벽 1.2mm 두 겹 가정 + 내부 20%
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
        grip = c.plate.thickness + 5          # 판을 관통해 살짝만 나오게(렌더 깔끔)
        for h in c.holes:
            b = g.place(g.hex_bolt_solid(f, grip), h.x, h.y)
            bolts = b if bolts is None else bolts + b

    tok = uuid.uuid4().hex[:8]
    stl_path = GEN / f"{tok}_part.stl"
    ex.to_stl(part, stl_path)
    ex.to_step(part, GEN / f"{tok}.step")
    # 내보내기 포맷: STL(엔진), 3MF·OBJ(trimesh 변환), STEP
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
    _z = (-c.plate.thickness / 2 if c.kind == "plate" else None)
    if write_drawing(part, GEN / f"{tok}.dxf", z=_z, contract=c, fastener=(f if c.kind == "plate" else None), title=f"RealCAD {c.kind}") \
            or ex.to_dxf(part, GEN / f"{tok}.dxf", z=_z):
        dxf_url = f"gen/{tok}.dxf"
    if c.kind == "plate":
        from ..export.bom import make_bom, write_bom_csv
        _eng = next((x.actual for x in r["findings"] if x.code == "H3"), None)
        bom = make_bom(c, f, r["hole_dia"] if r.get("hole_dia") else hole_dia or 0.0, _eng)
        write_bom_csv(bom, GEN / f"{tok}_bom.csv")

    # 대화형 편집 세션에 현재 계약 저장(후속 "더 크게/구멍 추가" 수정의 시드)
    sid = sid or _new_sid()
    SESSIONS[sid] = {"mode": "param", "contract": c.to_dict()}

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
        "stats": _mesh_stats(tm),
        "downloads": {
            "STL": f"gen/{tok}_part.stl",
            "3MF": f"gen/{tok}.3mf",
            "STEP": f"gen/{tok}.step",
            "OBJ": f"gen/{tok}.obj",
            **({"BOM": f"gen/{tok}_bom.csv"} if bom else {}),
            **({"DXF": dxf_url} if dxf_url else {}),
        },
    }


class DesignCodeReq(BaseModel):
    prompt: str
    answers: dict | None = None
    settings: PrintSettings | None = None


def _emit_code(tok: str, stl_path: Path, step_path: Path, r: dict, sid: str) -> dict:
    """코드생성/편집 성공 결과(r) → 웹 응답. STL/STEP 은 sandbox 가 이미 썼고 OBJ/3MF 변환."""
    ex._clean_degenerate(stl_path)              # 극점 퇴화면 정리(watertight)
    import trimesh
    tm = trimesh.load(str(stl_path))
    (GEN / f"{tok}.obj").write_text(tm.export(file_type="obj"))
    (GEN / f"{tok}.3mf").write_bytes(tm.export(file_type="3mf"))
    # 후속 편집 시드로 코드 보관 + 되돌리기용 히스토리 적립(직전 성공본을 쌓음, 최근 20개)
    _prev = SESSIONS.get(sid)
    _hist = (_prev.get("hist") if _prev else None) or []
    if _prev and _prev.get("mode") == "code" and _prev.get("code") and not r.get("_norecord"):
        _hist = (_hist + [_prev["code"]])[-20:]
    SESSIONS[sid] = {"mode": "code", "code": r["code"], "hist": _hist}
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
    return {
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
        "session": sid,
        "part_url": f"gen/{tok}_part.stl",
        "bolts_url": None,
        "downloads": {
            "STL": f"gen/{tok}_part.stl",
            "3MF": f"gen/{tok}.3mf",
            "STEP": f"gen/{tok}.step",
            "OBJ": f"gen/{tok}.obj",
            **({"DXF": _dxf} if _dxf else {}),
        },
    }


@app.post("/api/design_code")
def design_code_ep(req: DesignCodeReq):
    """코드생성 CAD — AI가 build123d 코드를 직접 짜서 임의 기계부품 생성(격리 실행·자동수정).

    기본형 메뉴로 못 하는 "뭐든 다" 경로. 유기적 조각 형상은 여전히 불가(retrieve/Meshy).
    """
    try:
        prompt = augment(req.prompt, req.answers) + _settings_note(getattr(req, "settings", None))
        tok = uuid.uuid4().hex[:8]
        stl_path = GEN / f"{tok}_part.stl"
        step_path = GEN / f"{tok}.step"
        r = codegen.design_code(prompt, stl_path, step_path, max_iters=3)
        if not r["ok"]:
            return {"error": r["error"], "code": r.get("code", ""),
                    "iters": r.get("iters", 0), "mode": "code"}
        return _emit_code(tok, stl_path, step_path, r, _new_sid())
    except Exception as e:
        return {"error": _safe_err(e), "mode": "code"}


class EditReq(BaseModel):
    session: str
    instruction: str
    settings: PrintSettings | None = None


@app.post("/api/edit")
def edit_ep(req: EditReq):
    """대화형 편집 — 세션의 현재 설계(코드 또는 계약)를 후속 지시로 최소 수정(전체 재생성 아님).

    예) 코드: "리모컨 만들어줘"(design_code) → "버튼 5개 추가해줘"(edit)
        계약: "텀블러 만들어줘"(design) → "더 크게, 두께 3mm로"(edit)
    """
    inst = (req.instruction or "").strip()
    if not inst:
        return {"error": "수정 내용을 입력하세요."}
    st = SESSIONS.get(req.session)
    if not st:
        return {"error": "세션이 만료됐어요. 먼저 설계를 새로 생성한 뒤 수정하세요.",
                "expired": True}
    try:
        if st["mode"] == "code":
            tok = uuid.uuid4().hex[:8]
            stl_path = GEN / f"{tok}_part.stl"
            step_path = GEN / f"{tok}.step"
            r = editor.design_edit_code(st["code"], inst + _settings_note(getattr(req, "settings", None)), stl_path, step_path, max_iters=3)
            if not r["ok"]:
                # 수정 실패 — 세션 코드는 직전 성공본 유지(되돌릴 수 있게)
                return {"error": r["error"], "code": r.get("code", ""),
                        "iters": r.get("iters", 0), "mode": "code",
                        "session": req.session, "edited": True}
            out = _emit_code(tok, stl_path, step_path, r, req.session)
            out["edited"] = True
            return out
        # 파라메트릭 계약 편집
        prior = st["contract"]
        new_c, _u, _raw = editor.edit_contract(prior, inst)
        _apply_settings(new_c, getattr(req, "settings", None))
        if new_c.kind == "retrieve":
            return {"kind": "retrieve", "query": new_c.retrieve.query,
                    "note": new_c.retrieve.note, "session": req.session, "edited": True,
                    "hint": "이 수정은 파라메트릭으로 표현 불가 — 자유곡면은 생성/리트리벌 경로예요."}
        out = _respond(run(new_c, max_iters=3), sid=req.session)
        out["edited"] = True
        out["diff"] = editor.diff_contract(prior, new_c.to_dict())
        return out
    except Exception as e:
        return {"error": _safe_err(e), "session": req.session}


class UndoReq(BaseModel):
    session: str


@app.post("/api/undo")
def undo_ep(req: UndoReq):
    """되돌리기 — 세션의 직전 버전(코드)으로 복원. '안 맞으면 고쳐'의 되감기.

    plain undo(브랜칭): 되돌린 뒤 다시 수정하면 이후 버전은 버려진다. 코드 모드 전용.
    """
    from ..agent import sandbox
    st = SESSIONS.get(req.session)
    if not st:
        return {"error": "세션이 만료됐어요. 먼저 설계를 새로 생성하세요.", "expired": True}
    if st.get("mode") != "code":
        return {"no_history": True, "msg": "이 설계는 되돌리기를 지원하지 않아요(코드 생성/수정만 가능)."}
    hist = list(st.get("hist") or [])
    if not hist:
        return {"no_history": True, "msg": "더 되돌릴 게 없어요 — 첫 버전이에요."}
    prev_code = hist.pop()                       # 직전 버전을 현재로
    try:
        tok = uuid.uuid4().hex[:8]
        stl_path = GEN / f"{tok}_part.stl"
        step_path = GEN / f"{tok}.step"
        info = sandbox.execute_to_files(prev_code, stl_path, step_path)
        r = {"code": prev_code, "info": info, "findings": codegen._findings(info),
             "iters": 0, "fixed": False, "_norecord": True}
        out = _emit_code(tok, stl_path, step_path, r, req.session)
        SESSIONS[req.session]["hist"] = hist     # 되돌린 버전은 히스토리에서 제거(한 칸 뒤로)
        out["edited"] = True
        out["undone"] = True
        out["remaining"] = len(hist)
        return out
    except Exception as e:
        return {"error": f"되돌리기 실패: {_safe_err(e)}", "session": req.session}


class RetrieveReq(BaseModel):
    prompt: str
    source: str = "thingiverse"
    limit: int = 5


@app.post("/api/retrieve")
def retrieve_ep(req: RetrieveReq):
    """자유곡면(마우스·신발 등) → 플래너가 kind='retrieve'로 판정하면 외부 3D 라이브러리 검색.

    파라메트릭 생성 가능(plate/container/...)하면 /api/design 을 쓰라는 힌트만 돌려준다.
    TODO(후속): 후보 선택 → download_url에서 STL 내려받기 → watertight 검증 → 빌드볼륨 분할.
    """
    try:
        contract, _usage, _raw = plan(req.prompt)
        if contract.kind != "retrieve":
            return {"kind": contract.kind,
                    "hint": "파라메트릭 생성 가능 — /api/design 사용",
                    "contract": contract.to_dict()}
        r = contract.retrieve
        candidates = search_models(r.query, source=req.source, limit=req.limit)
        return {"kind": "retrieve", "query": r.query, "note": r.note,
                "candidates": candidates}
    except Exception as e:
        return {"error": _safe_err(e)}


class Generate3DReq(BaseModel):
    prompt: str
    art_style: str = "realistic"


_EXTERNAL = _os.environ.get("REALCAD_ENABLE_EXTERNAL", "").strip() == "1"


@app.post("/api/generate3d")
def generate3d_ep(req: Generate3DReq):
    if not _EXTERNAL:   # 해커톤 제출 빌드: 런타임 AI 모델은 Meta 만. 외부 텍스트→3D(Meshy)는 옵트인
        return {"error": "외부 3D 생성 모델은 이 빌드에서 꺼져 있어요 (REALCAD_ENABLE_EXTERNAL=1 로 켤 수 있음). "
                         "RealCAD 의 런타임 AI 는 Meta Muse Spark 만 사용합니다."}
    return _generate3d(req)


def _generate3d(req: Generate3DReq):
    """자유곡면 '생성'(텍스트→3D, Meshy). 플래너가 kind='retrieve'(자유곡면)로 보면 생성 작업 제출.

    바로 메시가 나오지 않고 task_id를 돌려준다 → /api/generate3d/status 로 폴링.
    파라메트릭 생성 가능하면 /api/design 힌트만 돌려준다.
    """
    try:
        contract, _usage, _raw = plan(req.prompt)
        query = contract.retrieve.query if contract.kind == "retrieve" else req.prompt
        if contract.kind != "retrieve":
            # 파라메트릭으로 되는 건 굳이 생성 안 하고 안내(원하면 그래도 생성 가능)
            job = generate_3d(req.prompt, art_style=req.art_style)
            return {"kind": contract.kind,
                    "hint": "파라메트릭 생성 가능 — 더 정밀하려면 /api/design 사용",
                    "generation": job}
        return {"kind": "retrieve", "query": query, "note": contract.retrieve.note,
                "generation": generate_3d(query, art_style=req.art_style)}
    except Exception as e:
        return {"error": _safe_err(e)}


@app.get("/api/generate3d/status")
def generate3d_status_ep(task_id: str):
    """텍스트→3D 생성 작업 상태·결과(메시 URL) 조회."""
    try:
        return generation_status(task_id)
    except Exception as e:
        return {"error": _safe_err(e)}


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
        blob = (f"{r.query} {r.note}" if r else note).lower()
        # 단어 경계로만 — "mecha"가 "mechanical"에, "body"가 "nobody"에 걸리면 안 됨
        organic = bool(re.search(
            r"\b(figure|figurine|character|mech|mecha|gundam|robot|animal|person|people|human|"
            r"humanoid|body|torso|bust|statue|sculpture|creature|doll|mascot|anatomical|skull|"
            r"face|dragon|dog|cat|bird|fish|flower|tree)\b", blob))
        # 유기형(피규어·동물·사람) → 리트리벌/부품분해. 나머지는 전부 사진 코드생성
        # (고정 프리미티브 8종보다 코드생성이 훨씬 유능 — 키보드를 '통'으로 환원하는 오분류 방지).
        if contract.kind == "retrieve" and organic:
            hint = ("사진 속 물체가 자유곡면이라 파라메트릭/코드로 못 만들어 — 리트리벌/생성으로." if not r.parts
                    else f"사진 속 물체를 {len(r.parts)}개 부품으로 분해했어요. 각 부품을 리트리벌/생성으로 받으세요.")
            return {"kind": "retrieve", "query": r.query, "note": r.note, "parts": r.parts, "hint": hint}
        tok = uuid.uuid4().hex[:8]
        stl_path = GEN / f"{tok}_part.stl"; step_path = GEN / f"{tok}.step"
        cr = codegen.design_code_photo(url, note or (r.query if r else ""), stl_path, step_path, max_iters=3)
        if cr["ok"]:
            return _emit_code(tok, stl_path, step_path, cr, _new_sid())
        # 코드생성 실패 시: 플래너가 기본형을 골랐으면 그걸로, 아니면 리트리벌 안내
        if contract.kind != "retrieve":
            return _respond(run(contract, max_iters=3))
        return {"kind": "retrieve", "query": r.query, "note": r.note, "parts": r.parts,
                "hint": "사진 속 물체를 코드로 못 만들었어요 — 리트리벌/생성으로 받으세요."}
    except Exception as e:
        return {"error": _safe_err(e)}


@app.post("/api/wrap")
async def wrap_ep(model: UploadFile = File(...), clearance: float = Form(2.0),
                  wall: float = Form(2.0), base: float = Form(2.0), top_gap: float = Form(5.0)):
    """외부참조(STEP/STL 등)를 받아 치수를 재고 그 주변에 케이스를 만든다(어셈블리)."""
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
            # 보드를 기둥 위에 앉힌다
            export_stl(_Pos(-cx, -cy, base + standoff_h - b.min.Z) * part, str(ref_stl))
        else:
            m = trimesh.load(str(raw), force="mesh")
            bb = m.bounds
            size = tuple(float(x) for x in (bb[1] - bb[0]))
            ctr = (bb[0] + bb[1]) / 2
            m.apply_translation([-ctr[0], -ctr[1], base - bb[0][2]])
            m.export(str(ref_stl))

        lid_url = None
        if mounts:   # 보드 구멍 감지 → 밀폐형(바디+뚜껑+모서리나사+가스켓+포트맵)
            is_pi = len(mounts) == 4  # 파이류(58×49 패턴) → 포트맵 적용
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
    """임포트한 대형 메시(STL/OBJ/3MF/PLY)를 빌드볼륨에 맞춰 분할 + 정렬핀 + 검증.

    method="smart"(기본, 관절·돌출부 선분리 후 크기분할) / "chopper"(최소 조각) / "grid"(축격자).
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
        # smart=관절·돌출부 선분리(자연 솔기) / chopper=최소 조각 / grid=축정렬 격자
        if method == "grid":
            r = grid_split(m, build=build, target_max=tm, dowels=dowels)
        elif method == "chopper":
            r = partition(m, build=build, target_max=tm, dowels=dowels)
        else:
            r = smart_partition(m, build=build, target_max=tm, dowels=dowels)
        v = verify(r, build=build)

        urls = []
        for i, p in enumerate(r["pieces"]):
            p.export(str(GEN / f"{tok}_p{i}.stl"))      # trimesh 메시 직접 출력
            urls.append(f"gen/{tok}_p{i}.stl")
        pin_url = None
        if r["pins"]:
            allpins = trimesh.util.concatenate(r["pins"])
            allpins.export(str(GEN / f"{tok}_pins.stl"))
            pin_url = f"gen/{tok}_pins.stl"
        return {
            "fits": r["fits"], "method": method, "n": r.get("n"), "cuts": r.get("cuts", []),
            "size": [round(x, 1) for x in r["size"]],
            "build": list(build), "n_pieces": v["n_pieces"], "all_fit": v["all_fit"],
            "pins": v["pins"], "volume_orig_cm3": v["volume_orig_cm3"],
            "volume_pieces_cm3": v["volume_pieces_cm3"], "volume_err_pct": v["volume_err_pct"],
            "pieces": v["pieces"], "piece_urls": urls, "pins_url": pin_url,
        }
    except Exception as e:
        return {"error": _safe_err(e)}


# 정적 프론트(index.html 등)를 / 에 마운트 — API 라우트 뒤에 둬야 함
app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")
