"""build123d 로 부품·볼트 솔리드를 만든다.

좌표 약속: 부품 윗면 = z=0. 볼트는 위에서 꽂히므로 머리는 z>0(윗면 위), 축은 z<0(재료 안).
"""
from __future__ import annotations
import math
from build123d import (
    Part, Box, Cylinder, Sphere, Pos, Rot, RegularPolygon, Circle,
    Polygon, RectangleRounded, extrude, Plane,
)
from ..fasteners.standards import Fastener


def plate(length: float, width: float, thickness: float) -> Part:
    """윗면이 z=0 인 판 (두께만큼 아래로)."""
    return Pos(0, 0, -thickness / 2) * Box(length, width, thickness)


def drill(part: Part, x: float, y: float, dia: float, depth: float) -> Part:
    """(x,y)에서 아래로 관통/맹공 구멍을 뚫는다."""
    cutter = Pos(x, y, -depth / 2 + 0.01) * Cylinder(radius=dia / 2, height=depth + 0.1)
    return part - cutter


def wall(x: float, width: float, height: float, thickness: float) -> Part:
    """판 윗면(z=0)에서 위로 선 벽. x 위치, y방향 width, z방향 height."""
    return Pos(x, 0, height / 2) * Box(thickness, width, height)


def hex_bolt_solid(f: Fastener, grip_mm: float) -> Part:
    """육각 볼트 솔리드. 머리는 z 0..head_height, 축은 -grip..0."""
    shaft = Pos(0, 0, -grip_mm / 2) * Cylinder(radius=f.nominal_dia_mm / 2, height=grip_mm)
    hexa = RegularPolygon(radius=f.head_across_corners_mm / 2, side_count=6)
    head = extrude(hexa, amount=f.head_height_mm)  # Plane.XY 기준 +Z
    return Part() + shaft + head


def place(solid: Part, x: float, y: float) -> Part:
    return Pos(x, y, 0) * solid


def build_container(cc) -> Part:
    """통/컵/박스 — 바닥 z=0, 벽+바닥 두께, 위가 열린 용기. 격자 위에 바로 앉는다."""
    ih = max(cc.height - cc.base, 1.0)
    if cc.shape == "box":
        outer = Pos(0, 0, cc.height / 2) * Box(cc.length, cc.width, cc.height)
        inner = Pos(0, 0, cc.base + ih / 2 + 0.1) * Box(
            max(cc.length - 2 * cc.wall, 1), max(cc.width - 2 * cc.wall, 1), ih + 0.2)
        part = outer - inner
        if cc.dividers and cc.dividers > 0:
            step = cc.length / (cc.dividers + 1)
            for i in range(1, cc.dividers + 1):
                part = part + Pos(-cc.length / 2 + step * i, 0, cc.base + ih / 2) * \
                    Box(cc.wall, cc.width - 2 * cc.wall, ih)
    else:
        outer = Pos(0, 0, cc.height / 2) * Cylinder(radius=cc.outer_d / 2, height=cc.height)
        inner = Pos(0, 0, cc.base + ih / 2 + 0.1) * Cylinder(
            radius=max(cc.outer_d / 2 - cc.wall, 0.5), height=ih + 0.2)
        part = outer - inner
    return part


def involute_gear_outline(z: int, m: float, pressure_deg: float = 20.0, backlash: float = 0.05,
                          n_flank: int = 8) -> list[tuple[float, float]]:
    """인벌류트 스퍼 기어 바깥 윤곽(한 바퀴, 단순 폴리곤) 점 목록.
    표준 치형: 이끝 1.0m, 이뿌리 1.25m, 압력각 20°. backlash(×m)만큼 이두께를 줄여 이론 중심거리에서 맞물린다."""
    a = math.radians(pressure_deg)
    rp = m * z / 2.0                      # 피치원
    rb = rp * math.cos(a)                 # 기초원
    ra = rp + m                           # 이끝원
    rf = max(rp - 1.25 * m, 0.3 * m)      # 이뿌리원
    inv = lambda t: math.tan(t) - t
    half_t = (math.pi * m / 2.0 - backlash * m) / 2.0 / rp     # 피치원 반 이두께 각
    theta0 = half_t + inv(a)                                     # 기초원에서 이 중심선까지 반각
    pitch = 2 * math.pi / z
    r_lo = max(rb, rf)
    t_lo = math.sqrt((r_lo / rb) ** 2 - 1.0) if r_lo > rb else 0.0
    t_hi = math.sqrt((ra / rb) ** 2 - 1.0)
    # 플랭크 (반지름, 중심선에서의 반각) — 기초/이뿌리 → 이끝
    flank = []
    for k in range(n_flank + 1):
        t = t_lo + (t_hi - t_lo) * k / n_flank
        r = rb * math.sqrt(1 + t * t)
        half = theta0 - inv(t)
        flank.append((r, max(half, 0.0)))
    if flank[-1][1] <= 1e-4:              # 이끝이 뾰족해지면(작은 잇수) 이끝원을 살짝 낮춘다
        flank = [(r, h) for r, h in flank if h > 1e-4]
    pts = []
    for i in range(z):
        c = i * pitch
        seq = []
        if rf < rb:                       # 이뿌리 → 기초원 반지름 방향(오른쪽 플랭크 아래)
            seq.append((rf, c - theta0))
        seq += [(r, c - h) for r, h in flank]                    # 오른쪽 플랭크 ↑
        tip_h = flank[-1][1]
        for k in (1, 2):                                          # 이끝 호
            seq.append((ra, c - tip_h + 2 * tip_h * k / 3))
        seq += [(r, c + h) for r, h in reversed(flank)]          # 왼쪽 플랭크 ↓
        if rf < rb:
            seq.append((rf, c + theta0))
        # 이뿌리 호: 이 이의 왼쪽 끝 → 다음 이의 오른쪽 시작
        a0, a1 = c + theta0, c + pitch - theta0
        for k in ((1, 2, 3) if z <= 120 else (2,)):
            seq.append((rf, a0 + (a1 - a0) * k / 4))
        pts += [(r * math.cos(t_), r * math.sin(t_)) for r, t_ in seq]
    return pts


def build_gear(g) -> Part:
    """인벌류트 스퍼 기어 — 윤곽 폴리곤 1개를 돌출(불리언 1회) + 축 구멍. 바닥 z=0.
    이론 중심거리 m(z1+z2)/2 에서 상대 기어와 간섭 없이 맞물린다(백래시 0.05m)."""
    z = max(int(g.teeth), 6); m = float(g.module); th = float(g.thickness)
    pts = involute_gear_outline(z, m, n_flank=(8 if z <= 60 else 5 if z <= 120 else 3))
    body = extrude(Polygon(*pts, align=None), amount=th)
    if g.bore and g.bore > 0:
        rf = max(m * z / 2 - 1.25 * m, 0.3 * m)
        bore = min(float(g.bore), 2 * rf - 2 * m)          # 보어가 이뿌리를 뚫지 않게
        if bore > 0.2:
            body = body - Pos(0, 0, th / 2) * Cylinder(radius=bore / 2, height=th + 1)
    return body


# 보드 프리셋(공개 표준 치수). holes = 보드 중심 기준 나사구멍 좌표(mm). 파이는 왼쪽 가장자리 3.5mm·간격 58×49 로 비대칭.
def _centered(l, w, holes):
    return [(round(x - l / 2, 2), round(y - w / 2, 2)) for x, y in holes]


BOARDS = {
    "raspberry_pi_4":    {"l": 85.0, "w": 56.0, "screw": "M2.5", "pilot": 2.2,
                          "holes": _centered(85.0, 56.0, [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)])},
    "raspberry_pi_5":    {"l": 85.0, "w": 56.0, "screw": "M2.5", "pilot": 2.2,
                          "holes": _centered(85.0, 56.0, [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)])},
    "raspberry_pi_3b":   {"l": 85.0, "w": 56.0, "screw": "M2.5", "pilot": 2.2,
                          "holes": _centered(85.0, 56.0, [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)])},
    "raspberry_pi_zero": {"l": 65.0, "w": 30.0, "screw": "M2.5", "pilot": 2.2,
                          "holes": _centered(65.0, 30.0, [(3.5, 3.5), (61.5, 3.5), (3.5, 26.5), (61.5, 26.5)])},
    "arduino_uno":       {"l": 68.6, "w": 53.3, "screw": "M3", "pilot": 2.6,
                          "holes": _centered(68.6, 53.3, [(13.97, 2.54), (15.24, 50.8), (66.04, 7.62), (66.04, 35.56)])},
}
for _b in BOARDS.values():   # 하위호환: dx·dy = 구멍 패턴 외접 크기
    _xs = [h[0] for h in _b["holes"]]; _ys = [h[1] for h in _b["holes"]]
    _b["dx"] = round(max(_xs) - min(_xs), 2); _b["dy"] = round(max(_ys) - min(_ys), 2)


class UnknownBoard(ValueError):
    pass


def board_spec(name: str, e=None) -> dict:
    """프리셋 보드 또는 board="custom"(계약의 board_l/board_w/board_holes 로 정의)."""
    if name == "custom" and e is not None and e.board_l > 0 and e.board_w > 0:
        from ..fasteners.standards import resolve, insert_spec
        f = resolve(e.board_screw)[0]
        pilot = round(f.nominal_dia_mm - 1.0825 * f.pitch_mm, 2)      # 셀프탭/탭용 파일럿
        return {"l": e.board_l, "w": e.board_w, "screw": f.name, "pilot": pilot,
                "holes": _centered(e.board_l, e.board_w, [tuple(h) for h in e.board_holes]),
                "dx": 0.0, "dy": 0.0}
    if name not in BOARDS:
        raise UnknownBoard(f"미지원 보드 {name!r}. 지원: {', '.join(BOARDS)} 또는 custom(board_l, board_w, board_holes)")
    return BOARDS[name]


def build_enclosure(e) -> Part:
    """기판 케이스: 외함 + 보드 고정 기둥(나사 파일럿홀) + 포트 쪽 열림. 바닥 z=0."""
    b = board_spec(e.board, e)
    bl, bw = b["l"], b["w"]
    inner_l, inner_w = bl + 2 * e.clearance, bw + 2 * e.clearance
    outer_l, outer_w = inner_l + 2 * e.wall, inner_w + 2 * e.wall
    total_h = e.base + e.standoff_h + e.inner_h

    outer = Pos(0, 0, total_h / 2) * Box(outer_l, outer_w, total_h)
    cav_h = total_h - e.base
    inner = Pos(0, 0, e.base + cav_h / 2 + 0.1) * Box(inner_l, inner_w, cav_h + 0.2)
    part = outer - inner

    so_top = e.base + e.standoff_h
    pilot_depth = max(min(6.0, so_top - 1.2), 1.0)      # 기둥 꼭대기에서 아래로, 바닥 피막 ≥ 1.2 mm 보장
    for sx, sy in b["holes"]:
        part = part + Pos(sx, sy, so_top / 2) * Cylinder(radius=3.0, height=so_top)
        part = part - Pos(sx, sy, so_top - pilot_depth / 2 + 0.05) * Cylinder(radius=b["pilot"] / 2, height=pilot_depth + 0.1)

    if e.open_ports:                       # 긴 벽(±y) 포트 쪽 열기
        oh = total_h - (so_top + 2)
        for sign in (-1, 1):
            part = part - Pos(0, sign * outer_w / 2, (so_top + 2) + oh / 2) * \
                Box(bl - 6, e.wall * 4, oh)
    return part


def build_wrap_case(l: float, w: float, h: float,
                    clearance: float = 2.0, wall: float = 2.0,
                    base: float = 2.0, top_gap: float = 5.0,
                    mounts=None, standoff_h: float = 0.0, pilot: float = 2.2) -> Part:
    """외부참조 바운딩박스 l×w×h 를 감싸는 케이스. 바닥 z=0.
    mounts=[(x,y),...] 가 있으면 그 위치에 기둥(standoff)+나사 파일럿홀을 세워 보드를 조립한다."""
    lift = standoff_h if (mounts and standoff_h > 0) else 0.0
    inner_l, inner_w = l + 2 * clearance, w + 2 * clearance
    inner_h = lift + h + top_gap
    total_h = base + inner_h
    outer = Pos(0, 0, total_h / 2) * Box(inner_l + 2 * wall, inner_w + 2 * wall, total_h)
    inner = Pos(0, 0, base + inner_h / 2 + 0.1) * Box(inner_l, inner_w, inner_h + 0.2)
    part = outer - inner
    if mounts and standoff_h > 0:
        for (mx, my) in mounts:
            part = part + Pos(mx, my, base + standoff_h / 2) * Cylinder(radius=3.0, height=standoff_h)
            part = part - Pos(mx, my, base + standoff_h - 3 + 0.1) * Cylinder(radius=pilot / 2, height=6)
    return part


def pi_port_cuts(holes_rel, size, base, lift, h, clearance, wall):
    """감지한 나사구멍으로 파이4 보드 방향을 잡고, 각 커넥터(USB×2스택·랜·HDMI×2·USB-C·오디오·SD)
    개별 구멍을 '플러그 여유'까지 더해 계산. 반환: [(cx,cy,cz,sx,sy,sz), ...] (케이스 프레임).
    보드 좌표는 커뮤니티 근사값(±1~2mm)."""
    inner_l, inner_w = size[0] + 2 * clearance, size[1] + 2 * clearance
    outer_l, outer_w = inner_l + 2 * wall, inner_w + 2 * wall
    hx = sorted(set(round(p[0], 1) for p in holes_rel))
    hy = sorted(set(round(p[1], 1) for p in holes_rel))
    if len(hx) < 2 or len(hy) < 2:
        return []
    hx0, hx1, hy0, hy1 = hx[0], hx[-1], hy[0], hy[-1]
    bz = base + lift
    usb_plus_x = (size[0] / 2 - hx1) > (hx0 + size[0] / 2)       # USB/랜이 +x?
    hdmi_minus_y = (hy0 + size[1] / 2) > (size[1] / 2 - hy1)      # 전원/HDMI가 -y?

    def bx2cx(bx):   # 보드 x(3.5=첫 구멍) → 케이스 x
        return (bx + (hx0 - 3.5)) if usb_plus_x else ((hx1 + 3.5) - bx)

    def by2cy(by):
        return (by + (hy0 - 3.5)) if hdmi_minus_y else ((hy1 + 3.5) - by)

    t = wall * 4
    xw = (outer_l / 2) if usb_plus_x else (-outer_l / 2)          # USB/랜 벽
    sdw = -xw                                                     # SD 벽
    yw = (-outer_w / 2) if hdmi_minus_y else (outer_w / 2)        # 전원/HDMI 벽
    cuts = []
    # USB/Ethernet 짧은 끝면 — (보드 y, 개구폭(+여유), z하한, z상한)
    for by, ww, z0, z1 in [(9.0, 16, 2, 17), (27.0, 16, 2, 17), (45.75, 17, 2, 15.5)]:
        cuts.append((xw, by2cy(by), bz + (z0 + z1) / 2, t, ww, z1 - z0))
    # 전원/HDMI/오디오 긴 변 — (보드 x, 개구폭(+여유), z하한, z상한)
    for bx, ww, z0, z1 in [(11.2, 11, 1.5, 6), (26.0, 9, 1.5, 6), (39.5, 9, 1.5, 6), (53.5, 8, 1.5, 8)]:
        cuts.append((bx2cx(bx), yw, bz + (z0 + z1) / 2, ww, t, z1 - z0))
    # SD카드 반대 짧은 끝면
    cuts.append((sdw, by2cy(28.0), bz + 1.5, t, 15, 4))
    return cuts


def build_case_with_lid(l, w, h, clearance=2.5, wall=2.5, base=2.5,
                        standoff_h=4.0, mounts=None, lid_t=3.0,
                        gasket=True, screw="M3", ports=False, port_cuts=None):
    """밀폐형 케이스(바디+뚜껑). 바디: 벽 막힘 + 보드 기둥 + 모서리 나사보스 + 가스켓 홈.
    뚜껑: 모서리 나사 관통홀 + 안쪽 립. return (body, lid).  (방수/IP 지향)"""
    pilot = {"M2.5": 2.1, "M3": 2.5}.get(screw, 2.5)
    clear = {"M2.5": 2.8, "M3": 3.4}.get(screw, 3.4)
    inner_l, inner_w = l + 2 * clearance, w + 2 * clearance
    outer_l, outer_w = inner_l + 2 * wall, inner_w + 2 * wall
    lift = standoff_h if (mounts and standoff_h > 0) else 0.0
    inner_h = lift + h + 4.0
    total_h = base + inner_h

    outer = Pos(0, 0, total_h / 2) * Box(outer_l, outer_w, total_h)
    inner = Pos(0, 0, base + inner_h / 2 + 0.1) * Box(inner_l, inner_w, inner_h + 0.2)
    body = outer - inner

    if mounts and standoff_h > 0:                       # 보드 고정 기둥
        for (mx, my) in mounts:
            body = body + Pos(mx, my, base + standoff_h / 2) * Cylinder(radius=3.0, height=standoff_h)
            body = body - Pos(mx, my, base + standoff_h - 3 + 0.1) * Cylinder(radius=pilot / 2, height=6)

    br = 3.5
    corners = [(sx * (outer_l / 2 - br), sy * (outer_w / 2 - br)) for sx in (-1, 1) for sy in (-1, 1)]
    for (cx, cy) in corners:                            # 모서리 나사 보스(벽 모서리)
        body = body + Pos(cx, cy, total_h / 2) * Cylinder(radius=br, height=total_h)
        body = body - Pos(cx, cy, total_h - 12 / 2 + 0.1) * Cylinder(radius=pilot / 2, height=12)

    if port_cuts:                                       # 면별 포트 묶음 컷(파이 포트맵)
        for (cx, cy, cz, sx, sy, sz) in port_cuts:
            body = body - Pos(cx, cy, cz) * Box(sx, sy, sz)
    elif ports:                                         # 범용: 긴 벽에 커넥터 높이만큼
        board_bottom = base + lift
        oz0, oz1 = board_bottom + 1.5, board_bottom + h - 1.0
        ow = max(l - 10, 5)
        for sign in (-1, 1):
            body = body - Pos(0, sign * outer_w / 2, (oz0 + oz1) / 2) * \
                Box(ow, wall * 4, max(oz1 - oz0, 2))

    if gasket:                                          # 윗면 가스켓 홈(링)
        gw, gd = 1.6, 1.5
        cl, cw = (inner_l + outer_l) / 2, (inner_w + outer_w) / 2
        ring_o = Pos(0, 0, total_h - gd / 2 + 0.1) * Box(cl + gw, cw + gw, gd + 0.2)
        ring_i = Pos(0, 0, total_h - gd / 2 + 0.1) * Box(cl - gw, cw - gw, gd + 0.3)
        body = body - (ring_o - ring_i)

    lid_z = total_h + 6 + lid_t / 2                     # 조립뷰: 뚜껑을 위로 띄움
    lid = Pos(0, 0, lid_z) * Box(outer_l, outer_w, lid_t)
    for (cx, cy) in corners:
        lid = lid - Pos(cx, cy, lid_z) * Cylinder(radius=clear / 2, height=lid_t + 1)
    lid = lid + Pos(0, 0, lid_z - lid_t / 2 - 1.2) * Box(inner_l - 0.6, inner_w - 0.6, 2.4)  # 안쪽 립
    return body, lid


def build_profile(p) -> Part:
    """평면 윤곽 → 두께만큼 돌출. 바닥 z=0, 위로 thickness. watertight 단일 솔리드."""
    r = max(p.outer_d / 2.0, 0.5)
    th = max(p.thickness, 0.1)
    shape = (p.shape or "asterisk").lower()
    if shape == "disc":
        sk = Circle(radius=r)
    elif shape == "polygon":
        sk = RegularPolygon(radius=r, side_count=max(int(p.points or 6), 3))
    elif shape == "rounded_rect":
        cr = p.corner_radius if p.corner_radius and p.corner_radius > 0 else p.outer_d * 0.1
        cr = max(min(cr, r - 0.01), 0.1)
        sk = RectangleRounded(p.outer_d, p.outer_d, cr)
    elif shape == "star":
        n = max(int(p.points or 6), 3)
        inner = r * 0.45
        pts = []
        for i in range(2 * n):
            rad = r if i % 2 == 0 else inner
            a = math.pi * i / n
            pts.append((rad * math.cos(a), rad * math.sin(a)))
        sk = Polygon(*pts)
    else:  # asterisk — 중심에서 방사형으로 뻗은 둥근 막대 n개의 합집합(스픽 로고형)
        n = max(int(p.arms or 6), 2)
        aw = p.arm_width if p.arm_width and p.arm_width > 0 else p.outer_d * 0.12
        aw = max(aw, 1.0)
        sk = Circle(radius=aw * 0.6)                      # 중심 허브(연결 보장)
        for i in range(n):
            arm = Pos(r / 2, 0) * RectangleRounded(r, aw, aw / 2 * 0.99)
            sk = sk + Rot(0, 0, 360.0 * i / n) * arm
    return extrude(sk, amount=th)


def _wedge_cutter(radius: float, height: float, deg: float) -> Part:
    """+x 축을 중심으로 deg 만큼 벌어진 파이형 쐐기(C클립 입을 자른다). z 0..height 관통."""
    half = math.radians(deg) / 2.0
    steps = max(4, int(deg / 8))
    pts = [(0.0, 0.0)]
    for i in range(steps + 1):
        a = -half + (2 * half) * i / steps
        pts.append((radius * math.cos(a), radius * math.sin(a)))
    return Pos(0, 0, -0.1) * extrude(Polygon(*pts), amount=height + 0.2)


def build_clamp(c) -> Part:
    """봉을 무는 C자 클립 + 선택적 부착물. 바닥 z=0. 입은 +x 로 벌어짐."""
    ri = c.rod_d / 2.0 + max(c.clearance, 0.0)
    R = ri + max(c.wall, 0.8)
    h = max(c.height, 1.0)
    part = Pos(0, 0, h / 2) * Cylinder(radius=R, height=h) \
        - Pos(0, 0, h / 2) * Cylinder(radius=ri, height=h + 1)
    if c.gap_deg and c.gap_deg > 0:
        part = part - _wedge_cutter(R + 2, h, min(c.gap_deg, 300))
    if c.attach == "pocket":
        pw, pd, ph, w = max(c.pocket_w, 2), max(c.pocket_d, 2), max(c.pocket_h, 2), max(c.wall, 1.2)
        cx = -(R - 2.0) - pd / 2.0                        # 입 반대쪽(-x)에 2mm 겹쳐 접합
        part = part + Pos(cx, 0, ph / 2) * Box(pd, pw, ph)
        part = part - Pos(cx, 0, w + ph / 2 + 0.1) * \
            Box(max(pd - 2 * w, 1), max(pw - 2 * w, 1), ph)   # 위가 열린 주머니
    elif c.attach == "plate":
        tl, tw, tt = max(c.tab_l, 2), max(c.tab_w, 2), max(c.tab_t, 0.8)
        cx = -(R - 2.0) - tl / 2.0
        part = part + Pos(cx, 0, tt / 2) * Box(tl, tw, tt)
    return part


def build_ball(b) -> Part:
    """속 빈 구 쉘(달 조명) + 바닥 소켓 구멍. 바닥극 z=0 에 앉힘. watertight."""
    R = max(b.outer_d / 2.0, 1.0)
    inner_r = max(R - max(b.wall, 0.4), 0.5)
    shell = Sphere(radius=R) - Sphere(radius=inner_r)
    if b.socket_d and b.socket_d > 0:
        sh = b.socket_h if (b.socket_h and b.socket_h > 0) else (max(b.wall, 0.4) + 3)
        shell = shell - Pos(0, 0, -R + sh / 2 - 0.1) * \
            Cylinder(radius=b.socket_d / 2.0, height=sh)
    return Pos(0, 0, R) * shell                           # 바닥극을 z=0 으로


def build_from_contract(c):
    """DesignContract → (Part, Fastener|None, hole_dia|None). kind로 분기."""
    if c.kind == "container":
        return build_container(c.container), None, None
    if c.kind == "gear":
        return build_gear(c.gear), None, None
    if c.kind == "enclosure":
        return build_enclosure(c.enclosure), None, None
    if c.kind == "profile":
        return build_profile(c.profile), None, None
    if c.kind == "clamp":
        return build_clamp(c.clamp), None, None
    if c.kind == "ball":
        return build_ball(c.ball), None, None
    from ..fasteners.standards import resolve
    f, exact, note = resolve(c.fastener)
    c.fastener_exact, c.fastener_note = exact, note      # 파이프라인이 F0 로 보고
    part = plate(c.plate.length, c.plate.width, c.plate.thickness)
    if c.wall is not None:
        part = part + wall(c.wall.x, c.plate.width, c.wall.height, c.wall.thickness)
    ht = getattr(c, "hole_type", "through")
    if ht == "tapped":
        # 탭 구멍: 탭 드릴 ≈ D − 1.0825·p (75% 체결). 나사산은 모델링하지 않고 H3 로 깊이만 검증
        dia = float(c.hole_dia) if getattr(c, "hole_dia", None) else round(f.nominal_dia_mm - 1.0825 * f.pitch_mm, 2)
    elif ht == "insert":
        from ..fasteners.standards import insert_spec
        spec = insert_spec(f)
        dia = float(c.hole_dia) if getattr(c, "hole_dia", None) else (spec[0] if spec else f.clearance(c.fit))
    else:
        dia = float(c.hole_dia) if getattr(c, "hole_dia", None) else f.clearance(c.fit)
    style = getattr(c, "hole_style", "plain")
    comp = float(getattr(c, "hole_comp", 0.0) or 0.0)
    if ht != "tapped" and comp > 0 and not getattr(c, "hole_dia", None):   # 자동 사이징 구멍에만 FDM 수축 보정(명시 지름은 그대로)
        dia = round(dia + comp, 2)
    for h in c.holes:
        if ht == "insert":
            # 인서트 구멍은 맹공(바닥 1 mm 남김) + 인서트 길이 + 1 mm 여유, 판이 얇으면 관통
            from ..fasteners.standards import insert_spec
            spec = insert_spec(f); L = (spec[1] + 1.0) if spec else c.plate.thickness
            depth = min(L, c.plate.thickness - 1.0) if c.plate.thickness - 1.0 > 1.0 else c.plate.thickness
            if depth >= c.plate.thickness - 1e-6:
                part = drill(part, h.x, h.y, dia, c.plate.thickness)
            else:
                part = part - Pos(h.x, h.y, -depth / 2 + 0.01) * Cylinder(radius=dia / 2, height=depth + 0.02)
        else:
            part = drill(part, h.x, h.y, dia, c.plate.thickness)
        if style == "counterbore":
            part = part - counterbore_cutter(f, h.x, h.y)
        elif style == "countersink":
            part = part - countersink_cutter(f, h.x, h.y)
    return part, f, dia


def counterbore_cutter(f: Fastener, x: float, y: float) -> Part:
    """카운터보어: 지름 = 머리 맞모거리 + 1.0 mm, 깊이 = 머리 높이(머리 윗면이 판면과 같아짐)."""
    d = f.head_across_corners_mm + 1.0
    depth = f.head_height_mm
    return Pos(x, y, -depth / 2 + 0.01) * Cylinder(radius=d / 2, height=depth + 0.02)


def countersink_cutter(f: Fastener, x: float, y: float) -> Part:
    """카운터싱크(접시머리): 입구 지름 ≈ 2.0×D, 각도 90°(미터)/82°(인치). 원뿔 커터."""
    from build123d import Cone
    top_d = 2.0 * f.nominal_dia_mm
    ang = 90.0 if f.is_metric else 82.0
    depth = (top_d / 2.0) / math.tan(math.radians(ang / 2.0))
    # Cone(bottom_radius, top_radius, height) 는 바닥이 -h/2, 위가 +h/2 → 위를 판면(z=0)에 맞춘다
    return Pos(x, y, -depth / 2 + 0.01) * Cone(bottom_radius=0.01, top_radius=top_d / 2, height=depth + 0.02)
