"""기계요소 규격표: 평행키, 깊은 홈 볼베어링, C형 멈춤링, 오일실, V벨트 풀리 홈, 스퍼기어 공식.

출처(조사 문서 01_리서치/동력전달장치_조립_규격조사_20261030.md 에 URL 전체):
- 평행키: KS B 1311 (JIS B 1301 동등). Miki Pulley 표, PAES 304:2000 교차 확인.
- 베어링: KS B 2023 (ISO 15 치수계열). 6203/6204/6205 는 NSK 카탈로그 값, 나머지는 ISO 15 표준 치수.
- 멈춤링(C형 축용): KS B 1336 (JIS B 2804). Misumi FC-32 PDF, Miki Pulley.
- 오일실: KS B 2804 (JIS B 2402-1). 20x35x7 은 SKF/DDS 제품 페이지로 확인, 그 외는 통용 카탈로그 조합.
- V풀리 홈: KS B 1400 (JIS B 1854-1987 동등). Misumi(NBK) 표.
- 기어: KHK 기술자료 표준 치형(압력각 20도, 이끝 1.0m, 이뿌리 1.25m).

`verified` 가 True 인 행은 조사에서 1차 자료로 확인한 값, False 는 표준 치수계열 값(원문 재확인 권장).
"""
from __future__ import annotations
from dataclasses import dataclass
import math


# ── 평행키 KS B 1311 ───────────────────────────────────────────────────
@dataclass(frozen=True)
class KeySpec:
    b: float          # 키 폭
    h: float          # 키 높이
    t1: float         # 축 홈 깊이
    t2: float         # 허브 홈 깊이
    d_min: float      # 적용 축 지름(초과)
    d_max: float      # 적용 축 지름(이하)
    verified: bool = True

    @property
    def name(self) -> str:
        return f"{self.b:g}x{self.h:g}"

    @property
    def top_clearance(self) -> float:
        """키 윗면과 허브 홈 바닥 사이 틈 = t1 + t2 - h (6x6 이면 0.3)."""
        return round(self.t1 + self.t2 - self.h, 3)


# (d_min, d_max, b, h, t1, t2, verified)
_KEYS = [
    (6, 8, 2, 2, 1.2, 1.0, False),
    (8, 10, 3, 3, 1.8, 1.4, True),
    (10, 12, 4, 4, 2.5, 1.8, True),
    (12, 17, 5, 5, 3.0, 2.3, True),
    (17, 22, 6, 6, 3.5, 2.8, True),
    (22, 30, 8, 7, 4.0, 3.3, True),
    (30, 38, 10, 8, 5.0, 3.3, True),
    (38, 44, 12, 8, 5.0, 3.3, True),
    (44, 50, 14, 9, 5.5, 3.8, True),
    (50, 58, 16, 10, 6.0, 4.3, True),
    (58, 65, 18, 11, 7.0, 4.4, False),
    (65, 75, 20, 12, 7.5, 4.9, False),
]


def parallel_key(shaft_d: float) -> KeySpec:
    """축 지름 → 평행키 규격. 범위 밖이면 ValueError."""
    for lo, hi, b, h, t1, t2, ok in _KEYS:
        if lo < shaft_d <= hi:
            return KeySpec(b, h, t1, t2, lo, hi, ok)
    raise ValueError(f"평행키 표 범위 밖 축 지름 {shaft_d} (6 초과 75 이하만)")


# ── 깊은 홈 볼베어링 KS B 2023 / ISO 15 ───────────────────────────────
@dataclass(frozen=True)
class BearingSpec:
    code: str
    d: float          # 내경
    D: float          # 외경
    B: float          # 폭
    r: float          # 모따기 최소
    da_min: float     # 축 턱 지름 최소(내륜 측면만 닿게)
    da_max: float     # 축 턱 지름 최대
    Da_max: float     # 하우징 턱 지름 최대(외륜 측면만 닿게)
    verified: bool = False

    @property
    def ball_d(self) -> float:
        """간략 모델용 볼 지름(단면 높이의 60%)."""
        return round(0.6 * (self.D - self.d) / 2.0, 2)

    @property
    def pitch_d(self) -> float:
        return (self.d + self.D) / 2.0


def _bearing(code, d, D, B, r, da=None, Da=None, verified=False):
    # 턱 지름 폴백: 축 턱 d+5 ~ d+0.25(D-d), 하우징 턱 D-5 (6204/6205 NSK 값과 일치하는 근사식)
    da_min, da_max = (da if da else (d + 5.0, round(d + 0.25 * (D - d), 1)))
    Da_max = Da if Da else D - 5.0
    return BearingSpec(code, d, D, B, r, da_min, da_max, Da_max, verified)


BEARINGS: dict[str, BearingSpec] = {b.code: b for b in [
    _bearing("6000", 10, 26, 8, 0.3), _bearing("6001", 12, 28, 8, 0.3), _bearing("6002", 15, 32, 9, 0.3),
    _bearing("6003", 17, 35, 10, 0.3), _bearing("6004", 20, 42, 12, 0.6), _bearing("6005", 25, 47, 12, 0.6),
    _bearing("6006", 30, 55, 13, 1.0),
    _bearing("6200", 10, 30, 9, 0.6), _bearing("6201", 12, 32, 10, 0.6), _bearing("6202", 15, 35, 11, 0.6),
    _bearing("6203", 17, 40, 12, 0.6, verified=True),
    _bearing("6204", 20, 47, 14, 1.0, da=(25.0, 26.5), Da=42.0, verified=True),
    _bearing("6205", 25, 52, 15, 1.0, da=(30.0, 32.0), Da=47.0, verified=True),
    _bearing("6206", 30, 62, 16, 1.0), _bearing("6207", 35, 72, 17, 1.1),
    _bearing("6300", 10, 35, 11, 0.6), _bearing("6301", 12, 37, 12, 1.0), _bearing("6302", 15, 42, 13, 1.0),
    _bearing("6303", 17, 47, 14, 1.0), _bearing("6304", 20, 52, 15, 1.1), _bearing("6305", 25, 62, 17, 1.1),
]}


def bearing(code: str) -> BearingSpec:
    c = str(code).strip().upper().replace("ZZ", "").replace("-2RS", "").replace("2RS", "")
    if c not in BEARINGS:
        raise ValueError(f"미지원 베어링 {code!r}. 지원: {', '.join(BEARINGS)}")
    return BEARINGS[c]


def bearing_for_shaft(d: float, series: str = "62") -> BearingSpec:
    """축 지름(내경)으로 베어링 고르기(기본 6200 계열)."""
    for b in BEARINGS.values():
        if b.code.startswith(series) and abs(b.d - d) < 1e-6:
            return b
    raise ValueError(f"내경 {d} 의 {series}xx 베어링 없음")


# ── C형 멈춤링(축용) KS B 1336 ───────────────────────────────────────
@dataclass(frozen=True)
class RingSpec:
    d1: float         # 호칭(축 지름)
    d3: float         # 링 안지름(자유 상태)
    t: float          # 두께
    b: float          # 링 폭(최대 단면)
    d2: float         # 홈 지름
    m: float          # 홈 폭
    n: float          # 홈에서 축 끝까지 최소 거리
    verified: bool = True

    @property
    def groove_depth(self) -> float:
        return round((self.d1 - self.d2) / 2.0, 3)

    @property
    def od(self) -> float:
        """장착 상태 바깥지름 근사 d4 = d3 + 1.45 b."""
        return round(self.d3 + 1.45 * self.b, 1)


_RINGS = [
    # d1, d3, t, b, d2, m, n, verified
    (10, 9.3, 1.0, 1.6, 9.6, 1.15, 1.5, False),
    (12, 11.1, 1.0, 1.8, 11.5, 1.15, 1.5, False),
    (15, 13.8, 1.0, 2.1, 14.3, 1.15, 1.5, True),
    (16, 14.7, 1.0, 2.2, 15.2, 1.15, 1.5, False),
    (17, 15.7, 1.0, 2.2, 16.2, 1.15, 1.5, True),
    (20, 18.5, 1.2, 2.7, 19.0, 1.35, 1.5, True),
    (25, 23.2, 1.2, 3.1, 23.9, 1.35, 1.5, True),
    (30, 27.9, 1.6, 3.5, 28.6, 1.75, 2.0, True),
    (35, 32.2, 1.6, 4.0, 33.0, 1.75, 2.0, False),
    (40, 37.0, 1.8, 4.5, 38.0, 1.95, 2.5, False),
]


def retaining_ring(shaft_d: float) -> RingSpec:
    for row in _RINGS:
        if abs(row[0] - shaft_d) < 1e-6:
            return RingSpec(*row)
    raise ValueError(f"멈춤링 표에 없는 축 지름 {shaft_d} (지원: {', '.join(str(r[0]) for r in _RINGS)})")


# ── 오일실 KS B 2804 (d x D x b) ──────────────────────────────────────
@dataclass(frozen=True)
class SealSpec:
    d: float
    D: float
    b: float
    verified: bool = False

    @property
    def name(self) -> str:
        return f"{self.d:g}x{self.D:g}x{self.b:g}"


_SEALS = {10: (20, 5, False), 12: (22, 7, False), 15: (25, 5, False), 17: (30, 7, False), 20: (35, 7, True), 25: (40, 7, False),
          30: (45, 8, False), 35: (50, 8, False), 40: (55, 8, False)}


def oil_seal(shaft_d: float) -> SealSpec:
    for d, (D, b, ok) in _SEALS.items():
        if abs(d - shaft_d) < 1e-6:
            return SealSpec(d, D, b, ok)
    raise ValueError(f"오일실 표에 없는 축 지름 {shaft_d} (지원: {', '.join(str(k) for k in _SEALS)})")


# ── V벨트 풀리 홈 KS B 1400 ──────────────────────────────────────────
@dataclass(frozen=True)
class GrooveSpec:
    belt: str         # A B C D
    dp: float         # 호칭(피치) 지름
    alpha: float      # 홈 각도(도)
    lo: float         # 피치 폭
    w1: float         # 홈 윗폭
    k: float          # 피치선 위 깊이
    ko: float         # 피치선 아래 깊이
    e: float          # 홈 간격
    f: float          # 끝 여유

    @property
    def od(self) -> float:
        """풀리 바깥지름 = dp + 2k."""
        return self.dp + 2 * self.k

    @property
    def depth(self) -> float:
        return self.k + self.ko


# belt → [(dp 상한(초과면 다음 행), alpha, w1)], lo, k, ko, e, f
_GROOVES = {
    "A": ([(100, 34, 11.95), (125, 36, 12.12), (1e9, 38, 12.30)], 9.2, 4.5, 8.0, 15.0, 10.0),
    "B": ([(160, 34, 15.86), (200, 36, 16.07), (1e9, 38, 16.29)], 12.5, 5.5, 9.5, 19.0, 12.5),
    "C": ([(250, 34, 21.18), (315, 36, 21.45), (1e9, 38, 21.72)], 16.9, 7.0, 12.0, 25.5, 17.0),
    "D": ([(450, 36, 30.77), (1e9, 38, 31.14)], 24.6, 9.5, 15.5, 37.0, 24.0),
}


def vpulley_groove(belt: str, dp: float) -> GrooveSpec:
    belt = str(belt).strip().upper()
    if belt not in _GROOVES:
        raise ValueError(f"V벨트 형 {belt!r} 미지원 (A B C D)")
    rows, lo, k, ko, e, f = _GROOVES[belt]
    for hi, alpha, w1 in rows:
        if dp <= hi:
            return GrooveSpec(belt, dp, alpha, lo, w1, k, ko, e, f)
    raise ValueError("unreachable")


# ── 스퍼기어 공식(표준 치형, 압력각 20도) ───────────────────────────────
@dataclass(frozen=True)
class GearDims:
    m: float
    z: int
    d: float          # 피치원
    da: float         # 이끝원
    df: float         # 이뿌리원
    db: float         # 기초원
    h: float          # 전체 이 높이


def gear_dims(m: float, z: int, pressure_deg: float = 20.0) -> GearDims:
    d = m * z
    return GearDims(m, z, d, d + 2 * m, d - 2.5 * m, d * math.cos(math.radians(pressure_deg)), 2.25 * m)


def center_distance(m: float, z1: int, z2: int) -> float:
    return m * (z1 + z2) / 2.0


def gear_face_width(m: float) -> float:
    """이폭 관례 10m."""
    return 10.0 * m


# ── 커버 볼트 PCD 관례 ───────────────────────────────────────────────
def cover_bolt_pcd(bearing_D: float) -> float:
    """커버 볼트 PCD = 베어링 외경 + 15 (6204 이면 62, 조사 6.3 절 예시와 일치)."""
    return bearing_D + 15.0


def cover_bolt_size(bearing_D: float) -> str:
    return "M5" if bearing_D < 40 else ("M6" if bearing_D < 60 else "M8")


# ── 지그용 압입 드릴 부시(머리 없음) : KS B 1030 원문 미열람, DIN 179 표(J.W. Winco) 값. 보어 F7(드릴용 G6), 외경 n6 ─────
@dataclass(frozen=True)
class BushSpec:
    d1: float         # 드릴(보어) 지름
    d2: float         # 바깥지름(압입)
    lengths: tuple    # 표준 길이
    verified: bool = False

    def length_for(self, plate_t: float) -> float:
        """지그 판 두께에 맞는 표준 길이(판 두께 이상 중 최소, 없으면 최대)."""
        for L in self.lengths:
            if L >= plate_t - 1e-6:
                return L
        return self.lengths[-1]


_BUSHES = [(0, 6, 10, (10, 16, 20)), (6, 8, 12, (10, 16, 20)), (8, 10, 15, (12, 20, 25)), (10, 12, 18, (12, 20, 25)),
           (12, 15, 22, (16, 28)), (15, 18, 26, (16, 28)), (18, 20, 30, (20, 36))]


def drill_bush(drill_d: float) -> BushSpec:
    for lo, hi, d2, Ls in _BUSHES:
        if lo < drill_d <= hi:
            return BushSpec(drill_d, d2, Ls)
    raise ValueError(f"드릴 부시 표 범위 밖 지름 {drill_d} (20 이하만)")
