"""Machine element standards tables: parallel keys, deep groove ball bearings, C-type retaining rings, oil seals, V-belt pulley grooves, spur gear formulas.

Sources:
- Parallel keys: KS B 1311 (equivalent to JIS B 1301). Cross-checked with Miki Pulley tables and PAES 304:2000.
- Bearings: KS B 2023 (ISO 15 dimension series). 6203/6204/6205 from the NSK catalog, the rest ISO 15 standard dimensions.
- Retaining rings (C-type, for shafts): KS B 1336 (JIS B 2804). Misumi FC-32 PDF, Miki Pulley.
- Oil seals: KS B 2804 (JIS B 2402-1). 20x35x7 confirmed on SKF/DDS product pages, others are common catalog combinations.
- V-pulley grooves: KS B 1400 (equivalent to JIS B 1854-1987). Misumi (NBK) tables.
- Gears: KHK technical data, standard tooth profile (20 degree pressure angle, addendum 1.0m, dedendum 1.25m).

Rows with `verified` True were confirmed against primary sources; False rows are standard dimension series values (recheck recommended).
"""
from __future__ import annotations
from dataclasses import dataclass
import math


# ── Parallel keys KS B 1311 ─────────────────────────────────────────
@dataclass(frozen=True)
class KeySpec:
    b: float          # Key width
    h: float          # Key height
    t1: float         # Shaft keyway depth
    t2: float         # Hub keyway depth
    d_min: float      # Applicable shaft diameter (over)
    d_max: float      # Applicable shaft diameter (up to)
    verified: bool = True

    @property
    def name(self) -> str:
        return f"{self.b:g}x{self.h:g}"

    @property
    def top_clearance(self) -> float:
        """Gap between key top and hub keyway bottom = t1 + t2 - h (0.3 for 6x6)."""
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
    """Shaft diameter → parallel key spec. ValueError if out of range."""
    for lo, hi, b, h, t1, t2, ok in _KEYS:
        if lo < shaft_d <= hi:
            return KeySpec(b, h, t1, t2, lo, hi, ok)
    raise ValueError(f"평행키 표 범위 밖 축 지름 {shaft_d} (6 초과 75 이하만)")


# ── Deep groove ball bearings KS B 2023 / ISO 15 ───────────────
@dataclass(frozen=True)
class BearingSpec:
    code: str
    d: float          # Bore
    D: float          # Outer diameter
    B: float          # Width
    r: float          # Minimum chamfer
    da_min: float     # Minimum shaft shoulder diameter (contacts only the inner ring face)
    da_max: float     # Maximum shaft shoulder diameter
    Da_max: float     # Maximum housing shoulder diameter (contacts only the outer ring face)
    verified: bool = False

    @property
    def ball_d(self) -> float:
        """Ball diameter for the simplified model (60% of section height)."""
        return round(0.6 * (self.D - self.d) / 2.0, 2)

    @property
    def pitch_d(self) -> float:
        return (self.d + self.D) / 2.0


def _bearing(code, d, D, B, r, da=None, Da=None, verified=False):
    # Shoulder diameter fallback: shaft shoulder d+5 to d+0.25(D-d), housing shoulder D-5 (approximation that matches NSK values for 6204/6205)
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
    """Pick a bearing by shaft diameter (bore), 6200 series by default."""
    for b in BEARINGS.values():
        if b.code.startswith(series) and abs(b.d - d) < 1e-6:
            return b
    raise ValueError(f"내경 {d} 의 {series}xx 베어링 없음")


# ── C-type retaining rings (for shafts) KS B 1336 ──────────────
@dataclass(frozen=True)
class RingSpec:
    d1: float         # Nominal size (shaft diameter)
    d3: float         # Ring inner diameter (free state)
    t: float          # Thickness
    b: float          # Ring width (max section)
    d2: float         # Groove diameter
    m: float          # Groove width
    n: float          # Minimum distance from groove to shaft end
    verified: bool = True

    @property
    def groove_depth(self) -> float:
        return round((self.d1 - self.d2) / 2.0, 3)

    @property
    def od(self) -> float:
        """Approximate installed outer diameter d4 = d3 + 1.45 b."""
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


# ── Oil seals KS B 2804 (d x D x b) ────────────────────────────────
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


# ── V-belt pulley grooves KS B 1400 ─────────────────────────────
@dataclass(frozen=True)
class GrooveSpec:
    belt: str         # A B C D
    dp: float         # Nominal (pitch) diameter
    alpha: float      # Groove angle (degrees)
    lo: float         # Pitch width
    w1: float         # Groove top width
    k: float          # Depth above pitch line
    ko: float         # Depth below pitch line
    e: float          # Groove pitch
    f: float          # Edge margin

    @property
    def od(self) -> float:
        """Pulley outer diameter = dp + 2k."""
        return self.dp + 2 * self.k

    @property
    def depth(self) -> float:
        return self.k + self.ko


# belt → [(dp upper limit (next row if exceeded), alpha, w1)], lo, k, ko, e, f
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


# ── Spur gear formulas (standard profile, 20 degree pressure angle) ───
@dataclass(frozen=True)
class GearDims:
    m: float
    z: int
    d: float          # Pitch circle
    da: float         # Tip circle
    df: float         # Root circle
    db: float         # Base circle
    h: float          # Total tooth depth


def gear_dims(m: float, z: int, pressure_deg: float = 20.0) -> GearDims:
    d = m * z
    return GearDims(m, z, d, d + 2 * m, d - 2.5 * m, d * math.cos(math.radians(pressure_deg)), 2.25 * m)


def center_distance(m: float, z1: int, z2: int) -> float:
    return m * (z1 + z2) / 2.0


def gear_face_width(m: float) -> float:
    """Face width by convention: 10m."""
    return 10.0 * m


# ── Cover bolt PCD convention ──────────────────────────────────
def cover_bolt_pcd(bearing_D: float) -> float:
    """Cover bolt PCD = bearing OD + 15 (62 for 6204)."""
    return bearing_D + 15.0


def cover_bolt_size(bearing_D: float) -> str:
    return "M5" if bearing_D < 40 else ("M6" if bearing_D < 60 else "M8")


# ── Headless press-fit drill bushings for jigs: DIN 179 table (J.W. Winco) values (KS B 1030 original not checked). Bore F7 (G6 for drills), OD n6 ─────
@dataclass(frozen=True)
class BushSpec:
    d1: float         # Drill (bore) diameter
    d2: float         # Outer diameter (press fit)
    lengths: tuple    # Standard length
    verified: bool = False

    def length_for(self, plate_t: float) -> float:
        """Standard length for a jig plate thickness (shortest one ≥ the plate thickness, else the longest)."""
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
