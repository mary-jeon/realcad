"""설계 계약(DesignContract) — 메타(Muse Spark)가 자연어 요구를 이걸로 번역한다.
우리 커널은 이 계약만 신뢰해 부품을 만들고 검증한다(모델이 뱉은 코드를 직접 exec 안 함).

kind: plate(판/브래킷+볼트구멍) · container(통/컵/박스, 벽+바닥) · gear(스퍼 기어)
    · enclosure(보드 케이스) · profile(평면 커스텀 실루엣 돌출) · clamp(봉 무는 C클립)
    · ball(속 빈 구 쉘, 달 조명)
    · assembly(조립: power_train 동력전달장치, eccentric_slider 편심왕복장치. 규격표로 치수 유도)
    · retrieve(파라메트릭 기본형으로 못 만드는 유기적 자유곡면 — 외부 3D 라이브러리 검색으로 넘김).
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
    board_l: float = 0.0            # board="custom" 일 때 보드 길이
    board_w: float = 0.0            # board="custom" 일 때 보드 폭
    board_holes: list = field(default_factory=list)   # custom: [[x,y],...] 보드 왼쪽아래 원점 mm
    board_screw: str = "M3"         # custom: 기둥 나사


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
class Assembly:
    """동력전달장치(power_train) 조립. 결정 입력 4개(베어링 호칭, 기어 m·z, 풀리 형·피치지름, 피니언 잇수)에서
    나머지 치수는 KS 규격표(mech/standards.py)로 유도한다. 메이트 M1~M9 는 빌더가 좌표로 고정한다."""
    preset: str = "power_train"
    bearing: str = "6204"         # 깊은 홈 볼베어링 호칭 → 축 베어링 자리 지름 = 내경
    shaft_d: float = 0.0          # 0 이면 베어링 내경
    gear_module: float = 2.0
    gear_teeth: int = 30
    gear_width: float = 0.0       # 0 이면 10m
    pinion_teeth: int = 0         # 0 이면 피니언(두번째 축) 없음
    pulley_type: str = "A"        # V벨트 형 A B C D, "none" 이면 풀리 없음
    pulley_dp: float = 100.0      # 풀리 피치(호칭) 지름
    pulley_grooves: int = 1
    pulley_hub_w: float = 0.0     # 0 이면 자동(홈 수·축 지름)
    housing: bool = True
    covers: bool = True
    bolts: bool = True
    oil_seal: bool = True
    rings: bool = True            # 멈춤링
    exploded: float = 0.0         # 분해도 간격(mm), 0 = 조립 상태
    # preset "eccentric_slider"(편심왕복장치) 전용
    eccentricity: float = 8.0     # 편심량 e (행정 = 2e)
    link_length: float = 50.0     # 링크 중심 간 길이(편심 저널 중심 ↔ 핀)
    slider_d: float = 20.0        # 슬라이더 봉 지름(= 가이드부시 보어)
    # preset "drill_jig"(드릴지그) 전용: 공작물과 구멍 패턴
    work_l: float = 80.0
    work_w: float = 50.0
    work_t: float = 15.0
    drill_d: float = 10.0
    holes: list = field(default_factory=lambda: [[-20.0, 0.0], [20.0, 0.0]])   # 공작물 중심 기준 (x, y)
    # preset "vise"(탁상 바이스) 전용
    jaw_w: float = 80.0           # 조 폭(Y)
    open_max: float = 60.0        # 최대 벌림
    screw_d: float = 16.0         # 리드나사 호칭 지름
    # preset "cam_clamp"(캠 클램프) 전용
    work_d: float = 30.0          # 원통 공작물 지름
    cam_lift: float = 4.0         # 캠 편심(리프트)


@dataclass
class Retrieve:
    """파라메트릭 기본형으로 표현 불가 → 외부 3D 모델 라이브러리에서 검색해 불러온다."""
    query: str = ""               # 외부 라이브러리 검색어(영문)
    note: str = ""                # 왜 파라메트릭 생성이 불가한지 한 줄
    parts: list = field(default_factory=list)   # 복합물을 부품 분해 요청 시: [{name, query}]


@dataclass
class DesignContract:
    kind: str = "plate"
    plate: Plate | None = None
    fastener: str = "1/4-20"
    fit: str = "normal"
    hole_dia: float | None = None      # 명시 구멍 지름(mm). None 이면 규격 공차구멍. 커널이 H2 로 실측 검증
    hole_type: str = "through"         # through(관통+너트) | tapped(판에 직접 나사) | insert(히트세트 인서트) 
    hole_style: str = "plain"          # plain | counterbore(머리 묻힘) | countersink(접시머리)
    hole_comp: float = 0.2             # FDM 구멍 수축 보정(mm, 지름에 더함). 커뮤니티 실측 0.1~0.3 작게 나옴. 0 이면 보정 없음
    material: str = "pla"              # 판 재질: pla/petg/abs/plastic(k=2.0) aluminum(1.5) brass(1.3) steel(1.0)
    mate_thickness: float = 0.0        # 관통 체결 시 상대 부재 두께(mm). 볼트 길이 산정용(0=모름→판 두께만)
    washer: bool = False               # 평와셔 포함(길이 산정)
    nut: bool = True                   # 관통이면 너트 포함(길이 산정)
    wall: Wall | None = None
    holes: list[Hole] = field(default_factory=list)
    container: Container | None = None
    gear: Gear | None = None
    enclosure: Enclosure | None = None
    profile: Profile | None = None
    clamp: Clamp | None = None
    ball: Ball | None = None
    assembly: Assembly | None = None
    retrieve: Retrieve | None = None
    fastener_exact: bool = True        # builder 가 채움: 요청 규격을 정확히 보유했는가
    fastener_note: str = ""            # 미보유 시 치환 설명(F0 메시지)

    @classmethod
    def from_dict(cls, d: dict) -> "DesignContract":
        """LLM/사용자 입력 dict → 계약. 수치는 _sanitize 로 안전 범위에 가둔다(DoS·OCC 폭주 방지)."""
        return _sanitize(cls._from_dict_raw(d))

    @classmethod
    def _from_dict_raw(cls, d: dict) -> "DesignContract":
        kind = d.get("kind", "plate")
        if kind == "retrieve":
            rd = d.get("retrieve", d)
            parts = []
            for p in (rd.get("parts") or []):
                if isinstance(p, dict) and (p.get("name") or p.get("query")):
                    parts.append({"name": str(p.get("name", "")).strip(),
                                  "query": str(p.get("query", "") or p.get("name", "")).strip()})
            return cls(kind="retrieve", retrieve=Retrieve(
                query=str(rd.get("query", "")).strip(),
                note=str(rd.get("note", "")).strip(), parts=parts))
        if kind == "enclosure":
            ed = d.get("enclosure", d)
            return cls(kind="enclosure", enclosure=Enclosure(
                board=ed.get("board", "raspberry_pi_4"),
                clearance=float(ed.get("clearance", 2)), wall=float(ed.get("wall", 2)),
                base=float(ed.get("base", 2)), standoff_h=float(ed.get("standoff_h", 4)),
                inner_h=float(ed.get("inner_h", 22)),
                open_ports=bool(ed.get("open_ports", True)),
                board_l=float(ed.get("board_l", 0) or 0), board_w=float(ed.get("board_w", 0) or 0),
                board_holes=[[float(h[0]), float(h[1])] for h in (ed.get("board_holes") or []) if isinstance(h, (list, tuple)) and len(h) == 2][:12],
                board_screw=str(ed.get("board_screw", "M3") or "M3")))
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
        if kind == "assembly":
            ad = d.get("assembly", d)
            g = ad.get("gear") if isinstance(ad.get("gear"), dict) else {}
            pu = ad.get("pulley") if isinstance(ad.get("pulley"), dict) else {}
            ptype = str(pu.get("type", ad.get("pulley_type", "A")) or "A")
            return cls(kind="assembly", assembly=Assembly(
                preset=str(ad.get("preset", "power_train") or "power_train"),
                bearing=str(ad.get("bearing", "6204") or "6204"),
                shaft_d=float(ad.get("shaft_d", 0) or 0),
                gear_module=float(g.get("module", ad.get("gear_module", 2)) or 2),
                gear_teeth=int(g.get("teeth", ad.get("gear_teeth", 30)) or 30),
                gear_width=float(g.get("width", ad.get("gear_width", 0)) or 0),
                pinion_teeth=int(ad.get("pinion_teeth", 0) or 0),
                pulley_type=("none" if ptype.lower() in ("none", "no", "false", "") else ptype.upper()),
                pulley_dp=float(pu.get("dp", ad.get("pulley_dp", 100)) or 100),
                pulley_grooves=int(pu.get("grooves", ad.get("pulley_grooves", 1)) or 1),
                pulley_hub_w=float(pu.get("hub_width", ad.get("pulley_hub_w", 0)) or 0),
                housing=bool(ad.get("housing", True)), covers=bool(ad.get("covers", True)),
                bolts=bool(ad.get("bolts", True)), oil_seal=bool(ad.get("oil_seal", True)),
                rings=bool(ad.get("rings", True)),
                exploded=float(ad.get("exploded", 0) or 0),
                eccentricity=float(ad.get("eccentricity", ad.get("e", 8)) or 8),
                link_length=float(ad.get("link_length", 50) or 50),
                slider_d=float(ad.get("slider_d", 20) or 20),
                work_l=float((ad.get("work") or {}).get("length", ad.get("work_l", 80)) or 80),
                work_w=float((ad.get("work") or {}).get("width", ad.get("work_w", 50)) or 50),
                work_t=float((ad.get("work") or {}).get("thickness", ad.get("work_t", 15)) or 15),
                drill_d=float(ad.get("drill_d", 10) or 10),
                jaw_w=float(ad.get("jaw_w", 80) or 80), open_max=float(ad.get("open_max", 60) or 60), screw_d=float(ad.get("screw_d", 16) or 16),
                work_d=float(ad.get("work_d", 30) or 30), cam_lift=float(ad.get("cam_lift", 4) or 4),
                holes=[[float(h[0]), float(h[1])] for h in (ad.get("holes") or [[-20, 0], [20, 0]]) if isinstance(h, (list, tuple)) and len(h) == 2][:16]))
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
            hole_dia=(float(d["hole_dia"]) if d.get("hole_dia") not in (None, "", 0) else None),
            hole_type=str(d.get("hole_type", "through") or "through").lower(),
            hole_style=str(d.get("hole_style", "plain") or "plain").lower(),
            hole_comp=float(d.get("hole_comp", 0.2) if d.get("hole_comp") is not None else 0.2),
            material=str(d.get("material", "pla") or "pla").lower(),
            mate_thickness=float(d.get("mate_thickness", 0) or 0),
            washer=bool(d.get("washer", False)), nut=bool(d.get("nut", True)),
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
                "open_ports": e.open_ports, "board_l": e.board_l, "board_w": e.board_w,
                "board_holes": e.board_holes, "board_screw": e.board_screw}}
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
        if self.kind == "assembly":
            a = self.assembly
            return {"kind": "assembly", "assembly": {
                "preset": a.preset, "bearing": a.bearing, "shaft_d": a.shaft_d,
                "gear": {"module": a.gear_module, "teeth": a.gear_teeth, "width": a.gear_width},
                "pinion_teeth": a.pinion_teeth,
                "pulley": {"type": a.pulley_type, "dp": a.pulley_dp, "grooves": a.pulley_grooves, "hub_width": a.pulley_hub_w},
                "housing": a.housing, "covers": a.covers, "bolts": a.bolts, "oil_seal": a.oil_seal,
                "rings": a.rings, "exploded": a.exploded,
                **({"eccentricity": a.eccentricity, "link_length": a.link_length, "slider_d": a.slider_d}
                   if a.preset == "eccentric_slider" else {}),
                **({"work": {"length": a.work_l, "width": a.work_w, "thickness": a.work_t}, "drill_d": a.drill_d, "holes": a.holes}
                   if a.preset == "drill_jig" else {}),
                **({"jaw_w": a.jaw_w, "open_max": a.open_max, "screw_d": a.screw_d} if a.preset == "vise" else {}),
                **({"work_d": a.work_d, "cam_lift": a.cam_lift} if a.preset == "cam_clamp" else {})}}
        if self.kind == "retrieve":
            r = self.retrieve
            return {"kind": "retrieve", "retrieve": {
                "query": r.query, "note": r.note, "parts": r.parts}}
        return {
            "kind": "plate",
            "plate": {"length": self.plate.length, "width": self.plate.width,
                      "thickness": self.plate.thickness},
            "fastener": self.fastener, "fit": self.fit, "hole_dia": self.hole_dia, "hole_type": self.hole_type, "hole_style": self.hole_style, "hole_comp": self.hole_comp, "material": self.material, "mate_thickness": self.mate_thickness, "washer": self.washer, "nut": self.nut,
            "wall": ({"x": self.wall.x, "height": self.wall.height,
                      "thickness": self.wall.thickness} if self.wall else None),
            "holes": [{"x": h.x, "y": h.y} for h in self.holes],
        }


# ── 입력 범위 가드 ──────────────────────────────────────────────
MAX_DIM_MM = 1000.0        # 한 변 최대(일반 프린터 빌드볼륨의 수 배)
MIN_DIM_MM = 0.2
_INT_LIMITS = {"teeth": (4, 200), "dividers": (0, 50), "arms": (2, 64), "points": (3, 64),
               "gear_teeth": (8, 200), "pinion_teeth": (0, 200), "pulley_grooves": (1, 6)}
_MAX_HOLES = 64


def _clampf(v, lo=MIN_DIM_MM, hi=MAX_DIM_MM):
    try:
        v = float(v)
    except Exception:
        return lo
    if v != v:            # NaN
        return lo
    return max(lo, min(hi, v))


def _sanitize(c: "DesignContract") -> "DesignContract":
    """음수·NaN·10^6 같은 값으로 커널이 멈추지 않게 모든 수치를 가둔다."""
    for obj in (c.plate, c.wall, c.container, c.gear, c.enclosure, c.profile, c.clamp, c.ball, c.assembly):
        if obj is None:
            continue
        for k, v in list(vars(obj).items()):
            if isinstance(v, bool) or isinstance(v, str) or v is None:
                continue
            if k in _INT_LIMITS:
                lo, hi = _INT_LIMITS[k]
                try:
                    iv = int(v)
                except Exception:
                    iv = lo
                setattr(obj, k, max(lo, min(hi, iv)))
            elif k == "gap_deg":
                setattr(obj, k, _clampf(v, 10.0, 300.0))
            elif k in ("clearance", "socket_h", "arm_width", "corner_radius", "socket_d"):
                setattr(obj, k, _clampf(v, 0.0, MAX_DIM_MM))
            elif obj is c.wall and k == "x":                 # 벽 위치는 음수 가능(판 중심 기준)
                setattr(obj, k, _clampf(v, -MAX_DIM_MM, MAX_DIM_MM))
            elif isinstance(v, (int, float)):
                setattr(obj, k, _clampf(v))
    if c.assembly is not None:
        a = c.assembly
        # 0 = 자동 인 필드는 일반 루프가 0.2 로 올려놓으므로 되돌린다
        a.shaft_d = 0.0 if a.shaft_d < 5.0 else _clampf(a.shaft_d, 5.0, 75.0)
        a.gear_module = _clampf(a.gear_module, 0.5, 10.0)
        a.gear_width = 0.0 if a.gear_width < 1.0 else _clampf(a.gear_width, 1.0, 200.0)
        a.pulley_dp = _clampf(a.pulley_dp, 40.0, 600.0)
        a.pulley_hub_w = 0.0 if a.pulley_hub_w < 1.0 else _clampf(a.pulley_hub_w, 1.0, 200.0)
        a.exploded = 0.0 if a.exploded < 0.5 else _clampf(a.exploded, 0.5, 120.0)
        if a.pulley_type not in ("A", "B", "C", "D", "none"):
            a.pulley_type = "A"
        if a.preset not in ("power_train", "eccentric_slider", "gear_pump", "drill_jig", "vise", "cam_clamp"):
            a.preset = "power_train"
        a.eccentricity = _clampf(a.eccentricity, 2.0, 30.0)
        a.link_length = _clampf(a.link_length, 20.0, 200.0)
        a.slider_d = _clampf(a.slider_d, 8.0, 40.0)
        a.work_l = _clampf(a.work_l, 10.0, 400.0); a.work_w = _clampf(a.work_w, 10.0, 400.0); a.work_t = _clampf(a.work_t, 1.0, 100.0)
        a.drill_d = _clampf(a.drill_d, 1.0, 20.0)
        a.jaw_w = _clampf(a.jaw_w, 30.0, 300.0); a.open_max = _clampf(a.open_max, 10.0, 300.0); a.screw_d = _clampf(a.screw_d, 8.0, 40.0)
        a.work_d = _clampf(a.work_d, 5.0, 200.0); a.cam_lift = _clampf(a.cam_lift, 1.0, 20.0)
        a.holes = [[_clampf(h[0], -200.0, 200.0), _clampf(h[1], -200.0, 200.0)] for h in (a.holes or [])][:16] or [[0.0, 0.0]]
    if c.hole_dia is not None:
        c.hole_dia = _clampf(c.hole_dia, 0.5, 100.0)
    if c.fit not in ("close", "normal", "loose"):
        c.fit = "normal"
    if c.hole_type not in ("through", "tapped", "insert"):
        c.hole_type = "through"
    if c.hole_style not in ("plain", "counterbore", "countersink"):
        c.hole_style = "plain"
    c.mate_thickness = _clampf(c.mate_thickness, 0.0, 500.0)
    c.hole_comp = _clampf(c.hole_comp, 0.0, 1.0)
    if len(c.holes) > _MAX_HOLES:
        c.holes = c.holes[:_MAX_HOLES]
    for h in c.holes:
        h.x = _clampf(h.x, -MAX_DIM_MM, MAX_DIM_MM)
        h.y = _clampf(h.y, -MAX_DIM_MM, MAX_DIM_MM)
    return c
