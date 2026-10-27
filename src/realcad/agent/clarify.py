"""역질문 — 비전문가가 빠뜨린 '꼭 필요한' 정보만 되묻는다(ProCAD식). Meta 호출."""
from __future__ import annotations
from .meta_client import chat
from .planner import _extract_json

SYSTEM = """You are a friendly intake assistant for a 3D-printed functional part designer.
Given the user's request (which may be vague, e.g. "a pencil holder"), decide what ESSENTIAL
information is missing to make a good first design, and ask ONLY those questions (max 4).
Typical essentials: overall size, what it must hold/fit, fastener type and size, number of
fastening points. If the request already gives enough to make a reasonable first design,
return an empty list.
Ask in Korean, short and plain (a non-engineer must understand). Give a sensible suggested
default for each. Return JSON only:
{"questions": [{"key": "size", "question": "...", "suggestion": "..."}]}"""


def clarify(prompt: str) -> tuple[list[dict], dict]:
    content, usage = chat(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": prompt}],
        json_mode=True, temperature=0.0, max_tokens=4000,
    )
    data = _extract_json(content)
    qs = data.get("questions", []) if isinstance(data, dict) else []
    return qs[:4], usage


def augment(prompt: str, answers: dict | None) -> str:
    """사용자 답을 프롬프트에 붙여 planner 가 쓰게 한다."""
    if not answers:
        return prompt
    lines = [f"- {k}: {v}" for k, v in answers.items() if str(v).strip()]
    if not lines:
        return prompt
    return prompt + "\n\nAdditional details from the user:\n" + "\n".join(lines)
