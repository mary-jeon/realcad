"""RealCAD MCP server (stdio, standard library only).

Lets MCP clients call RealCAD as a tool. The design itself is still done by the web backend (/api/*)
with the Meta model; this file only wraps that API.

Register with an MCP client, for example:
  claude mcp add realcad -- /path/to/realcad/.venv/bin/python /path/to/realcad/src/realcad/mcp_server.py
Environment variables:
  REALCAD_URL    web backend address (default http://127.0.0.1:8750)
  REALCAD_TOKEN  same value if the backend requires a token
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("REALCAD_URL", "http://127.0.0.1:8750").rstrip("/")
TOKEN = os.environ.get("REALCAD_TOKEN", "").strip()
WEB = Path(__file__).resolve().parents[2] / "web"
PROTOCOL = "2025-06-18"

_SETTINGS = {
    "type": "object",
    "description": "3D 프린팅 조건(선택). material: pla|petg|abs|tpu|steel|aluminum, nozzle mm, hole_comp mm, build [x,y,z] mm, iters 자동수정 횟수",
    "properties": {
        "material": {"type": "string"},
        "nozzle": {"type": "number"},
        "hole_comp": {"type": "number"},
        "build": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
        "iters": {"type": "integer"},
    },
}

_PARTS = {
    "type": "array", "minItems": 2, "maxItems": 12,
    "description": "조립 순서대로. 첫 부품이 고정. 각 부품은 session(앞서 만든 부품) 또는 file(돌려받은 STEP 경로) 중 하나",
    "items": {"type": "object", "required": ["name"], "properties": {
        "name": {"type": "string"}, "session": {"type": "string"}, "file": {"type": "string"},
        "material": {"type": "string"}, "spec": {"type": "string"}, "qty": {"type": "integer"}, "fixed": {"type": "boolean"}}},
}

TOOLS = [
    {
        "name": "design_part",
        "description": "자연어로 기계 부품을 설계한다(브래킷, 케이스, 판, 볼트 구멍, 조립 프리셋 등). Meta 모델이 설계 계약을 만들고 OCC 커널이 간섭, 공차, 연단거리를 검사한 뒤 STEP/STL 경로와 수정용 session 을 돌려준다.",
        "inputSchema": {"type": "object", "required": ["prompt"], "properties": {
            "prompt": {"type": "string", "description": "만들 부품 설명(한국어/영어, mm 단위 권장)"},
            "settings": _SETTINGS}},
    },
    {
        "name": "design_any",
        "description": "기본형으로 안 되는 임의 형상을 Meta 모델이 build123d 코드로 직접 짜서 격리 실행으로 만든다(실패 시 커널 오류로 자동 수정). 시판 제품용 액세서리면 spec_text 에 lookup_spec 결과를 넣는다.",
        "inputSchema": {"type": "object", "required": ["prompt"], "properties": {
            "prompt": {"type": "string"},
            "spec_text": {"type": "string", "description": "lookup_spec 이 돌려준 spec_text(선택)"},
            "answers": {"type": "object", "description": "lookup_spec 질문에 대한 실측 답 {질문id: 값}(선택)"},
            "settings": _SETTINGS}},
    },
    {
        "name": "edit_part",
        "description": "앞서 만든 부품(session)을 후속 지시로 최소 수정한다. 예: '구멍 0.3 크게', '두께 3mm', '바닥 두 면을 옆 벽 높이까지 올려'.",
        "inputSchema": {"type": "object", "required": ["session", "instruction"], "properties": {
            "session": {"type": "string"},
            "instruction": {"type": "string"},
            "dry_run": {"type": "boolean", "description": "true 면 바꾼 결과를 만들어 보여 주기만 하고 부품은 그대로 둔다. 돌려받은 plan_id 를 apply_plan 에 보내야 적용된다."},
            "settings": _SETTINGS}},
    },
    {
        "name": "apply_plan",
        "description": "edit_part 를 dry_run 으로 돌려 받은 plan_id 를 그대로 적용한다. 미리보기에서 보여 준 바로 그 변경만 들어가고, 그 사이 부품이 바뀌었으면 거절한다.",
        "inputSchema": {"type": "object", "required": ["plan_id"], "properties": {"plan_id": {"type": "string"}}},
    },
    {
        "name": "part_features",
        "description": "부품마다 잰 평면(P*), 구멍(H*), 원통 돌기(B*)의 번호, 방향, 중심, 지름을 돌려준다. assemble_parts 의 메이트에 이 번호를 쓴다.",
        "inputSchema": {"type": "object", "required": ["parts"], "properties": {"parts": _PARTS}},
    },
    {
        "name": "assemble_parts",
        "description": "앞서 만든 부품들을 메이트로 조립한다(일치 coincident, 거리 distance, 동심 concentric). mates 를 직접 주거나, instruction 에 말로 쓰면 Meta 모델이 잰 면과 구멍 중에서 메이트를 고른다. 첫 부품(또는 fixed)은 고정. 놓은 뒤 메이트 오차, 구속 상태, 부품 간섭, 재질과 수량을 검사하고 STEP, 부품별 STL, 질량 BOM 을 돌려준다.",
        "inputSchema": {"type": "object", "required": ["parts"], "properties": {
            "parts": _PARTS,
            "mates": {"type": "array", "description": "예: {\"type\":\"concentric\",\"a\":\"case:H1\",\"b\":\"pi:H1\"}, {\"type\":\"coincident\",\"a\":\"case:P31\",\"b\":\"pi:P1\"}, {\"type\":\"distance\",...,\"value\":2}. 면은 {\"part\":\"case\",\"face\":\"+Z\",\"near\":[x,y,z]}, 구멍은 {\"part\":\"pi\",\"hole\":[x,y],\"dia\":2.7} 로도 고를 수 있다.",
                      "items": {"type": "object"}},
            "instruction": {"type": "string", "description": "mates 대신 말로: 예 '파이를 케이스 기둥 위에 나사 구멍 맞춰 올려'"}}},
    },
    {
        "name": "undo_part",
        "description": "session 의 직전 성공본으로 되돌린다.",
        "inputSchema": {"type": "object", "required": ["session"], "properties": {"session": {"type": "string"}}},
    },
    {
        "name": "lookup_spec",
        "description": "문장에 나온 시판 제품(맥미니, 스위치 등)의 외형 치수를 공식 규격표, 그다음 Meta 기억으로 찾아 확실/추정/모름과 상대편 치수 질문을 돌려준다.",
        "inputSchema": {"type": "object", "required": ["prompt"], "properties": {"prompt": {"type": "string"}}},
    },
]

_ROUTES = {"design_part": "/api/design", "design_any": "/api/design_code", "edit_part": "/api/edit",
           "undo_part": "/api/undo", "lookup_spec": "/api/spec_lookup", "apply_plan": "/api/apply_plan",
           "part_features": "/api/part_features", "assemble_parts": "/api/assemble"}


def _part_refs(parts):
    """MCP part refs -> backend refs: an absolute file path returned earlier becomes gen/<name>."""
    out = []
    for p in parts or []:
        q = {k: v for k, v in dict(p).items() if v is not None and k != "file"}
        f = p.get("file") if isinstance(p, dict) else None
        if f and not q.get("session"):
            fp = Path(f)
            if fp.is_absolute():
                try:
                    q["url"] = "gen/" + fp.resolve().relative_to((WEB / "gen").resolve()).as_posix()
                except ValueError:
                    raise ValueError(f"{f}: RealCAD 가 만든 파일(web/gen 안)만 조립할 수 있어요")
            else:
                q["url"] = f if f.startswith("gen/") else "gen/" + f
        out.append(q)
    return out


def _post(path: str, body: dict, timeout: float = 600) -> dict:
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"X-RealCAD-Token": TOKEN} if TOKEN else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.URLError as e:
        return {"error": f"RealCAD 백엔드({BASE})에 연결 못 함: {e}. 서버를 먼저 켜 주세요."}


def _abs(rel: str | None) -> str | None:
    return str((WEB / rel).resolve()) if rel and not rel.startswith("http") else rel


def _summarize(d: dict) -> dict:
    """Keep only what people and models need from the response (code body and large arrays are trimmed)."""
    if not isinstance(d, dict):
        return {"raw": d}
    keep = ("error", "passed", "kind", "mode", "session", "iters", "fixed", "stats", "note", "hint",
            "products", "questions", "counterpart", "spec_text", "expired", "organic", "files_ok",
            "dry_run", "plan_id", "change", "next", "instruction", "plan_applied", "why", "measured", "total_mass_g", "mass_unknown", "bom_flat", "downloads_failed")
    out = {k: d[k] for k in keep if k in d}
    if d.get("downloads"):
        out["files"] = {k: _abs(v) for k, v in d["downloads"].items()}
    for key in ("checks", "findings"):
        if isinstance(d.get(key), list):
            items = d[key]
            out[key] = [{k: f.get(k) for k in ("id", "code", "name", "severity", "ok", "msg", "message", "detail",
                                                 "actual", "required", "suggestion") if f.get(k) not in (None, "", {})}
                        if isinstance(f, dict) else f for f in items[:30]]
            if len(items) > 30:
                out[key + "_more"] = len(items) - 30
    if isinstance(d.get("parts"), list):
        out["parts"] = [{k: (_abs(p.get(k)) if k == "url" else p.get(k)) for k in ("no", "name", "qty", "material", "url", "dof")
                         if isinstance(p, dict) and k in p} for p in d["parts"][:40]]
    if isinstance(d.get("diff"), list):
        out["diff"] = d["diff"][:80]
    if d.get("preview_url"):
        out["preview_file"] = _abs(d["preview_url"])
    if d.get("code"):
        out["code_chars"] = len(d["code"])
    if out.get("session"):
        out["viewer"] = f"{BASE}/acad.html?load={d['downloads']['STL']}" if d.get("downloads", {}).get("STL") else None
    return out


def call_tool(name: str, args: dict) -> dict:
    if name not in _ROUTES:
        raise KeyError(name)
    body = {k: v for k, v in args.items() if v is not None}
    if "parts" in body:
        try:
            body["parts"] = _part_refs(body["parts"])
        except ValueError as e:
            return {"error": str(e)}
    d = _post(_ROUTES[name], body)
    if name == "part_features" and isinstance(d, dict) and "parts" in d:
        return d
    if isinstance(d, dict) and d.get("kind") == "concept":   # a figure: the reference sheet is drawn, build from it right away
        d = _post("/api/design_concept", {"token": d["token"], "prompt": d["prompt"], "settings": body.get("settings")})
    out = _summarize(d)
    if isinstance(d, dict) and d.get("concept"):
        out["reference_sheet"] = _abs(d["concept"])
    return out


def _reply(id_, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": id_}
    if error:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(msg: dict) -> None:
    method, id_ = msg.get("method"), msg.get("id")
    if id_ is None:                      # notifications (notifications/*) get no reply
        return
    if method == "initialize":
        _reply(id_, {"protocolVersion": (msg.get("params") or {}).get("protocolVersion", PROTOCOL),
                     "capabilities": {"tools": {}},
                     "serverInfo": {"name": "realcad", "version": "0.1.0"},
                     "instructions": "RealCAD: 자연어 → Meta Muse Spark 설계 → OCC 커널 검사 → STEP/STL. 결과의 files 경로와 session 을 쓰고, 고칠 때는 edit_part."})
    elif method == "ping":
        _reply(id_, {})
    elif method == "tools/list":
        _reply(id_, {"tools": TOOLS})
    elif method == "tools/call":
        p = msg.get("params") or {}
        try:
            res = call_tool(p.get("name", ""), p.get("arguments") or {})
            _reply(id_, {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, indent=1)}],
                         "isError": bool(res.get("error"))})
        except KeyError:
            _reply(id_, error={"code": -32602, "message": f"unknown tool: {p.get('name')}"})
        except Exception as e:           # tool failures are returned as results, not protocol errors
            _reply(id_, {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True})
    else:
        _reply(id_, error={"code": -32601, "message": f"method not found: {method}"})


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            handle(json.loads(line))
        except json.JSONDecodeError:
            _reply(None, error={"code": -32700, "message": "parse error"})


if __name__ == "__main__":
    main()
