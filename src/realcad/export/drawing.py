"""치수 기입된 2D 도면 DXF — AutoCAD 사용자가 바로 여는 '제작 도면'.

커뮤니티 니즈(Autodesk 포럼 "Fusion already knows the dimensions", "I always miss something"):
3D 가 아는 치수를 자동으로 도면에 적는다. 단위 mm 를 헤더($INSUNITS=4)에 명시해 10배 축소 사고를 막는다.
계약(plate) 경로는 치수를 정확히 알므로 전체 L×W·두께·구멍 지름·구멍 위치·체결 규격을 기입하고,
그 외는 윤곽(+구멍)과 전체 크기만 기입한다.
"""
from __future__ import annotations
from pathlib import Path


def _outline_entities(part, z: float):
    """수평 단면 → (outer wires, inner wires) 의 점 목록(mm). build123d 와이어를 폴리라인 점으로."""
    from build123d import Plane, section, Pos
    sec = section(part, section_by=Plane.XY.offset(z), height=0.0)
    sec = Pos(0, 0, -z) * sec
    outs, ins = [], []
    for f in sec.faces():
        outs.append(_wire_pts(f.outer_wire()))
        for w in f.inner_wires():
            ins.append((_wire_pts(w), w))
    return outs, ins


def _wire_pts(w, n: int = 120):
    pts = []
    for e in w.edges():
        k = 2 if e.geom_type.name == "LINE" else n // max(1, len(w.edges()))
        k = max(k, 2)
        for i in range(k):
            p = e.position_at(i / k)
            pts.append((float(p.X), float(p.Y)))
    return pts


def _circle_of(wire):
    """와이어가 원이면 (cx, cy, d) 아니면 None."""
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        edges = wire.edges()
        if len(edges) != 1 or edges[0].geom_type.name != "CIRCLE":
            return None
        c = BRepAdaptor_Curve(edges[0].wrapped).Circle()
        loc = c.Location()
        return (float(loc.X()), float(loc.Y()), 2.0 * float(c.Radius()))
    except Exception:
        return None


def write_drawing(part, path: str | Path, z: float | None = None, contract=None, fastener=None,
                  title: str = "RealCAD") -> Path | None:
    """치수 기입 DXF. 실패해도 None 만 돌려주고 예외를 올리지 않는다."""
    try:
        import ezdxf
        from ezdxf.enums import TextEntityAlignment
        bb = part.bounding_box()
        if z is None:
            z = bb.min.Z + min(1.0, max(bb.size.Z * 0.5, 0.2))
        outs, ins = _outline_entities(part, z)
        if not outs:
            return None
        doc = ezdxf.new("R2010", setup=True)
        doc.header["$INSUNITS"] = 4            # 4 = millimeters (AutoCAD 단위 사고 방지)
        doc.header["$MEASUREMENT"] = 1         # metric
        doc.layers.add("OUTLINE", color=7); doc.layers.add("HOLES", color=1)
        doc.layers.add("DIM", color=3); doc.layers.add("NOTES", color=4)
        msp = doc.modelspace()
        for pts in outs:
            msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "OUTLINE"})
        holes = []
        for pts, w in ins:
            c = _circle_of(w)
            if c:
                msp.add_circle((c[0], c[1]), c[2] / 2, dxfattribs={"layer": "HOLES"}); holes.append(c)
            else:
                msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "HOLES"})
        # 전체 치수(바운딩) — 아래/왼쪽
        xmin, xmax = min(p[0] for o in outs for p in o), max(p[0] for o in outs for p in o)
        ymin, ymax = min(p[1] for o in outs for p in o), max(p[1] for o in outs for p in o)
        off = max(8.0, 0.08 * max(xmax - xmin, ymax - ymin))
        d1 = msp.add_linear_dim(base=(xmin, ymin - off), p1=(xmin, ymin), p2=(xmax, ymin), dxfattribs={"layer": "DIM"}); d1.render()
        d2 = msp.add_linear_dim(base=(xmin - off, ymin), p1=(xmin, ymin), p2=(xmin, ymax), angle=90, dxfattribs={"layer": "DIM"}); d2.render()
        # 구멍 치수: 지름 + 위치(좌하단 기준)
        for i, (cx, cy, d) in enumerate(sorted(holes)):
            dd = msp.add_diameter_dim(center=(cx, cy), radius=d / 2, angle=45, dxfattribs={"layer": "DIM"}); dd.render()
            if i < 4:                                        # 위치 치수는 4개까지(도면 과밀 방지)
                k = off * (1.6 + 0.5 * i)
                dx = msp.add_linear_dim(base=(xmin, ymax + k), p1=(xmin, ymax), p2=(cx, ymax), dxfattribs={"layer": "DIM"}); dx.render()
                dy = msp.add_linear_dim(base=(xmax + k, ymin), p1=(xmax, ymin), p2=(xmax, cy), angle=90, dxfattribs={"layer": "DIM"}); dy.render()
        # 노트 블록
        notes = [f"{title}  (units: mm, scale 1:1)", f"OVERALL {xmax - xmin:.2f} x {ymax - ymin:.2f} x {bb.size.Z:.2f} mm"]
        if contract is not None and getattr(contract, "kind", "") == "plate" and fastener is not None:
            f = fastener; c = contract
            hd = holes[0][2] if holes else 0.0
            kind = {"through": "THRU + NUT", "tapped": "TAPPED", "insert": "HEAT-SET INSERT"}.get(c.hole_type, c.hole_type.upper())
            style = {"plain": "", "counterbore": " C'BORE", "countersink": " C'SINK"}.get(c.hole_style, "")
            notes.append(f"{len(c.holes)}x HOLE Ø{hd:.2f} {kind}{style} FOR {f.name} ({c.fit} fit, ASME B18.2.8/ISO 273)")
            notes.append(f"MATERIAL {c.material.upper()}  THICKNESS {c.plate.thickness:.2f}")
        y = ymin - off * 2.2
        for i, t in enumerate(notes):
            msp.add_text(t, height=max(2.5, 0.025 * (xmax - xmin)), dxfattribs={"layer": "NOTES"}).set_placement((xmin, y - i * off * 0.6), align=TextEntityAlignment.LEFT)
        path = Path(path); doc.saveas(str(path))
        return path
    except Exception:
        return None
