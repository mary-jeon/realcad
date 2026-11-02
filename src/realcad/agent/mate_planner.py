"""Mate planner: "put the board on the case posts" -> mates that the solver can place (geometry/mates.py).

The model never types coordinates for the result. It only chooses which measured features touch which,
from the feature table of every part (flat faces P*, holes H*, pins and bosses B*). The solver places the
parts, then every mate and every pair of parts is measured; if a mate cannot be met or parts collide,
the measurements go back to the model once to choose again.
"""
from __future__ import annotations

import json
import re

from .meta_client import chat

SYSTEM = """You assemble CAD parts with mates, as in a CAD assembly. You get each part's measured features
(part coordinates, mm, Z up) and the user's instruction. Choose mates; a solver places the parts from them.

Feature ids: P* = flat face (normal = outward direction it faces), H* = hole, B* = pin/boss/outer cylinder.
Mate types:
 {"type":"coincident","a":"<part>:<P id>","b":"<part>:<P id>"}            two flat faces touch, facing each other
 {"type":"coincident","a":...,"b":...,"aligned":true}                       two flat faces flush, facing the same way
 {"type":"distance","a":"<part>:<P id>","b":"<part>:<P id>","value":<mm>}   faces facing each other with a gap
 {"type":"concentric","a":"<part>:<H or B id>","b":"<part>:<H or B id>"}    same axis (screw hole over screw hole, pin in hole)
   add "flip":true only to turn the part end for end on that axis.
Rules:
- The FIRST part in the list stays fixed. Every other part needs mates that tie it to a part placed before it.
- Fully define each part when you can: one face mate + two concentric mates on a hole pattern, or three face mates.
- Board on posts or standoffs: concentric between two board mounting holes and the matching post holes
  (pick two holes far apart, matching their spacing), plus coincident between the board's bottom face (normal -Z)
  and the TOP face of a post (normal +Z, the small face at the top of the post, not the case floor).
- Hole patterns must match: the distance between the two holes you pick on one part must equal the distance between
  the two you pick on the other part. Check this with the centers before answering.
- Use only ids that appear in the tables. Never invent coordinates.
Return JSON only:
{"mates":[...], "why":"<one short Korean sentence: what touches what>"}"""


def _tables_text(tables: dict) -> str:
    out = []
    for name, t in tables.items():
        out.append(f"PART {name}: bbox {t['bbox_mm']}")
        for a in t["axes"]:
            out.append(f"  {a['id']} {a['kind']} dia {a['dia']} axis {a['axis']} center {a['center']} length {a['length']}")
        for p in t["planes"]:
            out.append(f"  {p['id']} face normal {p['normal']} center {p['center']} area {p['area_mm2']} x{p['x']} y{p['y']} z{p['z']}")
    return "\n".join(out)


def _parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    d = json.loads(m.group(0) if m else text)
    mates = d.get("mates") or []
    if not isinstance(mates, list) or not mates:
        raise ValueError("메이트를 하나도 못 정했어요")
    if len(mates) > 40:
        raise ValueError(f"메이트가 너무 많아요 ({len(mates)}개, 최대 40)")
    for i, m in enumerate(mates, 1):
        if not isinstance(m, dict) or not m.get("type") or not m.get("a") or not m.get("b"):
            raise ValueError(f"메이트 {i}번에 type, a, b 가 다 있어야 해요: {str(m)[:120]}")
    return {"mates": mates, "why": re.sub(r"\s*[·—–]\s*", ", ", str(d.get("why") or ""))[:300]}


def plan(instruction: str, tables: dict, feedback: str = "") -> dict:
    """-> {"mates": [...], "why": str}. tables: {part name: feature_table(...)} in assembly order (first = fixed)."""
    user = (f"Parts (first one is fixed): {', '.join(tables)}\n\n{_tables_text(tables)}\n\n"
            f"Instruction: {instruction.strip()}")
    if feedback:
        user += "\n\nYour previous mates were placed and measured. Fix them:\n" + feedback
    out, _u = chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                   json_mode=True, temperature=0.0, max_tokens=8000)
    return _parse(out)
