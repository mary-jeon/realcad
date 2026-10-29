"""대화형 편집 — 이미 만든 설계를 후속 지시로 '수정'한다(전체 재생성 아님).

Phase 0 (프롬프트캐드 로드맵). 두 경로 모두 지원:
  - 파라메트릭 경로: 현재 DesignContract(JSON)를 받아 바뀐 필드만 고친 새 계약을 낸다.
    (예: "텀블러 만들어줘" → "더 크게, 뚜껑 빼줘")
  - 코드 경로(AnyCAD): 현재 build123d 코드를 받아 최소 수정한 새 코드를 낸다.
    (예: "리모컨 만들어줘" → "버튼 5개 추가해줘")

핵심 원칙(연구 §7.1-3): LLM이 밑바닥부터 다시 그리지 않고 **현재 상태를 시드로** 받아
필요한 부분만 바꾸게 한다. 바뀐 것은 diff 로 뽑아 사용자에게 보고한다.
"""
from __future__ import annotations
import json

from .meta_client import chat
from . import codegen, sandbox
from ..contract.schema import DesignContract
from ..agent.planner import SYSTEM as PLAN_SYSTEM, _extract_json


# ──────────────────────────── 파라메트릭 계약 편집 ────────────────────────────

_CONTRACT_EDIT = """You are editing an EXISTING design, not creating a new one.

Here is the CURRENT design contract (JSON):
{contract}

The user now asks to change it:
"{instruction}"

Apply ONLY that change. Keep every field the user did not ask to change EXACTLY as it is.
Keep the same "kind" unless the requested change is impossible within it and clearly needs
another kind. Output the COMPLETE updated contract JSON (same schema as above), nothing else."""


def edit_contract(prior: dict, instruction: str) -> tuple[DesignContract, dict, str]:
    """현재 계약(dict) + 수정 지시 → 새 DesignContract. 바꾸라는 것만 바꾸게 유도."""
    content, usage = chat(
        [{"role": "system", "content": PLAN_SYSTEM},
         {"role": "user", "content": _CONTRACT_EDIT.format(
             contract=json.dumps(prior, ensure_ascii=False), instruction=instruction)}],
        json_mode=True, temperature=0.0, max_tokens=8000,
    )
    return DesignContract.from_dict(_extract_json(content)), usage, content


def _flatten(d: dict) -> dict:
    """계약 dict → {필드경로: 값}. kind 하위 1단계까지 펼친다(비교·diff용)."""
    out = {"kind": d.get("kind")}
    for k, v in d.items():
        if k == "kind":
            continue
        if isinstance(v, dict):
            for kk, vv in v.items():
                out[f"{k}.{kk}"] = vv
        elif isinstance(v, list):
            out[k] = f"[{len(v)}]"          # 리스트는 개수로(구멍 개수 등)
        else:
            out[k] = v
    return out


def diff_contract(old: dict, new: dict) -> list[dict]:
    """두 계약의 바뀐 필드만 '사람이 읽는' 목록으로. [{field, from, to}]"""
    fo, fn = _flatten(old), _flatten(new)
    changes = []
    for key in sorted(set(fo) | set(fn)):
        a, b = fo.get(key), fn.get(key)
        if a != b:
            changes.append({"field": key, "from": a, "to": b})
    return changes


# ──────────────────────────── 코드(AnyCAD) 편집 ────────────────────────────

_CODE_EDIT = r"""You are EDITING existing, working build123d code — not writing a new part.

--- current code (it runs and produces `part`) ---
{code}
--- end current code ---

The user now asks to change it:
"{instruction}"

Apply ONLY that change, as a minimal edit. Keep everything the user did not mention IDENTICAL
(same overall shape, same dimensions, same variable names where possible). Still obey every HARD
RULE above (assign to `part`, millimeters, FDM-printable, build123d + math only, watertight).
Return the COMPLETE updated code, code only — no fences, no prose."""


def edit_code(prior_code: str, instruction: str) -> tuple[str, dict]:
    """현재 build123d 코드 + 수정 지시 → 최소 수정한 새 코드."""
    content, usage = chat(
        [{"role": "system", "content": codegen.SYSTEM},
         {"role": "user", "content": _CODE_EDIT.format(
             code=prior_code, instruction=instruction)}],
        json_mode=False, temperature=0.0, max_tokens=12000,
    )
    return codegen._strip(content), usage


def design_edit_code(prior_code: str, instruction: str, stl_path, step_path,
                     max_iters: int = 3) -> dict:
    """코드 편집 + 격리실행 + 자동수정 루프. design_code 와 같은 반환 모양.

    it0: 현재 코드를 시드로 수정. 실패하면 codegen 의 repair(에러 되먹임)로 고친다.
    """
    code = edit_code(prior_code, instruction)[0]
    last_code = code
    error = None
    for it in range(max_iters + 1):
        if it > 0:          # 재시도는 에러 되먹임 수선
            code, _u = codegen.generate_code(instruction, last_code, error)
            last_code = code
        try:
            info = sandbox.execute_to_files(code, stl_path, step_path)
            return {"ok": True, "code": code, "info": info,
                    "findings": codegen._findings(info), "iters": it, "fixed": it > 0}
        except sandbox.SandboxError as e:
            error = str(e)
            if it == max_iters:
                return {"ok": False, "error": error, "code": code,
                        "iters": it, "findings": []}
    return {"ok": False, "error": error or "unknown", "code": code or "",
            "iters": max_iters, "findings": []}
