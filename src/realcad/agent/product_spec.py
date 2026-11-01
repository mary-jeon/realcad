"""Commercial product spec lookup: when a prompt names a retail product (e.g. "a bracket to hang a mini PC"),
get its real outer dimensions from (1) the official spec table, then (2) the Meta model's memory with
self-reported confidence, and present them as confirmed / estimated / unknown. Only dimensions no model
can know (the counterpart, e.g. a stand arm or desk top) are asked of the user.

Flow: lookup_table (free, instant) -> extract_with_meta (one call, JSON) -> merge -> SpecCard
SpecCard.to_prompt() builds the SPEC block for codegen (authoritative dimensions + faces to keep clear).

Status by model self-confidence c:
  confirmed (official spec)  in the table, with a source URL
  confirmed (model memory)   c >= 0.9
  estimated                  0.6 <= c < 0.9, user confirmation recommended
  unknown                    c < 0.6, turned into a dimension question
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field, asdict
from .meta_client import chat

SURE = 0.9
GUESS = 0.6

# Official spec table: manufacturer published specs or international standards. (w, d, h) mm, weight g.
# keep_clear: faces/areas the design must not block.
KNOWN: list[dict] = [
    {"id": "mac_mini_m4", "name": "Apple Mac mini (M4, 2024)",
     "match": r"(맥\s*미니|mac\s*mini)",
     "w": 127.0, "d": 127.0, "h": 50.0, "weight_g": 670,
     "source": "https://support.apple.com/en-us/121555",
     "keep_clear": ["바닥: 공기 흡입과 배출이 모두 바닥에 있어 바닥 전체를 막으면 안 됨, 막대 몇 개로만 받치기",
                    "뒷면: 썬더볼트 3개, HDMI, 이더넷, 전원 코드가 꽂힘, 케이블 공간 60 mm 이상 비워두기",
                    "앞면: USB-C 2개와 이어폰 단자",
                    "바닥 뒤쪽 모서리: 전원 버튼, 손가락이 닿게 열어두기"]},
    {"id": "macbook_air_13_m3", "name": "Apple MacBook Air 13 (M3, 2024)",
     "match": r"(맥북\s*에어\s*13|macbook\s*air\s*13)",
     "w": 304.1, "d": 215.0, "h": 11.3, "weight_g": 1240,
     "source": "https://support.apple.com/en-us/118551",
     "keep_clear": ["양 옆면: 왼쪽 MagSafe 와 썬더볼트 2개, 오른쪽 이어폰 단자", "바닥 고무발 4개"]},
    {"id": "raspberry_pi_5", "name": "Raspberry Pi 5 (board)",
     "match": r"(라즈베리\s*파이\s*5|raspberry\s*pi\s*5|rpi\s*5)",
     "w": 85.0, "d": 56.0, "h": 17.0, "weight_g": 46,
     "source": "https://datasheets.raspberrypi.com/rpi5/raspberry-pi-5-mechanical-drawing.pdf",
     "keep_clear": ["고정 구멍 4개: 58 x 49 mm 간격, M2.5", "긴 변: USB 와 이더넷, 짧은 변: USB-C 전원과 micro HDMI 2개",
                    "윗면: 쿨러 또는 GPIO 핀 높이 여유"]},
    {"id": "switch_oled", "name": "Nintendo Switch OLED (with Joy-Con)",
     "match": r"(스위치\s*oled|switch\s*oled)",
     "w": 242.0, "d": 13.9, "h": 102.0, "weight_g": 420,
     "source": "https://www.nintendo.com/us/switch/tech-specs/",
     "keep_clear": ["아랫변: USB-C 와 스피커", "윗변: 배기구, 게임카드, 이어폰"]},
    {"id": "aa_battery", "name": "AA battery (IEC R6 / LR6)",
     "match": r"(\bAA\b|더블\s*에이|aa\s*건전지|aa\s*배터리)",
     "w": 14.5, "d": 14.5, "h": 50.5, "weight_g": 23,
     "source": "IEC 60086-2 R6", "keep_clear": []},
    {"id": "aaa_battery", "name": "AAA battery (IEC R03 / LR03)",
     "match": r"(\bAAA\b|트리플\s*에이|aaa\s*건전지|aaa\s*배터리)",
     "w": 10.5, "d": 10.5, "h": 44.5, "weight_g": 11,
     "source": "IEC 60086-2 R03", "keep_clear": []},
    {"id": "li_18650", "name": "18650 lithium cell",
     "match": r"18650",
     "w": 18.6, "d": 18.6, "h": 65.2, "weight_g": 47,
     "source": "IEC 61960 (18650 nominal 18 x 65, 실측 최대 18.6 x 65.2)", "keep_clear": []},
    {"id": "id1_card", "name": "ID-1 card (credit card)",
     "match": r"(신용\s*카드|체크\s*카드|credit\s*card|명함\s*크기|id-1)",
     "w": 85.6, "d": 53.98, "h": 0.76, "weight_g": 5,
     "source": "ISO/IEC 7810 ID-1", "keep_clear": []},
]


@dataclass
class ProductSpec:
    name: str
    w: float | None = None
    d: float | None = None
    h: float | None = None
    weight_g: float | None = None
    confidence: float = 0.0
    status: str = "모름"            # confirmed (official spec) / confirmed (model memory) / estimated / unknown
    source: str = ""
    keep_clear: list[str] = field(default_factory=list)

    def dims_text(self) -> str:
        if self.w is None:
            return "?"
        return f"{self.w:g} x {self.d:g} x {self.h:g}"


@dataclass
class SpecCard:
    products: list[ProductSpec] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)   # dimension questions about the counterpart object {key, question, suggestion}
    counterpart: str = ""                                   # name of the counterpart object this part attaches to
    usage: dict = field(default_factory=dict)

    def rows(self) -> list[dict]:
        return [asdict(p) | {"dims": p.dims_text()} for p in self.products]

    def to_prompt(self) -> str:
        """Authoritative dimension block for codegen. Empty string if there are no products."""
        if not self.products:
            return ""
        out = []
        for p in self.products:
            if p.w is None:
                continue
            out.append(f"SPEC — {p.name} [{p.status}, {p.source or 'model recall'}]: outer size "
                       f"{p.dims_text()} mm (W x D x H), weight {p.weight_g or '?'} g. Treat as authoritative. "
                       f"This part must FIT AROUND / HOLD this product, so apply the CLEARANCE discipline "
                       f"(cavity = product + 2 x 0.2 mm per side, default NORMAL fit) and never build at the raw size.")
            if p.keep_clear:
                out.append("KEEP CLEAR (do not cover, leave open): " + "; ".join(p.keep_clear))
        return "\n".join(out)

    def to_dict(self) -> dict:
        return {"products": self.rows(), "questions": self.questions,
                "counterpart": self.counterpart, "spec_text": self.to_prompt()}


def lookup_table(prompt: str) -> list[ProductSpec]:
    """Find products named in the prompt in the official spec table. Free and instant."""
    hits = []
    for k in KNOWN:
        if re.search(k["match"], prompt, re.I):
            hits.append(ProductSpec(name=k["name"], w=k["w"], d=k["d"], h=k["h"], weight_g=k["weight_g"],
                                    confidence=1.0, status="확실(공식 규격)", source=k["source"],
                                    keep_clear=list(k["keep_clear"])))
    return hits


SYSTEM = """You are the intake step of a 3D-printed bracket/holder/case designer.
Read the user's request and answer JSON only:
{
 "products": [ {"name": "...", "w_mm": 0, "d_mm": 0, "h_mm": 0, "weight_g": 0, "confidence": 0.0,
                "keep_clear": ["faces or spots the holder must not cover, in Korean, short"]} ],
 "counterpart": "the OTHER object this part attaches to (e.g. a laptop stand arm, a desk edge, a monitor), or empty",
 "questions": [ {"key": "arm_width", "question": "Korean, one line, what to measure and how", "suggestion": "a typical value with unit"} ]
}
Rules:
- "products" = commercially sold products named in the request whose outer dimensions are published
  (Mac mini, Raspberry Pi, a game console, a phone model...). Give the OFFICIAL spec values in mm.
  confidence = your honest probability that these are the exact official numbers (1.0 only if you are sure).
  If you do not know a product, still list it with confidence <= 0.3 and nulls.
- "questions" = ONLY measurements that NO model can know: the counterpart's width/thickness/gap,
  which way the user wants the product oriented, where it must attach. Max 3, most important first.
  Do NOT ask about things that are published specs or that the designer can default (wall thickness, fit).
- Answer in Korean for question/suggestion/keep_clear text. No markdown."""


def extract_with_meta(prompt: str) -> tuple[dict, dict]:
    content, usage = chat([{"role": "system", "content": SYSTEM},
                           {"role": "user", "content": prompt}],
                          json_mode=True, temperature=0.0, max_tokens=6000)
    text = content.strip()
    s, e = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[s:e + 1])
    except Exception:
        data = {}
    return (data if isinstance(data, dict) else {}), usage


def _status(c: float) -> str:
    if c >= SURE:
        return "확실(모델 기억)"
    if c >= GUESS:
        return "추정"
    return "모름"


def _num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _dup_of_table(name: str, dims: tuple, table_hits: list[ProductSpec]) -> bool:
    by_name = {k["name"]: k for k in KNOWN}
    for t in table_hits:
        k = by_name.get(t.name)
        if k and re.search(k["match"], name, re.I):
            return True
        if all(v is not None for v in dims) and all(
                abs(a - b) <= 0.02 * max(b, 1.0) for a, b in zip(sorted(dims), sorted((t.w, t.d, t.h)))):
            return True
    return False


def merge(table_hits: list[ProductSpec], data: dict) -> SpecCard:
    """Table values take precedence over model values. Products not in the table get model values plus a confidence status."""
    card = SpecCard(products=list(table_hits))
    seen = {p.name.lower() for p in card.products}
    for item in (data.get("products") or []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        c = _num(item.get("confidence")) or 0.0
        w, d, h = _num(item.get("w_mm")), _num(item.get("d_mm")), _num(item.get("h_mm"))
        # Drop the model value for a product already found in the table: its keyword regex matches the model's name, or dimensions agree within 2%.
        if _dup_of_table(name, (w, d, h), table_hits):
            continue
        p = ProductSpec(name=name, w=w, d=d, h=h, weight_g=_num(item.get("weight_g")),
                        confidence=round(c, 2), status=_status(c) if w else "모름",
                        source="", keep_clear=[str(x) for x in (item.get("keep_clear") or [])][:4])
        if p.status == "모름":
            p.w = p.d = p.h = None
        card.products.append(p)
        seen.add(name.lower())
    card.counterpart = str(data.get("counterpart") or "")
    qs = []
    for q in (data.get("questions") or [])[:3]:
        if isinstance(q, dict) and q.get("question"):
            qs.append({"key": str(q.get("key", f"q{len(qs)+1}")), "question": str(q["question"]),
                       "suggestion": str(q.get("suggestion", ""))})
    # unknown products become dimension questions
    for p in card.products:
        if p.status == "모름" and len(qs) < 3:
            qs.append({"key": "size_" + re.sub(r"\W+", "_", p.name.lower())[:20],
                       "question": f"{p.name} 의 가로 x 세로 x 높이(mm)를 자로 재서 알려줘",
                       "suggestion": ""})
    card.questions = qs
    return card


def lookup(prompt: str, use_meta: bool = True) -> SpecCard:
    """Prompt -> SpecCard. With use_meta=False only the table is used (tests, offline)."""
    hits = lookup_table(prompt)
    if not use_meta:
        return merge(hits, {})
    try:
        data, usage = extract_with_meta(prompt)
    except Exception as e:      # if the model call fails, continue with the table only
        card = merge(hits, {})
        card.usage = {"error": str(e)[:200]}
        return card
    card = merge(hits, data)
    card.usage = usage
    return card


def answers_text(answers: dict | None) -> str:
    """Turn the user's counterpart dimensions into the MEASURED block that codegen reads."""
    if not answers:
        return ""
    lines = [f"- {k}: {v}" for k, v in answers.items() if str(v).strip()]
    if not lines:
        return ""
    return ("MEASURED by the user (the counterpart object this part attaches to; build the mating "
            "features to THESE values plus clearance):\n" + "\n".join(lines))
