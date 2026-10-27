"""설계 계약(DesignContract) — 메타(Muse Spark)가 자연어 요구를 이걸로 번역한다.
우리 커널은 이 계약만 신뢰해 부품을 만들고 검증한다(모델이 뱉은 코드를 직접 exec 안 함).

kind: plate(판/브래킷+볼트구멍) · container(통/컵/박스, 벽+바닥) · gear(스퍼 기어)
    · enclosure(보드 케이스) · profile(평면 커스텀 실루엣 돌출) · clamp(봉 무는 C클립)
    · ball(속 빈 구 쉘, 달 조명).
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Plate:
    length: float
    width: float
    thickness: float


@dataclass
class Wall:
    x: float
    height: float
    thickness: float


@dataclass
class Hole:
    x: float
    y: float


@dataclass
class Container:
    shape: str = "round"          # "round" | "box"
    outer_d: float = 60.0         # round 바깥지름
    length: float = 60.0          # box 가로
    width: float = 60.0           # box 세로
    height: float = 90.0
    wall: float = 2.4
    base: float = 2.4
    dividers: int = 0             # 내부 칸막이 개수(0=없음)


@dataclass
class Gear:
    teeth: int = 20
    module: float = 2.0
    thickness: float = 6.0
    bore: float = 6.0             # 가운데 축 구멍 지름


@dataclass
class Enclosure:
    board: str = "raspberry_pi_4"   # 보드 프리셋
    clearance: float = 2.0          # 보드 가장자리 ↔ 안쪽 벽
    wall: float = 2.0
    base: float = 2.0
    standoff_h: float = 4.0         # 바닥에서 보드를 띄우는 기둥 높이
    inner_h: float = 22.0           # 보드 위 부품 공간
    open_ports: bool = True         # 포트 쪽(긴 벽) 열기


@dataclass
class Profile:
    """평면 윤곽을 두께만큼 돌출한 부품(코스터·로고 태그류)."""
    shape: str = "asterisk"       # asterisk | star | disc | polygon | rounded_rect
    outer_d: float = 100.0        # 바깥지름/크기(mm)
    thickness: float = 5.0
    arms: int = 6                 # asterisk 갈래 수
    points: int = 6               # star 꼭짓점 수 / polygon 변 수
    arm_width: float = 0.0        # asterisk 막대 폭(0=자동 outer_d*0.12)
    corner_radius: float = 0.0    # rounded_rect 모서리 R(0=자동 outer_d*0.1)


@dataclass
class Clamp:
    """봉(원통)을 무는 C자 클립 + 선택적 부착물."""
    rod_d: float = 16.0           # 무는 봉 지름
    clearance: float = 0.3        # 봉과 틈
    wall: float = 3.0             # 클립 살두께
    gap_deg: float = 120.0        # 입 벌어진 각도(끼울 수 있게)
    height: float = 20.0          # 클립 높이
    attach: str = "none"          # none | pocket | plate
    pocket_w: float = 80.0        # pocket: 폭(Y)
    pocket_d: float = 15.0        # pocket: 깊이(X, 돌출)
    pocket_h: float = 100.0       # pocket: 높이(Z)
    tab_l: float = 30.0           # plate: 탭 길이(X, 돌출)
    tab_w: float = 20.0           # plate: 탭 폭(Y)
    tab_t: float = 4.0            # plate: 탭 두께(Z)


@dataclass
class Ball:
    """속 빈 구 쉘(달 조명) — 바닥에 전구 소켓 구멍."""
    outer_d: float = 150.0        # 구 지름
    wall: float = 2.0             # 껍데기 두께(슬라이서가 비움)
    socket_d: float = 30.0        # 바닥 소켓 구멍 지름(0=구멍 없음)
    socket_h: float = 0.0         # 소켓 구멍 깊이(0=자동 wall+3)


@dataclass
class DesignContract:
    kind: str = "plate"
    plate: Plate | None = None
    fastener: str = "1/4-20"
    fit: str = "normal"
    wall: Wall | None = None
    holes: list[Hole] = field(default_factory=list)
    container: Container | None = None
    gear: Gear | None = None
    enclosure: Enclosure | None = None
    profile: Profile | None = None
    clamp: Clamp | None = None
    ball: Ball | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "DesignContract":
        kind = d.get("kind", "plate")
        if kind == "enclosure":
            ed = d.get("enclosure", d)
            return cls(kind="enclosure", enclosure=Enclosure(
                board=ed.get("board", "raspberry_pi_4"),
                clearance=float(ed.get("clearance", 2)), wall=float(ed.get("wall", 2)),
                base=float(ed.get("base", 2)), standoff_h=float(ed.get("standoff_h", 4)),
                inner_h=float(ed.get("inner_h", 22)),
                open_ports=bool(ed.get("open_ports", True))))
        if kind == "container":
            cd = d.get("container", d)
            return cls(kind="container", container=Container(
                shape=cd.get("shape", "round"),
                outer_d=float(cd.get("outer_d", 60)),
                length=float(cd.get("length", 60)), width=float(cd.get("width", 60)),
                height=float(cd.get("height", 90)),
                wall=float(cd.get("wall", 2.4)), base=float(cd.get("base", 2.4)),
                dividers=int(cd.get("dividers", 0))))
        if kind == "gear":
            gd = d.get("gear", d)
            return cls(kind="gear", gear=Gear(
                teeth=int(gd.get("teeth", 20)), module=float(gd.get("module", 2)),
                thickness=float(gd.get("thickness", 6)), bore=float(gd.get("bore", 6))))
        if kind == "profile":
            pd = d.get("profile", d)
            return cls(kind="profile", profile=Profile(
                shape=pd.get("shape", "asterisk"),
                outer_d=float(pd.get("outer_d", 100)),
                thickness=float(pd.get("thickness", 5)),
                arms=int(pd.get("arms", 6)), points=int(pd.get("points", 6)),
                arm_width=float(pd.get("arm_width", 0) or 0),
                corner_radius=float(pd.get("corner_radius", 0) or 0)))
        if kind == "clamp":
            cd = d.get("clamp", d)
            return cls(kind="clamp", clamp=Clamp(
                rod_d=float(cd.get("rod_d", 16)),
                clearance=float(cd.get("clearance", 0.3)),
                wall=float(cd.get("wall", 3)), gap_deg=float(cd.get("gap_deg", 120)),
                height=float(cd.get("height", 20)), attach=cd.get("attach", "none"),
                pocket_w=float(cd.get("pocket_w", 80)), pocket_d=float(cd.get("pocket_d", 15)),
                pocket_h=float(cd.get("pocket_h", 100)), tab_l=float(cd.get("tab_l", 30)),
                tab_w=float(cd.get("tab_w", 20)), tab_t=float(cd.get("tab_t", 4))))
        if kind == "ball":
            bd = d.get("ball", d)
            return cls(kind="ball", ball=Ball(
                outer_d=float(bd.get("outer_d", 150)), wall=float(bd.get("wall", 2)),
                socket_d=float(bd.get("socket_d", 30)), socket_h=float(bd.get("socket_h", 0))))
        # plate / bracket (기본)
        p = d["plate"]; w = d.get("wall")
        return cls(
            kind="plate",
            plate=Plate(float(p["length"]), float(p["width"]), float(p["thickness"])),
            fastener=d.get("fastener", "1/4-20"), fit=d.get("fit", "normal"),
            wall=Wall(float(w["x"]), float(w["height"]), float(w["thickness"])) if w else None,
            holes=[Hole(float(h["x"]), float(h["y"])) for h in d.get("holes", [])],
        )

    def to_dict(self) -> dict:
        if self.kind == "container":
            c = self.container
            return {"kind": "container", "container": {
                "shape": c.shape, "outer_d": c.outer_d, "length": c.length,
                "width": c.width, "height": c.height, "wall": c.wall,
                "base": c.base, "dividers": c.dividers}}
        if self.kind == "gear":
            g = self.gear
            return {"kind": "gear", "gear": {
                "teeth": g.teeth, "module": g.module,
                "thickness": g.thickness, "bore": g.bore}}
        if self.kind == "enclosure":
            e = self.enclosure
            return {"kind": "enclosure", "enclosure": {
                "board": e.board, "clearance": e.clearance, "wall": e.wall,
                "base": e.base, "standoff_h": e.standoff_h, "inner_h": e.inner_h,
                "open_ports": e.open_ports}}
        if self.kind == "profile":
            p = self.profile
            return {"kind": "profile", "profile": {
                "shape": p.shape, "outer_d": p.outer_d, "thickness": p.thickness,
                "arms": p.arms, "points": p.points, "arm_width": p.arm_width,
                "corner_radius": p.corner_radius}}
        if self.kind == "clamp":
            c = self.clamp
            return {"kind": "clamp", "clamp": {
                "rod_d": c.rod_d, "clearance": c.clearance, "wall": c.wall,
                "gap_deg": c.gap_deg, "height": c.height, "attach": c.attach,
                "pocket_w": c.pocket_w, "pocket_d": c.pocket_d, "pocket_h": c.pocket_h,
                "tab_l": c.tab_l, "tab_w": c.tab_w, "tab_t": c.tab_t}}
        if self.kind == "ball":
            b = self.ball
            return {"kind": "ball", "ball": {
                "outer_d": b.outer_d, "wall": b.wall,
                "socket_d": b.socket_d, "socket_h": b.socket_h}}
        return {
            "kind": "plate",
            "plate": {"length": self.plate.length, "width": self.plate.width,
                      "thickness": self.plate.thickness},
            "fastener": self.fastener, "fit": self.fit,
            "wall": ({"x": self.wall.x, "height": self.wall.height,
                      "thickness": self.wall.thickness} if self.wall else None),
            "holes": [{"x": h.x, "y": h.y} for h in self.holes],
        }
