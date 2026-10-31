"""캠 클램프(스트랩 클램프) 조립 빌더(preset cam_clamp) : CAD 실기 과제 6.

근거: 01_리서치/CAD실기과제_4종_조사_20261031.md §4 (153LAB 2023년 4회 기능사 3일차 스트랩 클램프: 본체, 누름판, V블록 90도,
축, 캠 손잡이, 스프링, 원통 공작물. 축 끼워맞춤 g6/h6).
구조: 본체(바닥판 + 기둥 2)의 축(핀, Y 방향)에 캠 손잡이가 끼워져 돈다. 누름판(스트랩)은 세로 장공으로 축을 지나며 위아래로만 움직이고,
캠 바깥 원이 누름판 윗면을 눌러 내린다. 누름판 앞끝이 V블록 위 원통 공작물을 누르고, 뒤끝은 스프링이 받친다.
기구학: 편심 원 캠 반지름 Rc, 편심 e. 각도 θ 에서 캠 바닥까지 거리 = Rc - e cosθ (θ=0 풀림, θ=180 잠김). 행정 = 2e.
"""
from __future__ import annotations
import math

from build123d import Part, Compound, Box, Cylinder, Sphere, Pos, Rot, Polygon, extrude, Plane

from . import standards as S
from .power_train import PartInfo, Assembly, cyl_x, ring_x, retaining_ring_solid, fit

BASE_T = 15.0
BASE_L = 170.0
BASE_W = 90.0
UPR_T = 12.0           # 기둥 두께(Y)
STRAP_W = 25.0         # 누름판 폭(Y)
STRAP_T = 12.0         # 누름판 두께
STRAP_L = 120.0        # 누름판 길이(X): 뒤끝 -50, 앞끝 +70
PIN_D = 10.0
CAM_R = 20.0           # 캠 바깥 원 반지름
CAM_T = 14.0           # 캠 두께(Y)
LEVER_D = 10.0
LEVER_L = 110.0
X_V = 50.0             # V블록 중심 x
X_SPRING = -40.0
SPRING_D = 14.0


def layout_cam_clamp(a) -> dict:
    wd, e = float(a.work_d), float(a.cam_lift)
    r = wd / 2.0
    vw = round(max(wd * 0.9, 20.0), 1)                  # V 입구 폭(90도 V: 깊이 = vw/2)
    v_h = 30.0                                          # V블록 높이
    v_len = STRAP_W + 2 * 12.0                          # V블록 길이(Y)
    z_vtop = BASE_T + v_h
    z_apex = z_vtop - vw / 2.0                          # V 꼭짓점 높이
    z_wc = z_apex + r * math.sqrt(2.0)                  # 90도 V 에 놓인 원통 중심
    z_wtop = z_wc + r                                   # 공작물 윗면 = 잠김 때 누름판 바닥
    z_pin = z_wtop + STRAP_T + CAM_R + e                # θ=180: 캠 바닥 = Rc + e 아래 → 누름판 윗면
    y_upr = STRAP_W / 2.0 + 1.0 + UPR_T / 2.0           # 기둥 중심 y(누름판 양옆 1 mm 틈)
    ring = S.retaining_ring(PIN_D)
    pin_len = 2 * (y_upr + UPR_T / 2.0) + 2 * (ring.m + 1.5)
    return dict(wd=wd, r=r, e=e, vw=vw, v_h=v_h, v_len=v_len, z_vtop=z_vtop, z_apex=z_apex, z_wc=z_wc, z_wtop=z_wtop,
                z_pin=z_pin, y_upr=y_upr, ring=ring, pin_len=pin_len, stroke=2 * e,
                upr_h=z_pin + CAM_R + e + 8.0 - BASE_T, motion_steps=[0, 45, 90, 135, 180], motion_label="도(캠 각도, 180 = 잠김)")


def strap_z_top(L: dict, theta_deg: float) -> float:
    """각도 θ 에서 누름판 윗면 높이 = 핀 중심 - (Rc - e cosθ)."""
    return L["z_pin"] - (CAM_R - L["e"] * math.cos(math.radians(theta_deg)))


def _body(L: dict) -> Part:
    base = Pos(10.0, 0, BASE_T / 2.0) * Box(BASE_L, BASE_W, BASE_T)
    body = base
    for sy in (-1, 1):
        body = body + Pos(0, sy * L["y_upr"], BASE_T + L["upr_h"] / 2.0) * Box(30.0, UPR_T, L["upr_h"])
        body = body + Pos(0, sy * L["y_upr"], BASE_T + L["upr_h"]) * Rot(90, 0, 0) * Cylinder(radius=15.0, height=UPR_T)   # 둥근 머리
    body = body - Pos(0, 0, L["z_pin"]) * Rot(90, 0, 0) * Cylinder(radius=PIN_D / 2.0, height=BASE_W + 2)                 # 축 구멍 H7
    for sx in (-60.0, 80.0):                                                                                              # 테이블 고정 장공 대신 구멍 4
        for sy in (-1, 1):
            body = body - Pos(sx, sy * (BASE_W / 2.0 - 10.0), BASE_T / 2.0) * Cylinder(radius=5.5, height=BASE_T + 2)
    body = body - Pos(X_SPRING, 0, BASE_T) * Cylinder(radius=SPRING_D / 2.0 + 0.5, height=6.0)                           # 스프링 자리(깊이 3)
    for sy in (-1, 1):                                                                                                    # V블록 고정 볼트 구멍(아래에서)
        body = body - Pos(X_V, sy * 14.0, BASE_T / 2.0) * Cylinder(radius=3.3, height=BASE_T + 2)
    return body


def _vblock(L: dict) -> Part:
    vw, vh = L["vw"], L["v_h"]
    blk = Pos(X_V, 0, BASE_T + vh / 2.0) * Box(vw + 20.0, L["v_len"], vh)
    # 90도 V 홈(Y 방향으로 관통): 단면 삼각형(꼭짓점 z_apex, 입구 폭 vw 윗면)
    tri = Polygon((X_V - vw / 2.0 - 1.0, L["z_vtop"] + 1.0), (X_V + vw / 2.0 + 1.0, L["z_vtop"] + 1.0), (X_V, L["z_apex"] - 1.0), align=None)
    cut = extrude(Plane.XZ * tri, amount=L["v_len"] / 2.0 + 1.0, both=True)
    blk = blk - cut
    for sy in (-1, 1):
        blk = blk - Pos(X_V, sy * 14.0, BASE_T + 6.0) * Cylinder(radius=3.0, height=14.0)                                   # M6 탭(아래에서 볼트)
    return blk


def _strap(L: dict) -> Part:
    """누름판(풀림 θ=0 기준 위치). 세로 장공: 폭 = 핀 Ø, 높이 = 핀 Ø + 2e + 1."""
    zt = strap_z_top(L, 0.0)
    s = Pos((70.0 + (-50.0)) / 2.0, 0, zt - STRAP_T / 2.0) * Box(STRAP_L, STRAP_W, STRAP_T)
    slot_h = PIN_D + 2 * L["e"] + 1.0
    zc = L["z_pin"] - L["e"] - 0.5 + 0.0            # 풀림 때 핀은 장공 위쪽, 잠김 때 아래쪽
    s = s - Pos(0, 0, zc) * Box(PIN_D, STRAP_W + 2, slot_h)
    return s


def _cam(L: dict) -> Part:
    """캠 손잡이(θ=0 기준: 편심이 +Z 쪽, 캠 바닥까지 Rc - e). 축 = 핀(Y), 회전 중심 = 핀."""
    e = L["e"]
    disc = Pos(0, 0, e) * Rot(90, 0, 0) * Cylinder(radius=CAM_R, height=CAM_T)          # 편심 원(중심이 핀보다 e 위)
    hub = Rot(90, 0, 0) * Cylinder(radius=PIN_D / 2.0 + 5.0, height=CAM_T)
    lever = Pos(-(CAM_R / 2.0 + LEVER_L / 2.0), 0, 0) * Rot(0, 90, 0) * Cylinder(radius=LEVER_D / 2.0, height=LEVER_L)   # 풀림(θ=0): 레버가 -X 로 수평, 잠김(180): +X
    ball = Pos(-(CAM_R / 2.0 + LEVER_L), 0, 0) * Sphere(radius=9.0)
    cam = disc + hub + lever + ball
    cam = cam - Rot(90, 0, 0) * Cylinder(radius=PIN_D / 2.0, height=CAM_T + 2)                                           # 핀 구멍
    return Pos(0, 0, L["z_pin"]) * cam


def place_cam(L: dict, theta_deg: float, local_at_pin: Part) -> Part:
    return Pos(0, 0, L["z_pin"]) * Rot(0, theta_deg, 0) * Pos(0, 0, -L["z_pin"]) * local_at_pin   # +θ: 레버 -X → +Z(90) → +X(180), 편심 +Z → -Z


def _spring(L: dict, theta_deg: float) -> Part:
    z0 = BASE_T + 3.0                                  # 자리 바닥
    z1 = strap_z_top(L, theta_deg) - STRAP_T           # 누름판 바닥
    return Pos(X_SPRING, 0, (z0 + z1) / 2.0) * (Cylinder(radius=SPRING_D / 2.0, height=z1 - z0) - Cylinder(radius=SPRING_D / 2.0 - 2.0, height=z1 - z0 + 2))


def build_cam_clamp(a) -> Assembly:
    L = layout_cam_clamp(a)
    e, r = L["e"], L["r"]
    parts: list[PartInfo] = []
    no = [0]

    def add(name, solid, spec="", qty=1, material="", explode=(0, 0, 0), group=""):
        no[0] += 1
        parts.append(PartInfo(name, solid, spec, qty, material, explode, group or name.split()[0], no[0]))

    add("본체", _body(L), f"바닥판 {BASE_L:g}×{BASE_W:g}×{BASE_T:g}, 기둥 2 (축 구멍 Ø{PIN_D:g} H7), 스프링 자리, V블록 볼트 구멍", 1, "GC200", (0, 0, -1.0))
    add("V블록", _vblock(L), f"90도 V, 입구 폭 {L['vw']:g}, 높이 {L['v_h']:g}, 공작물 Ø{L['wd']:g} 중심 높이 {L['z_wc']:.1f}", 1, "SM45C", (0, 0, 0.8), "스페이서")
    work = Pos(X_V, 0, L["z_wc"]) * Rot(90, 0, 0) * Cylinder(radius=r, height=L["v_len"] + 30.0)
    add("공작물(참조)", work, f"원통 Ø{L['wd']:g} (V블록 위, 누름판이 윗면 접촉)", 1, "", (0, 0, 0), "기어")
    strap0 = _strap(L)
    add("누름판", strap0, f"{STRAP_L:g}×{STRAP_W:g}×{STRAP_T:g}, 세로 장공 {PIN_D:g}×{PIN_D + 2 * e + 1:g}, 행정 {2 * e:g}", 1, "SM45C", (0, 0, 1.5), "커버")
    pin = Pos(0, 0, L["z_pin"]) * Rot(90, 0, 0) * Cylinder(radius=PIN_D / 2.0, height=L["pin_len"])
    rg = L["ring"]
    for sy in (-1, 1):
        y_out = L["y_upr"] + UPR_T / 2.0
        pin = pin - Pos(0, sy * (y_out + rg.m / 2.0), L["z_pin"]) * Rot(90, 0, 0) * (Cylinder(radius=PIN_D / 2.0 + 1, height=rg.m) - Cylinder(radius=rg.d2 / 2.0, height=rg.m + 1))
    add("축(핀)", pin, f"Ø{PIN_D:g} g6 × {L['pin_len']:.0f}, 양끝 멈춤링 홈 Ø{rg.d2:g}×{rg.m:g}", 1, "SM45C", (0, 1.5, 0), "축")
    cam0 = _cam(L)
    add("캠 손잡이", cam0, f"편심 원 캠 R{CAM_R:g} 편심 {e:g} 두께 {CAM_T:g}, 레버 Ø{LEVER_D:g}×{LEVER_L:g} + 볼, 행정 2e = {2 * e:g}", 1, "SM45C", (0, 0, 2.5), "풀리")
    add("스프링", _spring(L, 0.0), f"압축 코일 Ø{SPRING_D:g} (간략 원통), 누름판 뒤끝 복귀", 1, "SWP", (0, 0, 0.5), "키")
    for sy in (-1, 1):
        y_out = L["y_upr"] + UPR_T / 2.0
        ring_local = Rot(0, 0, 90) * retaining_ring_solid(rg, 0.0, 0.0, 0.0)          # X축 링 → Y축 링
        add("멈춤링(C형)", Pos(0, sy * (y_out + rg.m / 2.0) - (rg.t / 2.0 if sy > 0 else -rg.t / 2.0) * 0 + (-rg.t / 2.0 if sy > 0 else rg.t / 2.0) * 0, L["z_pin"]) * Pos(0, -rg.t / 2.0, 0) * ring_local,
            f"축용 {rg.d1:g} KS B 1336", 1, "SK5", (0, sy * 2.5, 0), "멈춤링")

    body, strap_p, work_p, cam_p, pin_p = parts[0], parts[3], parts[2], parts[5], parts[4]
    fits = [fit(f"축 Ø{PIN_D:g} ↔ 본체 기둥 구멍", pin_p, body, PIN_D / 2.0, L["y_upr"] - UPR_T / 2.0, L["y_upr"] + UPR_T / 2.0, (0.0, L["z_pin"]), axis="Y")]
    strap_bottom_locked = strap_z_top(L, 180.0) - STRAP_T
    strap_bottom_free = strap_z_top(L, 0.0) - STRAP_T
    extra = [{"code": "A12", "message": f"클램핑 / clamping: 잠김(180도) 누름판 바닥 {strap_bottom_locked:.2f} = 공작물 윗면 {L['z_wtop']:.2f}, 풀림(0도) 틈 {strap_bottom_free - L['z_wtop']:.2f} (= 2e {2 * e:g})",
              "ok": abs(strap_bottom_locked - L["z_wtop"]) < 0.05 and abs((strap_bottom_free - L["z_wtop"]) - 2 * e) < 0.05, "actual": strap_bottom_free - L["z_wtop"], "required": 2 * e,
              "standard": "편심 원 캠: 리프트 = Rc - e cosθ, 행정 2e", "suggestion": {"option_a": "핀 높이 또는 캠 편심 조정"}}]
    pub = {"preset": "cam_clamp", "z_axis": L["z_pin"], "ys": [0.0], "pinion": None, "work_d": L["wd"], "cam_lift": e, "stroke": 2 * e,
           "cam_r": CAM_R, "pin_d": PIN_D, "z_pin": L["z_pin"], "z_work_top": L["z_wtop"], "v": {"width": L["vw"], "angle": 90},
           "key_hubs": {}, "fits": fits, "extra_checks": extra, "motion_steps": L["motion_steps"], "motion_label": L["motion_label"]}
    mates = [
        {"id": "M1", "pair": "축(핀) ↔ 본체 기둥 구멍 2", "type": "동심 + 멈춤링 양끝", "detail": f"Ø{PIN_D:g} H7/g6", "ok": True},
        {"id": "M2", "pair": "캠 손잡이 ↔ 축", "type": "회전 조인트(기둥 사이)", "detail": f"캠 두께 {CAM_T:g} < 누름판 폭 {STRAP_W:g}", "ok": True},
        {"id": "M3", "pair": "누름판 장공 ↔ 축", "type": "세로 미끄럼(폭 = 핀 Ø)", "detail": f"장공 {PIN_D:g}×{PIN_D + 2 * e + 1:g}", "ok": True},
        {"id": "M4", "pair": "캠 바깥 원 ↔ 누름판 윗면", "type": "접선 접촉(캠 종동)", "detail": f"리프트 Rc - e cosθ, {CAM_R - e:g}~{CAM_R + e:g}", "ok": True},
        {"id": "M5", "pair": "누름판 바닥 ↔ 공작물 윗면", "type": "면 접촉(잠김 때)", "detail": f"z {L['z_wtop']:.1f}", "ok": True},
        {"id": "M6", "pair": "공작물 ↔ V블록", "type": "선 접촉 2 (90도 V)", "detail": f"Ø{L['wd']:g}, 중심 높이 꼭짓점 + r√2", "ok": True},
        {"id": "M7", "pair": "스프링 ↔ 본체 자리 / 누름판 뒤끝", "type": "면 접촉(압축)", "detail": f"길이 {strap_bottom_free - BASE_T - 3:.1f}~{strap_bottom_locked - BASE_T - 3:.1f}", "ok": True},
    ]
    asm = Assembly(parts, pub, mates, [{"no": p.no, "item": p.name, "spec": p.spec, "qty": p.qty, "material": p.material} for p in parts])

    def motion(theta_deg: float) -> dict:
        dz = strap_z_top(L, theta_deg) - strap_z_top(L, 0.0)
        return {"캠 손잡이": place_cam(L, theta_deg, cam0), "누름판": Pos(0, 0, dz) * strap0, "스프링": _spring(L, theta_deg)}
    asm.motion = motion
    return asm
