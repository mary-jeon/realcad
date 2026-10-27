"""프린터 빌드볼륨 분할 — 부품이 베드보다 크면 쪼개고 정렬용 다월(dowel) 구멍을 넣는다.

v1: 한도를 넘는 가장 심한 축 하나를 따라 n등분. 각 절단면에 다월 구멍 2개(관통 전 뚫어
각 조각이 반쪽씩 갖게). 별도 다월 핀을 출력해 끼우면 정렬·접착된다.
"""
from __future__ import annotations
import math
from build123d import Part, Box, Cylinder, Pos, Rot

_AX = {"X": 0, "Y": 1, "Z": 2}
BIG = 5000.0


def _bbox(part: Part):
    b = part.bounding_box()
    mn = (b.min.X, b.min.Y, b.min.Z)
    mx = (b.max.X, b.max.Y, b.max.Z)
    size = (mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2])
    ctr = ((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2)
    return mn, mx, size, ctr


def _slab(part: Part, ai: int, lo: float, hi: float) -> Part:
    dims = [2 * BIG, 2 * BIG, 2 * BIG]; dims[ai] = hi - lo
    ctr = [0.0, 0.0, 0.0]; ctr[ai] = (lo + hi) / 2
    return part & (Pos(*ctr) * Box(*dims))


def _dowel(ai: int, pos: float, c1: float, c2: float, dia: float, length: float) -> Part:
    cyl = Cylinder(radius=dia / 2, height=length)        # 기본 Z축
    if ai == 0:   cyl = Rot(0, 90, 0) * cyl; loc = (pos, c1, c2)
    elif ai == 1: cyl = Rot(90, 0, 0) * cyl; loc = (c1, pos, c2)
    else:         loc = (c1, c2, pos)
    return Pos(*loc) * cyl


def plan_split(part: Part, build_xyz: tuple[float, float, float],
               dowel_dia: float = 4.0, clearance: float = 0.4):
    """return dict(fits, axis, pieces:[Part], n, interfaces, dowel). 안 넘으면 fits=True, pieces=[part]."""
    mn, mx, size, ctr = _bbox(part)
    over = [(size[i] / build_xyz[i], i) for i in range(3)]
    ratio, ai = max(over)
    if ratio <= 1.0:
        return {"fits": True, "axis": None, "n": 1, "pieces": [part],
                "interfaces": [], "dowel": None, "size": size}

    n = math.ceil(size[ai] / build_xyz[ai])
    step = size[ai] / n
    cuts = [mn[ai] + step * k for k in range(1, n)]

    # 절단면 가로축 2개와 중심
    cross = [i for i in range(3) if i != ai]
    cc = [ctr[cross[0]], ctr[cross[1]]]
    cdim = [size[cross[0]], size[cross[1]]]
    big_c = 0 if cdim[0] >= cdim[1] else 1          # 큰 가로축에 다월 2개 벌려 배치
    off = cdim[big_c] / 4.0
    hole_len = max(dowel_dia * 4, 16.0)

    # 다월 구멍을 전체 부품에 먼저 뚫는다
    drilled = part
    for p in cuts:
        for s in (-off, off):
            c = cc[:]
            c[big_c] = cc[big_c] + s
            drilled = drilled - _dowel(ai, p, c[0], c[1], dowel_dia + clearance, hole_len)

    edges = [mn[ai]] + cuts + [mx[ai]]
    pieces = [_slab(drilled, ai, edges[k], edges[k + 1]) for k in range(n)]
    return {"fits": False, "axis": "XYZ"[ai], "n": n, "pieces": pieces,
            "interfaces": cuts, "dowel": {"dia": dowel_dia, "length": hole_len},
            "size": size}
