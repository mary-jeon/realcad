"""Conversational editing: modify an existing design with a follow-up instruction (not a full regeneration).

Two paths:
  - Parametric: take the current DesignContract (JSON) and return a new contract with only the changed fields.
    (e.g. "make a tumbler" -> "make it bigger, remove the lid")
  - Code (AnyCAD): take the current build123d code and return minimally edited code.
    (e.g. "make a remote" -> "add 5 buttons")

Key idea: the LLM does not redraw from scratch; it gets the current state as a seed
and changes only what is needed. Changes are extracted as a diff and reported to the user.
"""
from __future__ import annotations
import json

from .meta_client import chat
from . import codegen, sandbox
from ..contract.schema import DesignContract
from ..agent.planner import SYSTEM as PLAN_SYSTEM, _extract_json


# ──────────────────────────── Parametric contract editing ────────────────────────────

_CONTRACT_EDIT = """You are editing an EXISTING design, not creating a new one.

Here is the CURRENT design contract (JSON):
{contract}

The user now asks to change it:
"{instruction}"

Apply ONLY that change. Keep every field the user did not ask to change EXACTLY as it is.
Keep the same "kind" unless the requested change is impossible within it and clearly needs
another kind. Output the COMPLETE updated contract JSON (same schema as above), nothing else."""


def edit_contract(prior: dict, instruction: str) -> tuple[DesignContract, dict, str]:
    """Current contract (dict) + edit instruction -> new DesignContract, changing only what was asked."""
    content, usage = chat(
        [{"role": "system", "content": PLAN_SYSTEM},
         {"role": "user", "content": _CONTRACT_EDIT.format(
             contract=json.dumps(prior, ensure_ascii=False), instruction=instruction)}],
        json_mode=True, temperature=0.0, max_tokens=8000,
    )
    return DesignContract.from_dict(_extract_json(content)), usage, content


def _flatten(d: dict) -> dict:
    """Contract dict -> {field path: value}, flattened one level below kind (for comparison and diff)."""
    out = {"kind": d.get("kind")}
    for k, v in d.items():
        if k == "kind":
            continue
        if isinstance(v, dict):
            for kk, vv in v.items():
                out[f"{k}.{kk}"] = vv
        elif isinstance(v, list):
            out[k] = f"[{len(v)}]"          # lists compare by count (e.g. number of holes)
        else:
            out[k] = v
    return out


def diff_contract(old: dict, new: dict) -> list[dict]:
    """Changed fields between two contracts as a human-readable list: [{field, from, to}]."""
    fo, fn = _flatten(old), _flatten(new)
    changes = []
    for key in sorted(set(fo) | set(fn)):
        a, b = fo.get(key), fn.get(key)
        if a != b:
            changes.append({"field": key, "from": a, "to": b})
    return changes


# ──────────────────────────── Code (AnyCAD) editing ────────────────────────────

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
    """Current build123d code + edit instruction -> minimally edited new code."""
    content, usage = chat(
        [{"role": "system", "content": codegen.SYSTEM},
         {"role": "user", "content": _CODE_EDIT.format(
             code=prior_code, instruction=instruction)}],
        json_mode=False, temperature=0.0, max_tokens=12000,
    )
    return codegen._strip(content), usage


def design_edit_code(prior_code: str, instruction: str, stl_path, step_path,
                     max_iters: int = 3) -> dict:
    """Code edit + isolated run + auto-repair loop. Same return shape as design_code.

    it0 edits the current code as a seed; on failure, codegen's repair (error feedback) fixes it.
    """
    code = edit_code(prior_code, instruction)[0]
    last_code = code
    error = None
    for it in range(max_iters + 1):
        if it > 0:          # retries repair using the error feedback
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
