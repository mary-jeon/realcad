"""표준 볼트·체결 라이브러리 (US 인치 UNC/UNF 우선 + ISO 미터).

출처(ground truth): ASME B18.2.1(육각), B18.3(소켓캡), B18.2.8(공차구멍 Normal/Close/Loose),
B1.1(UN 나사). 치수는 인치 규격을 mm로 환산해 저장한다(build123d 기본 단위 mm).
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import re

IN = 25.4  # 1 inch = 25.4 mm


@dataclass(frozen=True)
class Fastener:
    name: str                 # "1/4-20 UNC" 등
    nominal_dia_mm: float      # 나사 바깥지름(major)
    pitch_mm: float            # 산 간격
    head_across_flats_mm: float
    head_height_mm: float
    # 공차구멍(clearance hole) 3등급 지름 — ASME B18.2.8
    clearance_close_mm: float
    clearance_normal_mm: float
    clearance_loose_mm: float

    @property
    def head_across_corners_mm(self) -> float:
        # 육각: 맞변거리 / cos30
        return self.head_across_flats_mm / math.cos(math.radians(30))

    def clearance(self, fit: str = "normal") -> float:
        return {
            "close": self.clearance_close_mm,
            "normal": self.clearance_normal_mm,
            "loose": self.clearance_loose_mm,
        }[fit]


# UNC 육각 캡 스크루 (ASME B18.2.1) + 공차구멍 (B18.2.8). 인치값→mm.
UNC: dict[str, Fastener] = {
    "1/4-20": Fastener("1/4-20 UNC", 0.250 * IN, (1 / 20) * IN,
                       (7 / 16) * IN, 0.163 * IN,
                       0.266 * IN, 0.281 * IN, 0.297 * IN),
    "5/16-18": Fastener("5/16-18 UNC", 0.3125 * IN, (1 / 18) * IN,
                        0.500 * IN, 0.211 * IN,
                        0.332 * IN, 0.344 * IN, 0.358 * IN),
    "3/8-16": Fastener("3/8-16 UNC", 0.375 * IN, (1 / 16) * IN,
                       0.5625 * IN, 0.243 * IN,
                       0.397 * IN, 0.406 * IN, 0.438 * IN),
    "#10-24": Fastener("#10-24 UNC", 0.190 * IN, (1 / 24) * IN,
                       0.3125 * IN, 0.110 * IN,
                       0.196 * IN, 0.201 * IN, 0.221 * IN),
    "#8-32": Fastener("#8-32 UNC", 0.164 * IN, (1 / 32) * IN,
                      0.34375 * IN, 0.110 * IN,
                      0.170 * IN, 0.177 * IN, 0.194 * IN),
    "#6-32": Fastener("#6-32 UNC", 0.138 * IN, (1 / 32) * IN,
                      0.25 * IN, 0.080 * IN,
                      0.144 * IN, 0.149 * IN, 0.166 * IN),
    "#4-40": Fastener("#4-40 UNC", 0.112 * IN, (1 / 40) * IN,
                      0.25 * IN, 0.067 * IN,
                      0.116 * IN, 0.120 * IN, 0.136 * IN),
    "1/2-13": Fastener("1/2-13 UNC", 0.500 * IN, (1 / 13) * IN,
                       0.750 * IN, 0.323 * IN,
                       0.531 * IN, 0.562 * IN, 0.625 * IN),
}

# ISO 미터 육각 (혼용 데모용). clearance: medium(ISO 273) 기준.
METRIC: dict[str, Fastener] = {
    "M3": Fastener("M3", 3.0, 0.5, 5.5, 2.0, 3.2, 3.4, 3.6),
    "M4": Fastener("M4", 4.0, 0.7, 7.0, 2.8, 4.3, 4.5, 4.8),
    "M5": Fastener("M5", 5.0, 0.8, 8.0, 3.5, 5.3, 5.5, 5.8),
    "M6": Fastener("M6", 6.0, 1.0, 10.0, 4.0, 6.4, 6.6, 7.0),
    "M8": Fastener("M8", 8.0, 1.25, 13.0, 5.3, 8.4, 9.0, 10.0),
}


ALL: dict[str, Fastener] = {**UNC, **METRIC}


def available() -> list[str]:
    return list(ALL.keys())


def _spec_to_mm(spec: str) -> float | None:
    """규격 문자열에서 나사 바깥지름(mm) 추정 — 미보유 규격의 근사 대체용."""
    s = spec.strip().upper().replace(" ", "")
    m = re.match(r"M(\d+(?:\.\d+)?)", s)
    if m:
        return float(m.group(1))
    m = re.match(r"#(\d+)", s)           # 미국 번호 나사: dia ≈ 0.060 + n*0.013 inch
    if m:
        return (0.060 + int(m.group(1)) * 0.013) * IN
    m = re.match(r"(\d+)/(\d+)", s)       # 분수 인치
    if m:
        return (int(m.group(1)) / int(m.group(2))) * IN
    m = re.match(r"(\d+(?:\.\d+)?)", s)   # 맨 앞 숫자(mm 가정)
    if m:
        return float(m.group(1))
    return None


def get(spec: str) -> Fastener:
    """"1/4-20"·"M6" 등으로 조회. 없으면 지름이 가장 가까운 규격으로 대체(크래시 방지)."""
    if spec in ALL:
        return ALL[spec]
    d = _spec_to_mm(spec)
    if d is not None:
        return min(ALL.values(), key=lambda f: abs(f.nominal_dia_mm - d))
    return UNC["1/4-20"]
