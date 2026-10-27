"""역질문 — 비전문가가 빠뜨린 '꼭 필요한' 정보만 되묻는다(ProCAD식). Meta 호출."""
from __future__ import annotations
from .meta_client import chat
from .planner import _extract_json

SYSTEM = """You are a MINIMAL intake assistant for a 3D-printed functional part designer.
STRONGLY prefer to ask NOTHING. The designer behind you infers sensible defaults on its own
(overall size, wall thickness, fit, fastener type and size). In almost all cases return an
empty question list and let it just build a reasonable first design.

Ask a question ONLY when a SINGLE critical fact is missing AND cannot be defaulted — for
example a mounting plate with no size at all, or "a case for my board" without saying which
board. Never ask more than 1 question. NEVER ask about trivia (button counts, colors, minor
features, "what goes inside") — the designer picks reasonable defaults for those.

If the request is an organic / freeform / sculpted shape that this tool cannot build from
parametric primitives (a computer mouse, a shoe, a figurine, an animal, a helmet, a handle
grip, a character, a vehicle body, etc.), return an EMPTY list — it is handled elsewhere by
3D-model retrieval, not by questions.

Ask in Korean, short and plain, with a sensible suggested default. Return JSON only:
{"questions": [{"key": "size", "question": "...", "suggestion": "..."}]}"""


def clarify(prompt: str) -> tuple[list[dict], dict]:
    content, usage = chat(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": prompt}],
        json_mode=True, temperature=0.0, max_tokens=4000,
    )
    data = _extract_json(content)
    qs = data.get("questions", []) if isinstance(data, dict) else []
    return qs[:1], usage


def augment(prompt: str, answers: dict | None) -> str:
    """사용자 답을 프롬프트에 붙여 planner 가 쓰게 한다."""
    if not answers:
        return prompt
    lines = [f"- {k}: {v}" for k, v in answers.items() if str(v).strip()]
    if not lines:
        return prompt
    return prompt + "\n\nAdditional details from the user:\n" + "\n".join(lines)
