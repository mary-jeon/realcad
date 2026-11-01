"""Dimensioned 2D drawing DXF that AutoCAD users can open as a shop drawing.

Writes the dimensions the 3D model already knows onto the drawing. Units are declared as mm in
the header ($INSUNITS=4) to avoid 10x scale mistakes. The contract (plate) path knows exact
dimensions, so it adds overall L x W, thickness, hole diameters, hole positions and fastener
spec; other parts get the outline (plus holes) and overall size only.
"""
from __future__ import annotations
from pathlib import Path


def _outline_entities(part, z: float):
    """Horizontal section -> point lists (mm) for (outer wires, inner wires). Converts build123d wires to polyline points."""
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
    """(cx, cy, d) if the wire is a circle, else None."""
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
    """Dimensioned DXF. Returns None on failure instead of raising."""
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
        doc.header["$INSUNITS"] = 4            # 4 = millimeters (avoids AutoCAD unit mistakes)
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
        # Overall (bounding) dimensions: bottom and left
        xmin, xmax = min(p[0] for o in outs for p in o), max(p[0] for o in outs for p in o)
        ymin, ymax = min(p[1] for o in outs for p in o), max(p[1] for o in outs for p in o)
        off = max(8.0, 0.08 * max(xmax - xmin, ymax - ymin))
        d1 = msp.add_linear_dim(base=(xmin, ymin - off), p1=(xmin, ymin), p2=(xmax, ymin), dxfattribs={"layer": "DIM"}); d1.render()
        d2 = msp.add_linear_dim(base=(xmin - off, ymin), p1=(xmin, ymin), p2=(xmin, ymax), angle=90, dxfattribs={"layer": "DIM"}); d2.render()
        # Hole dimensions: diameter + position (from lower left)
        for i, (cx, cy, d) in enumerate(sorted(holes)):
            dd = msp.add_diameter_dim(center=(cx, cy), radius=d / 2, angle=45, dxfattribs={"layer": "DIM"}); dd.render()
            if i < 4:                                        # At most 4 position dimensions (avoid clutter)
                k = off * (1.6 + 0.5 * i)
                dx = msp.add_linear_dim(base=(xmin, ymax + k), p1=(xmin, ymax), p2=(cx, ymax), dxfattribs={"layer": "DIM"}); dx.render()
                dy = msp.add_linear_dim(base=(xmax + k, ymin), p1=(xmax, ymin), p2=(xmax, cy), angle=90, dxfattribs={"layer": "DIM"}); dy.render()
        # Notes block
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
