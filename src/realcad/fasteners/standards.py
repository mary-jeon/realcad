"""표준 볼트·체결 라이브러리 — US 인치(UNC/UNF) + ISO 미터.

값 출처(모두 공개 규격·공개 참고표, 단위는 mm 로 환산 저장):
- 공차구멍(clearance hole, close/normal/loose) = **ASME B18.2.8-1999 표의 최소 구멍지름**.
  #4 .120/.1285/.144 · #6 .154/.170/.185 · #8 .180/.196/.213 · #10 .206/.221/.238 ·
  1/4 .266/.281/.297 · 5/16 .328/.344/.359 · 3/8 .391/.406/.422 · 1/2 .531/.562/.609 (in)
  미터(B18.2.8 / ISO 273 동일): M2 2.2/2.4/2.6 · M2.5 2.7/2.9/3.1 · M3 3.2/3.4/3.6 · M4 4.3/4.5/4.8 ·
  M5 5.3/5.5/5.8 · M6 6.4/6.6/7.0 · M8 8.4/9.0/10.0 · M10 10.5/11/12 · M12 13/13.5/14.5
- 머리: 1/4~1/2 = ASME B18.2.1 육각 캡스크루(맞변 F, 높이 H, 맞모 최소 G),
        #4~#10 = ASME B18.6.3 육각 머리 기계나사(맞변 A, 높이 H, 맞모 최소 W),
        미터 = ISO 4017 육각 볼트(s, k, e_min).
- 너트 높이 = ASME B18.2.2 육각 너트 / ISO 4032. 와셔 = SAE 평와셔(narrow) / ISO 7089. (참고값)
- 소켓 바깥지름 = 6각 소켓 일반 치수(공구 접근 검사용, 제조사별 ±1 mm 편차 — 참고값).

2026-10-29: 이전 판은 번호나사 4종의 공차구멍이 규격보다 한 등급 작았고(normal ≈ 규격 close),
#8 머리에 너트 폭이 들어가 있었으며, 미보유 규격을 조용히 치환했다. 전부 정정.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import re

IN = 25.4  # 1 inch = 25.4 mm


@dataclass(frozen=True)
class Fastener:
    name: str                  # "1/4-20 UNC", "M6" 등
    nominal_dia_mm: float      # 나사 바깥지름(major)
    pitch_mm: float            # 산 간격
    head_across_flats_mm: float
    head_height_mm: float
    # 공차구멍(clearance hole) 3등급 지름 — ASME B18.2.8 최소값
    clearance_close_mm: float
    clearance_normal_mm: float
    clearance_loose_mm: float
    # 아래는 선택(기본값 있음)
    head_across_corners_min_mm: float = 0.0   # 규격 맞모거리 최소(챔퍼 반영). 0이면 AF/cos30 로 계산
    head_type: str = "hex_cap"                # hex_cap | hex_machine | hex_bolt
    series: str = "UNC"                       # UNC | UNF | ISO
    nut_height_mm: float = 0.0                # 육각 너트 높이(관통 체결 BOM 용)
    washer_od_mm: float = 0.0                 # 평와셔 바깥지름
    washer_t_mm: float = 0.0                  # 평와셔 두께
    socket_od_mm: float = 0.0                 # 6각 소켓 바깥지름(공구 접근 H5 용, 참고값)

    @property
    def head_across_corners_mm(self) -> float:
        """머리 맞모거리. 규격 최소값이 있으면 그것(실물은 챔퍼 때문에 AF/cos30 보다 작다)."""
        if self.head_across_corners_min_mm > 0:
            return self.head_across_corners_min_mm
        return self.head_across_flats_mm / math.cos(math.radians(30))

    @property
    def is_metric(self) -> bool:
        return self.series == "ISO"

    def clearance(self, fit: str = "normal") -> float:
        try:
            return {"close": self.clearance_close_mm,
                    "normal": self.clearance_normal_mm,
                    "loose": self.clearance_loose_mm}[fit]
        except KeyError:
            raise ValueError(f"fit 은 close/normal/loose 중 하나 ({fit!r})") from None


def _in(name, dia, tpi, af, h, cc, cn, cl, ac, head_type, series, nut_h, w_od, w_t, sock):
    return Fastener(name, dia * IN, (1 / tpi) * IN, af * IN, h * IN,
                    cc * IN, cn * IN, cl * IN, ac * IN, head_type, series,
                    nut_h * IN, w_od * IN, w_t * IN, sock)


# ── 인치 UNC (거친 나사) ─────────────────────────────────────────────
#            name        dia    tpi  AF     H      close  normal loose  ACmin head_type     series nut_h w_od  w_t   socket_od(mm)
UNC: dict[str, Fastener] = {
    "#4-40":   _in("#4-40 UNC",   0.112, 40, 0.188, 0.060, 0.120, 0.1285, 0.144, 0.202, "hex_machine", "UNC", 0.098, 0.312, 0.032, 9.5),
    "#6-32":   _in("#6-32 UNC",   0.138, 32, 0.250, 0.093, 0.154, 0.170, 0.185, 0.272, "hex_machine", "UNC", 0.114, 0.375, 0.049, 11.5),
    "#8-32":   _in("#8-32 UNC",   0.164, 32, 0.250, 0.110, 0.180, 0.196, 0.213, 0.272, "hex_machine", "UNC", 0.130, 0.438, 0.049, 11.5),
    "#10-24":  _in("#10-24 UNC",  0.190, 24, 0.312, 0.120, 0.206, 0.221, 0.238, 0.340, "hex_machine", "UNC", 0.130, 0.500, 0.049, 13.5),
    "1/4-20":  _in("1/4-20 UNC",  0.250, 20, 0.4375, 0.163, 0.266, 0.281, 0.297, 0.488, "hex_cap", "UNC", 0.226, 0.625, 0.065, 16.5),
    "5/16-18": _in("5/16-18 UNC", 0.3125, 18, 0.500, 0.211, 0.328, 0.344, 0.359, 0.557, "hex_cap", "UNC", 0.273, 0.688, 0.065, 18.5),
    "3/8-16":  _in("3/8-16 UNC",  0.375, 16, 0.5625, 0.243, 0.391, 0.406, 0.422, 0.628, "hex_cap", "UNC", 0.337, 0.812, 0.065, 20.5),
    "1/2-13":  _in("1/2-13 UNC",  0.500, 13, 0.750, 0.323, 0.531, 0.562, 0.609, 0.840, "hex_cap", "UNC", 0.448, 1.062, 0.095, 26.0),
}

# ── 인치 UNF (가는 나사) — 머리·구멍은 같은 호칭의 UNC 와 동일, 피치만 다름 ──
_UNF_TPI = {"#4-40": ("#4-48", 48), "#6-32": ("#6-40", 40), "#8-32": ("#8-36", 36), "#10-24": ("#10-32", 32),
            "1/4-20": ("1/4-28", 28), "5/16-18": ("5/16-24", 24), "3/8-16": ("3/8-24", 24), "1/2-13": ("1/2-20", 20)}
UNF: dict[str, Fastener] = {}
for _k, (_name, _tpi) in _UNF_TPI.items():
    _b = UNC[_k]
    UNF[_name] = Fastener(_name + " UNF", _b.nominal_dia_mm, (1 / _tpi) * IN, _b.head_across_flats_mm,
                          _b.head_height_mm, _b.clearance_close_mm, _b.clearance_normal_mm,
                          _b.clearance_loose_mm, _b.head_across_corners_min_mm, _b.head_type, "UNF",
                          _b.nut_height_mm, _b.washer_od_mm, _b.washer_t_mm, _b.socket_od_mm)

# ── ISO 미터 (ISO 4017 육각, ISO 273 공차구멍 medium=normal) ───────────────
#                       name  dia  pitch  s(AF) k(H)  close normal loose e_min  head_type  series nut_h w_od  w_t  socket
METRIC: dict[str, Fastener] = {
    "M2":   Fastener("M2",   2.0, 0.40,  4.0,  1.4,  2.2,  2.4,  2.6,  4.32, "hex_bolt", "ISO", 1.6, 5.0,  0.3, 7.5),
    "M2.5": Fastener("M2.5", 2.5, 0.45,  5.0,  1.7,  2.7,  2.9,  3.1,  5.45, "hex_bolt", "ISO", 2.0, 6.0,  0.5, 8.5),
    "M3":   Fastener("M3",   3.0, 0.50,  5.5,  2.0,  3.2,  3.4,  3.6,  6.01, "hex_bolt", "ISO", 2.4, 7.0,  0.5, 9.5),
    "M4":   Fastener("M4",   4.0, 0.70,  7.0,  2.8,  4.3,  4.5,  4.8,  7.66, "hex_bolt", "ISO", 3.2, 9.0,  0.8, 11.0),
    "M5":   Fastener("M5",   5.0, 0.80,  8.0,  3.5,  5.3,  5.5,  5.8,  8.79, "hex_bolt", "ISO", 4.7, 10.0, 1.0, 13.0),
    "M6":   Fastener("M6",   6.0, 1.00, 10.0,  4.0,  6.4,  6.6,  7.0, 11.05, "hex_bolt", "ISO", 5.2, 12.0, 1.6, 15.0),
    "M8":   Fastener("M8",   8.0, 1.25, 13.0,  5.3,  8.4,  9.0, 10.0, 14.38, "hex_bolt", "ISO", 6.8, 16.0, 1.6, 18.0),
    "M10":  Fastener("M10", 10.0, 1.50, 16.0,  6.4, 10.5, 11.0, 12.0, 17.77, "hex_bolt", "ISO", 8.4, 20.0, 2.0, 22.0),
    "M12":  Fastener("M12", 12.0, 1.75, 18.0,  7.5, 13.0, 13.5, 14.5, 20.03, "hex_bolt", "ISO", 10.8, 24.0, 2.5, 24.5),
}

ALL: dict[str, Fastener] = {**UNC, **UNF, **METRIC}

# 표준 볼트 길이(BOM 용, 올림 선택). 인치는 mm 환산.
STD_LENGTHS_IN_MM = [round(x * IN, 2) for x in (0.25, 0.375, 0.5, 0.625, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 3.5, 4.0)]
STD_LENGTHS_MM = [4, 5, 6, 8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 55, 60, 70, 80, 90, 100]


def available() -> list[str]:
    return list(ALL.keys())


class UnknownFastener(KeyError):
    """보유하지 않은 규격. nearest 에 가장 가까운 규격 이름을 담아 준다(명시적 제안용)."""

    def __init__(self, spec: str, nearest: str | None):
        super().__init__(spec)
        self.spec, self.nearest = spec, nearest

    def __str__(self) -> str:
        hint = f" (가장 가까운 보유 규격: {self.nearest})" if self.nearest else ""
        return f"미지원 체결 규격 {self.spec!r}{hint}. 보유: {', '.join(ALL)}"


_COARSE_FOR = {"#4": "#4-40", "#6": "#6-32", "#8": "#8-32", "#10": "#10-24",
               "1/4": "1/4-20", "5/16": "5/16-18", "3/8": "3/8-16", "1/2": "1/2-13"}


def normalize(spec: str) -> str | None:
    """느슨한 표기 → 표 키. 'M6x1', 'm6', '1/4-20 UNC', '#10-24 unc', '1/4(거친 기본)', '#8' 등. 표에 없으면 None."""
    s = (spec or "").strip().upper().replace(" ", "").replace('"', "")
    s = re.sub(r"(UNC|UNF|UN)$", "", s)
    m = re.match(r"^M(\d+(?:\.\d+)?)(?:X[\d.]+)?$", s)        # M6, M6X1, M2.5
    if m:
        num = m.group(1)
        if "." in num:
            num = num.rstrip("0").rstrip(".")
        key = "M" + num
        return key if key in METRIC else None
    m = re.match(r"^(#\d+|\d+/\d+)-(\d+)$", s)                  # #10-24, 1/4-28
    if m:
        key = f"{m.group(1)}-{m.group(2)}"
        return key if key in ALL else None
    if s in _COARSE_FOR:                                        # '1/4' → 거친 나사 기본
        return _COARSE_FOR[s]
    return None


def _spec_to_mm(spec: str) -> float | None:
    """규격 문자열에서 나사 바깥지름(mm) 추정 — 가장 가까운 규격 제안용."""
    s = (spec or "").strip().upper().replace(" ", "")
    m = re.match(r"M(\d+(?:\.\d+)?)", s)
    if m:
        return float(m.group(1))
    m = re.match(r"#(\d+)", s)           # 번호 나사: dia ≈ 0.060 + n*0.013 inch
    if m:
        return (0.060 + int(m.group(1)) * 0.013) * IN
    m = re.match(r"(\d+)/(\d+)", s)       # 분수 인치
    if m:
        return (int(m.group(1)) / int(m.group(2))) * IN
    return None


def suggest_nearest(spec: str) -> str | None:
    """미지원 규격에 대해 같은 계열(미터/인치) 중 지름이 가장 가까운 규격 이름."""
    d = _spec_to_mm(spec)
    if d is None:
        return None
    pool = METRIC if spec.strip().upper().startswith("M") else UNC
    return min(pool, key=lambda k: abs(pool[k].nominal_dia_mm - d))


def get(spec: str) -> Fastener:
    """정확한 규격만 돌려준다. 없으면 UnknownFastener(가까운 규격 제안 포함) — 조용한 치환 금지."""
    key = spec if spec in ALL else normalize(spec)
    if key is None:
        raise UnknownFastener(spec, suggest_nearest(spec))
    return ALL[key]


def resolve(spec: str) -> tuple[Fastener, bool, str]:
    """(fastener, exact, note). 미지원이면 가장 가까운 규격을 돌려주되 exact=False 와 설명을 붙인다.
    파이프라인은 exact=False 를 HARD 실패(F0)로 보고해 사용자가 알고 고르게 한다."""
    try:
        return get(spec), True, ""
    except UnknownFastener as e:
        if e.nearest:
            return ALL[e.nearest], False, f"{spec!r} 규격 없음 → {e.nearest} 로 계산함(확인 필요)"
        return UNC["1/4-20"], False, f"{spec!r} 규격을 해석할 수 없음 → 1/4-20 UNC 로 계산함(확인 필요)"


def std_length(f: Fastener, required_mm: float) -> float:
    """필요 길이 이상인 가장 짧은 표준 볼트 길이."""
    table = STD_LENGTHS_MM if f.is_metric else STD_LENGTHS_IN_MM
    for L in table:
        if L >= required_mm - 1e-6:
            return float(L)
    return float(table[-1])
