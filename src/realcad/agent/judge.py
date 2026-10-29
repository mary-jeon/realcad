"""판정자 — 검증 실패를 보고 계약의 '파라미터'를 고친다(그림 재생성 아님). Meta 호출."""
from __future__ import annotations
import json
from .meta_client import chat
from .planner import _extract_json
from ..contract.schema import DesignContract

SYSTEM = """You fix mechanical design contracts for 3D-printed parts.
You are given the current DESIGN CONTRACT (JSON) and a list of HARD verification FAILURES
measured on the CAD kernel. Return a CORRECTED contract JSON (same schema) that resolves
every failure, keeping the design intent (same plate size and wall unless a change is required).
Prefer moving hole centers and adjusting positions over resizing. Units mm; plate centered at origin.
Rules: hole centers >= 1.5x bolt nominal dia from any plate edge; bolt heads clear of the wall
(1/4-20 hex head ~12.4mm across corners). H2 failure → remove "hole_dia" (use the standard clearance hole) or set it
to the required value. H3 failure (tapped engagement) → increase plate thickness to the required value, or set
"hole_type":"through". F0 (unsupported fastener) → change "fastener" to the suggested supported one. Output JSON only."""


def fix(contract_dict: dict, failures: list) -> tuple[DesignContract, dict, str]:
    lines = []
    for f in failures:
        lines.append(f"{f.code}: {f.message}; actual {f.actual}, required {f.required}; "
                     f"fix hint {f.suggestion}")
    user = ("Current contract:\n" + json.dumps(contract_dict)
            + "\n\nHARD failures:\n" + "\n".join(lines)
            + "\n\nReturn the corrected contract JSON only.")
    content, usage = chat(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        json_mode=True, temperature=0.0, max_tokens=8000,
    )
    return DesignContract.from_dict(_extract_json(content)), usage, content
