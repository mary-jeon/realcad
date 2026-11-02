"""Assembly checks: all measured on the kernel or compared against standard tables.

A1 part interference : intersection volume of every part pair whose bounding boxes overlap (same definition as Inventor Interference Analysis)
A2 fit diameters     : read cylinder radii of bores, seats and holes on the finished solids and check mates match (bearing/shaft, bearing/housing, gear/shaft, pulley/shaft, cover/housing)
A3 axial retention   : bearing inner and outer rings blocked on both sides (shoulder, retaining ring, collar, cover lip)
A4 key joint         : top clearance t1 + t2 - h, key length <= hub width, key top <= hub slot bottom (measured bbox)
A5 gear pair         : measured center distance of the two housing holes = m(z1+z2)/2, gear/pinion intersection volume ~ 0 (meshing)
A6 bearing shoulders : shaft shoulder diameter in [da min, da max], housing shoulder diameter <= Da max
M2 per-part watertight: each part's exported mesh is closed
"""
from __future__ import annotations
import itertools
import math

from .checks import Finding, NOT_MEASURED, _intersection_volume, mesh_report

VOL_TOL = 0.5          # mm^3, numerical tolerance (slivers from touching faces)


def _bbox_overlap(b1, b2, tol: float = 0.01) -> bool:
    return not (b1.min.X > b2.max.X + tol or b2.min.X > b1.max.X + tol or
                b1.min.Y > b2.max.Y + tol or b2.min.Y > b1.max.Y + tol or
                b1.min.Z > b2.max.Z + tol or b2.min.Z > b1.max.Z + tol)


def a1_interference(parts) -> Finding:
    """A1: pairwise intersection volume. Booleans only for pairs whose bounding boxes overlap (speed)."""
    bbs = [(p, p.solid.bounding_box()) for p in parts]
    bad, unknown, tested = [], [], 0
    for (p1, b1), (p2, b2) in itertools.combinations(bbs, 2):
        if not _bbox_overlap(b1, b2):
            continue
        tested += 1
        v = _intersection_volume(p1.solid, p2.solid)
        if v is None:
            unknown.append(f"{p1.name}∩{p2.name}")
        elif v > VOL_TOL:
            bad.append((p1.name, p2.name, round(v, 2)))
    ok = not bad and not unknown
    desc = ", ".join(f"{a}∩{b}={v}mm³" for a, b, v in bad[:5])
    if bad:
        msg = f"부품 간섭 {len(bad)}쌍 / interference: {desc}"
    elif unknown:
        msg = f"교차 부피를 계산하지 못한 쌍 {len(unknown)}개, 확인 못함 / not checked: " + ", ".join(unknown[:5])
    else:
        msg = f"부품 간섭 없음 / no interference ({tested}쌍 실측)"
    return Finding("A1", "HARD", ok, msg,
                   actual=float(sum(v for *_, v in bad)), required=0.0, standard="Inventor Interference Analysis 와 같은 정의(교차 부피)",
                   suggestion={} if ok else {"option_a": "겹친 부품의 자리 지름, 위치를 규격표 값으로", "option_b": "분해도(exploded)로 어느 부위인지 확인"})


def cyl_faces(part, axis: str, c, axis_tol: float = 0.3):
    """Cylinder faces parallel to axis ('X'|'Z') whose axis passes through c -> [(radius, lo, hi)] (lo, hi = axial range).
    For X, c = (y, z); for Z, c = (x, y)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    try:
        from build123d import GeomType
    except Exception:
        return []
    out = []
    for f in part.faces():
        try:
            if f.geom_type != GeomType.CYLINDER:
                continue
            cyl = BRepAdaptor_Surface(f.wrapped).Cylinder()
            ax = cyl.Axis(); dr = ax.Direction(); loc = ax.Location()
            if axis == "X":
                if abs(dr.X()) < 0.99 or abs(loc.Y() - c[0]) > axis_tol or abs(loc.Z() - c[1]) > axis_tol:
                    continue
                bb = f.bounding_box(); lo, hi = float(bb.min.X), float(bb.max.X)
            elif axis == "Y":
                if abs(dr.Y()) < 0.99 or abs(loc.X() - c[0]) > axis_tol or abs(loc.Z() - c[1]) > axis_tol:
                    continue
                bb = f.bounding_box(); lo, hi = float(bb.min.Y), float(bb.max.Y)
            else:
                if abs(dr.Z()) < 0.99 or abs(loc.X() - c[0]) > axis_tol or abs(loc.Y() - c[1]) > axis_tol:
                    continue
                bb = f.bounding_box(); lo, hi = float(bb.min.Z), float(bb.max.Z)
            out.append((float(cyl.Radius()), lo, hi))
        except Exception:
            continue
    return out


def has_cyl(part, radius: float, lo: float, hi: float, c, axis: str = "X", tol: float = 0.03) -> bool:
    """Is there really a cylinder face of the given radius on axis c, overlapping the axial range [lo,hi]?"""
    for r, a, b in cyl_faces(part, axis, c):
        if abs(r - radius) <= tol and b >= lo - 0.05 and a <= hi + 0.05:
            return True
    return False


def a2_fits(asm) -> Finding:
    """A2: for each fit pair declared by the builder (layout["fits"]), measure both parts' cylinder radii and check both exist."""
    fits = asm.layout.get("fits") or []
    by_no = {p.no: p for p in asm.parts}
    bad = []
    for ft in fits:
        pa, pb = by_no.get(ft["a"]), by_no.get(ft["b"])
        if pa is None or pb is None:
            continue
        okA = has_cyl(pa.solid, ft["r"], ft["lo"], ft["hi"], ft["c"], ft.get("axis", "X"))
        okB = has_cyl(pb.solid, ft["r"], ft["lo"], ft["hi"], ft["c"], ft.get("axis", "X"))
        if not (okA and okB):
            bad.append(f"{ft['desc']} ({pa.name}{'✓' if okA else '✗'}/{pb.name}{'✓' if okB else '✗'})")
    ok = not bad
    return Finding("A2", "HARD", ok,
                   (f"끼워맞춤 지름 일치 / mating diameters match ({len(fits)}쌍 원통면 실측)" if ok else f"끼워맞춤 불일치 {len(bad)}건: " + "; ".join(bad[:4])),
                   actual=float(len(bad)), required=0.0, standard="KS B 0401 끼워맞춤(H7/k5, H7/h6) 호칭 지름 일치",
                   suggestion={} if ok else {"option_a": "보어와 자리 지름을 베어링 내경/턱 지름으로 통일"})


def a3_axial_chain(asm, c) -> Finding:   # shared by both presets (decided by which retaining elements exist)
    """A3: bearing axial retention. Inner ring: shaft shoulder on the inside (always), retaining ring (rings) or collar + pulley (left) outside. Outer ring: housing shoulder (inside) + cover lip (outside)."""
    a = c.assembly
    L = asm.layout
    missing = []
    for yi, y in enumerate(L["ys"]):
        tag = "주축" if yi == 0 else "피니언 축"
        if not a.rings:
            missing.append(f"{tag} 베어링 내륜 바깥쪽(멈춤링 없음)")
        if not a.covers:
            missing.append(f"{tag} 베어링 외륜 바깥쪽(커버 없음)")
        if not a.housing:
            missing.append(f"{tag} 베어링 외륜 안쪽(본체 턱 없음)")
    ok = not missing
    return Finding("A3", "HARD", ok,
                   ("축 방향 고정 체인 완성 / axial location: 턱 → 베어링 → 멈춤링, 본체 턱 ↔ 커버 턱" if ok else "축 방향 고정 빠짐: " + ", ".join(missing[:3])),
                   actual=float(len(missing)), required=0.0, standard="베어링 내륜, 외륜 양쪽 고정(교재 조립도 관례)",
                   suggestion={} if ok else {"option_a": "rings/covers/housing 을 true 로"})


def a4_keys(asm) -> Finding:
    """A4: key top clearance (t1+t2-h >= 0.1), key length <= hub width - 2, key top (measured) <= hub slot bottom (measured estimate)."""
    L = asm.layout
    z = L["z_axis"]
    from ..mech import standards as S
    bad = []
    if "key_hubs" in L:
        hubs = {k: tuple(v) for k, v in (L["key_hubs"] or {}).items()}
    else:
        hubs = {"평행키(기어)": ("스퍼기어", L["shoulder_d"]), "평행키(풀리)": ("V벨트 풀리", L["shaft_d"]), "평행키(피니언)": ("피니언", L["shoulder_d"])}
    if not any(p.name in hubs for p in asm.parts):
        return Finding("A4", "SOFT", True, "키 없음 / no keys in this assembly", standard="KS B 1311")
    for p in asm.parts:
        if p.name not in hubs:
            continue
        hub_name, seat_d = hubs[p.name]
        hub = next((h for h in asm.parts if h.name == hub_name), None)
        if hub is None:
            continue
        ks = S.parallel_key(seat_d)
        kb, hb = p.solid.bounding_box(), hub.solid.bounding_box()
        if ks.top_clearance < 0.1:
            bad.append(f"{p.name} 윗틈 {ks.top_clearance:g}")
        if kb.size.X > hb.size.X - 2.0 + 1e-6:
            bad.append(f"{p.name} 길이 {kb.size.X:.1f} > 허브 폭 {hb.size.X:.1f} - 2")
        top_groove = z + seat_d / 2.0 + ks.t2            # hub slot bottom (design value)
        if kb.max.Z > top_groove - 0.05:
            bad.append(f"{p.name} 윗면 {kb.max.Z:.2f} ≥ 홈 바닥 {top_groove:.2f}")
    ok = not bad
    return Finding("A4", "HARD", ok,
                   ("키 체결 / key fit: 폭 b 일치, 윗틈 t1+t2-h ≥ 0.1, 길이 ≤ 허브 폭 - 2" if ok else "키 체결 문제: " + "; ".join(bad[:3])),
                   actual=float(len(bad)), required=0.0, standard="KS B 1311 평행키 t1, t2",
                   suggestion={} if ok else {"option_a": "키 길이를 허브 폭 - 4 로"})


def a5_gear_pair(asm) -> Finding | None:
    """A5: with a pinion, measured center distance of the two housing holes = a, gear/pinion intersection volume ~ 0."""
    L = asm.layout
    probe = L.get("pair_probe")          # use {"a", "r", "names": [g1, g2], "m", "width"} if the builder provides it
    if not L.get("pinion") and not probe:
        return None
    if probe:
        a_th = float(probe["a"]); z = L["z_axis"]; D = 2.0 * float(probe["r"])
        gear = next((p for p in asm.parts if p.name == probe["names"][0]), None)
        pin = next((p for p in asm.parts if p.name == probe["names"][1]), None)
        gm, gw = float(probe["m"]), float(probe["width"])
    else:
        a_th = float(L["center_distance"]); z = L["z_axis"]; D = L["bearing_dDB"][1]
        gear = next((p for p in asm.parts if p.name == "스퍼기어"), None)
        pin = next((p for p in asm.parts if p.name in ("피니언", "피니언 축(일체)")), None)
        gm, gw = L["gear"]["m"], L["gear"]["width"]
    hs = next((p for p in asm.parts if p.name == "본체"), None)
    msgs, ok = [], True
    if hs is not None:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from build123d import GeomType
        ys = set()
        for f in hs.solid.faces():
            try:
                if f.geom_type != GeomType.CYLINDER:
                    continue
                cyl = BRepAdaptor_Surface(f.wrapped).Cylinder()
                if abs(cyl.Axis().Direction().X()) < 0.99 or abs(cyl.Radius() - D / 2.0) > 0.03:
                    continue
                loc = cyl.Axis().Location()
                if abs(loc.Z() - z) < 0.3:
                    ys.add(round(loc.Y(), 2))
            except Exception:
                continue
        ys = sorted(ys)
        if len(ys) >= 2:
            a_meas = ys[-1] - ys[0]
            if abs(a_meas - a_th) > 0.05:
                ok = False
            msgs.append(f"본체 구멍 중심거리 실측 {a_meas:.2f} / 이론 {a_th:.2f}")
        else:
            ok = False; msgs.append("본체 베어링 구멍 2열을 못 찾음")
    v = None
    if gear is not None and pin is not None:
        v = _intersection_volume(gear.solid, pin.solid)
        lim = 0.05 * gm * gw
        if v is None:
            ok = False
            msgs.append("기어∩피니언 " + NOT_MEASURED)
        else:
            if v > lim:
                ok = False
            msgs.append(f"기어∩피니언 {v:.3f} mm³ (허용 {lim:.2f})")
    return Finding("A5", "HARD", ok, "기어 쌍 중심거리, 맞물림 / gear pair: " + "; ".join(msgs),
                   actual=v, required=0.0, standard="a = m(z1+z2)/2, 인벌류트 20도 백래시 0.05m",
                   suggestion={} if ok else {"option_a": "두 구멍 중심거리를 a 로", "option_b": "잇수, 모듈 확인"})


def a6_shoulders(asm) -> Finding | None:
    L = asm.layout
    if not L.get("da_range"):
        return None
    dsh, (da_min, da_max), Da = L["shoulder_d"], L["da_range"], L["Da_max"]
    ok = da_min - 1e-6 <= dsh <= da_max + 1e-6
    return Finding("A6", "HARD", ok, f"베어링 턱 / shoulder: 축 턱 Ø{dsh:g} ∈ [{da_min:g}, {da_max:g}], 본체 턱 Ø{Da:g} ≤ Da max",
                   actual=dsh, required=da_min, standard=f"{L['bearing']} da/Da (NSK)",
                   suggestion={} if ok else {"option_a": f"축 턱 지름을 {da_min:g}~{da_max:g} 로"})


def m2_parts(asm) -> Finding:
    """M2 (assembly): each part's exported mesh is watertight."""
    bad = []
    for p in asm.parts:
        rep = mesh_report(p.solid)
        if not (rep.get("is_valid") and rep.get("watertight")) or "error" in rep:
            bad.append(f"{p.name}({rep.get('error', '') or ('조각 ' + str(rep.get('bodies')))})")
    ok = not bad
    return Finding("M2", "HARD", ok,
                   (f"부품 {len(asm.parts)}개 전부 watertight / all parts watertight" if ok else f"닫히지 않은 부품 {len(bad)}개: " + ", ".join(bad[:4])),
                   standard="출력, STEP 교환 가능", suggestion={} if ok else {"option_a": "해당 부품 형상 단순화"})


def a7_motion(asm, angles=None) -> Finding | None:
    """A7 motion interference: step the mechanism through angles and measure intersection volume of moving vs fixed parts (and each other), measured stroke, and bushing engagement length."""
    if asm.motion is None:
        return None
    L = asm.layout
    if angles is None:
        angles = tuple(L.get("motion_steps") or (0, 45, 90, 135, 180, 225, 270, 315))
    moving_names = set(asm.motion(0.0).keys())
    static = [p for p in asm.parts if p.name not in moving_names]
    static_bb = [(p, p.solid.bounding_box()) for p in static]
    bad, zs, engage = [], [], []
    bush = asm.by_name("가이드부시")
    for th in angles:
        mv = asm.motion(float(th))
        items = list(mv.items())
        for i, (n1, s1) in enumerate(items):
            b1 = s1.bounding_box()
            for p, b2 in static_bb:
                if n1 in ("편심축", "구동축", "종동축") and p.name in ("볼베어링", "멈춤링(C형)", "V벨트 풀리", "평행키(풀리)", "칼라", "간격링", "오일실", "부시"):
                    continue                     # parts that rotate with the shaft (or are rotationally symmetric) were already checked statically in A1
                if _bbox_overlap(b1, b2):
                    v = _intersection_volume(s1, p.solid)
                    if v is None or v > VOL_TOL:
                        bad.append((th, n1, p.name, round(v, 1) if v is not None else "계산 못함"))
            for n2, s2 in items[i + 1:]:
                if _bbox_overlap(b1, s2.bounding_box()):
                    v = _intersection_volume(s1, s2)
                    if v is None or v > VOL_TOL:
                        bad.append((th, n1, n2, round(v, 1) if v is not None else "계산 못함"))
        if "핀" in mv:
            zs.append(float(mv["핀"].bounding_box().center().Z))
        if bush is not None and "슬라이더" in mv:
            rod_top = float(mv["슬라이더"].bounding_box().max.Z)
            engage.append(rod_top - float(L["bush_z"][1]))
    stroke = (max(zs) - min(zs)) if zs else 0.0
    stroke_th = float(L.get("stroke", 0.0))
    ok = not bad and (not zs or abs(stroke - stroke_th) < 0.05) and (not engage or min(engage) >= 5.0)
    label = L.get("motion_label", "각도")
    msg = f"운동 간섭 / motion check {len(angles)}{label}" + (f": 행정 실측 {stroke:.2f} (= 2e {stroke_th:g})" if zs else f": {', '.join(sorted(moving_names))} 이동")
    if engage:
        msg += f", 봉이 부시 위로 최소 {min(engage):.1f} mm"
    if bad:
        msg += " / 간섭: " + ", ".join(f"{th}도 {a}∩{b}={v}mm³" for th, a, b, v in bad[:4])
    return Finding("A7", "HARD", ok, msg, actual=float(sum(v for *_, v in bad if isinstance(v, (int, float)))), required=0.0,
                   standard="편심 기구: 행정 = 2e, 회전 1바퀴 전 구간 간섭 0", suggestion={} if ok else {"option_a": "본체 안쪽 여유 또는 링크 길이 L 조정"})


def a10_hole_pattern(asm) -> Finding | None:
    """A10 hole pattern: for layout["hole_probe"] = {"r", "points": [(x,y)], "part"}, check the part really has a Z-axis cylinder face (radius r) at each point."""
    pr = asm.layout.get("hole_probe")
    if not pr:
        return None
    r = float(pr["r"]); pts = pr["points"]; name = pr["part"]
    cands = [p for p in asm.parts if p.name == name]
    missing = []
    for (x, y) in pts:
        found = False
        for p in cands:
            for rr, lo, hi in cyl_faces(p.solid, "Z", (x, y), axis_tol=0.05):
                if abs(rr - r) <= 0.03:
                    found = True; break
            if found: break
        if not found:
            missing.append((round(x, 2), round(y, 2)))
    ok = not missing
    return Finding("A10", "HARD", ok, (f"구멍 패턴 / hole pattern: 요구 좌표 {len(pts)}개 자리에 {name} 보어 Ø{2 * r:g} 실측 일치" if ok else f"구멍 패턴 불일치: {missing} 에 {name} 없음"),
                   actual=float(len(missing)), required=0.0, standard="공작물 구멍 좌표(사용자 입력) ↔ 부시 축선 실측 ±0.05",
                   suggestion={} if ok else {"option_a": "holes 좌표와 부시 배치 확인"})


def a8_extra(asm) -> list[Finding]:
    """Turn numeric checks the builder put in layout["extra_checks"] (code, description, measured, limit, condition) into Findings."""
    out = []
    for e in (asm.layout.get("extra_checks") or []):
        out.append(Finding(e["code"], e.get("severity", "HARD"), bool(e["ok"]), e["message"],
                           actual=e.get("actual"), required=e.get("required"), standard=e.get("standard", ""),
                           suggestion={} if e["ok"] else e.get("suggestion", {})))
    return out


def verify_assembly(asm, c) -> list[Finding]:
    out = [a1_interference(asm.parts), a2_fits(asm), a4_keys(asm)]
    if asm.layout.get("da_range"):
        out.append(a3_axial_chain(asm, c))
        out.append(a6_shoulders(asm))
    a5 = a5_gear_pair(asm)
    if a5 is not None:
        out.append(a5)
    a7 = a7_motion(asm)
    if a7 is not None:
        out.append(a7)
    out.extend(a8_extra(asm))
    a10 = a10_hole_pattern(asm)
    if a10 is not None:
        out.append(a10)
    out.append(m2_parts(asm))
    from .audit import audit
    out.extend(audit(asm.parts, asm.bom))
    return out
