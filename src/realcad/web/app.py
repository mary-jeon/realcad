"""RealCAD 웹 백엔드 (FastAPI). 프롬프트 → 메타 설계 → 검증·수정 루프 → STEP/STL.

실행: PYTHONPATH=src .venv/bin/python -m uvicorn realcad.web.app:app --port 8750
"""
from __future__ import annotations
import uuid
from pathlib import Path

import base64
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..agent.planner import plan, plan_photo
from ..agent.clarify import clarify, augment
from ..agent.loop import run
from ..contract.schema import DesignContract
from ..printing.split import plan_split
from ..retrieval.library import search_models, generate_3d, generation_status
from ..fasteners.standards import get
from ..geometry import builder as g
from ..export import exporters as ex

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "web"
GEN = WEB / "gen"
GEN.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="RealCAD")


class ClarifyReq(BaseModel):
    prompt: str


class DesignReq(BaseModel):
    prompt: str
    answers: dict | None = None


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
        return {"error": str(e)}


def _finding(f) -> dict:
    return {"code": f.code, "severity": f.severity, "ok": f.ok,
            "message": f.message, "actual": f.actual, "required": f.required,
            "standard": f.standard, "suggestion": f.suggestion}


@app.post("/api/design")
def design(req: DesignReq):
    try:
        return _design(req)
    except Exception as e:
        return {"error": str(e)}


def _design(req: DesignReq):
    contract, _usage, _raw = plan(augment(req.prompt, req.answers))
    if contract.kind == "retrieve":
        # 파라메트릭 생성 불가 → 외부 라이브러리 리트리벌로 안내(박스로 억지 변환 금지).
        r = contract.retrieve
        return {"kind": "retrieve", "query": r.query, "note": r.note,
                "hint": "파라메트릭 생성 불가 — 자유곡면은 /api/retrieve 로 외부 모델을 검색하세요."}
    return _respond(run(contract, max_iters=3))


def _respond(r):
    c, part = r["contract"], r["part"]

    bolts = None
    fastener_name = "-"
    hole_dia = None
    if c.kind == "plate":
        f = get(c.fastener)
        fastener_name = f.name
        hole_dia = round(f.clearance(c.fit), 2)
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
    if bolts is not None:
        ex.to_stl(bolts, GEN / f"{tok}_bolts.stl")
        bolts_url = f"gen/{tok}_bolts.stl"

    return {
        "passed": r["summary"]["passed"],
        "iters": r["iters"],
        "fixed": r["fixed"],
        "kind": c.kind,
        "fastener": fastener_name,
        "hole_dia": hole_dia,
        "findings": [_finding(x) for x in r["findings"]],
        "contract": c.to_dict(),
        "part_url": f"gen/{tok}_part.stl",
        "bolts_url": bolts_url,
        "downloads": {
            "STL": f"gen/{tok}_part.stl",
            "3MF": f"gen/{tok}.3mf",
            "STEP": f"gen/{tok}.step",
            "OBJ": f"gen/{tok}.obj",
        },
    }


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
        return {"error": str(e)}


class Generate3DReq(BaseModel):
    prompt: str
    art_style: str = "realistic"


@app.post("/api/generate3d")
def generate3d_ep(req: Generate3DReq):
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
        return {"error": str(e)}


@app.get("/api/generate3d/status")
def generate3d_status_ep(task_id: str):
    """텍스트→3D 생성 작업 상태·결과(메시 URL) 조회."""
    try:
        return generation_status(task_id)
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/design_photo")
async def design_photo(image: UploadFile = File(...), note: str = Form("")):
    try:
        data = await image.read()
        mime = image.content_type or "image/jpeg"
        url = f"data:{mime};base64," + base64.b64encode(data).decode()
        contract, _u, _r = plan_photo(url, note)
        return _respond(run(contract, max_iters=3))
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/wrap")
async def wrap_ep(model: UploadFile = File(...), clearance: float = Form(2.0),
                  wall: float = Form(2.0), base: float = Form(2.0), top_gap: float = Form(5.0)):
    """외부참조(STEP/STL 등)를 받아 치수를 재고 그 주변에 케이스를 만든다(어셈블리)."""
    try:
        import trimesh
        from ..verify import checks as v
        data = await model.read()
        name = (model.filename or "ref").lower()
        ext = name.rsplit(".", 1)[-1] if "." in name else "stl"
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
        return {"error": str(e)}


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
        data = await model.read()
        name = (model.filename or "ref").lower()
        ext = name.rsplit(".", 1)[-1] if "." in name else "stl"
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
        return {"error": str(e)}


# 정적 프론트(index.html 등)를 / 에 마운트 — API 라우트 뒤에 둬야 함
app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")
