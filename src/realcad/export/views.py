"""Shop drawing PDF: three views (top, front, right) + isometric + overall dimensions + title block.

Uses OCC hidden line removal (HLR, HLRBRep) to project the part in each direction, drawing visible
edges solid and hidden edges dashed. Third-angle layout (front at the bottom, top view above it,
right view to its right, isometric in the empty upper right). Units mm, scale stated.

Aims at a one-page PDF a shop can use. A step up from `export/drawing.py` (single section DXF):
draws three projections of any part. Returns None on failure instead of raising.
"""
from __future__ import annotations
from pathlib import Path
import math


# Each view: (name, view direction = outward normal toward viewer, sheet horizontal u, sheet vertical v)
#   front: seen from -Y, horizontal X, vertical Z
#   top: looking down from +Z, horizontal X, vertical Y
#   right: seen from +X, horizontal Y, vertical Z
_VIEWS = {
    "FRONT": ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "TOP":   ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "RIGHT": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
}


def _norm(v):
    m = math.sqrt(sum(c * c for c in v)) or 1.0
    return (v[0] / m, v[1] / m, v[2] / m)


def _project_edges(part, eye, u_axis, v_axis):
    """Project part along eye and return (solid polylines, dashed polylines) as 2D (u, v) point lists.

    HLRBRep splits visible and hidden edges. Results are in the view plane's (ax2) local 2D coords
    (local X = u_axis, local Y = v_axis), so each edge is sampled and its X, Y read directly.
    """
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
    from build123d import Compound

    algo = HLRBRep_Algo()
    algo.Add(part.wrapped)
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*eye), gp_Dir(*u_axis))
    algo.Projector(HLRAlgo_Projector(ax))
    algo.Update()
    algo.Hide()
    hlr = HLRBRep_HLRToShape(algo)

    def comp(name):
        try:
            s = getattr(hlr, name)()
        except Exception:
            return None
        return s if (s is not None and not s.IsNull()) else None

    def polylines(shape):
        out = []
        if shape is None:
            return out
        try:
            edges = Compound(shape).edges()
        except Exception:
            return out
        for e in edges:
            try:
                n = 2 if e.geom_type.name == "LINE" else 48
                pts = [(float(p.X), float(p.Y)) for p in (e.position_at(i / n) for i in range(n + 1))]
                out.append(pts)
            except Exception:
                pass
        return out

    visible = polylines(comp("VCompound")) + polylines(comp("OutLineVCompound"))
    hidden = polylines(comp("HCompound")) + polylines(comp("OutLineHCompound"))
    return visible, hidden


def _iso_edges(part):
    """Isometric wireframe: hidden-line-removed solid edges seen from (1,1,1)."""
    eye = _norm((1.0, 1.0, 1.0))
    u = _norm((1.0, -1.0, 0.0))                 # sheet horizontal
    # v = eye x u (right-handed): sheet vertical
    v = _norm((eye[1] * u[2] - eye[2] * u[1],
               eye[2] * u[0] - eye[0] * u[2],
               eye[0] * u[1] - eye[1] * u[0]))
    vis, _ = _project_edges(part, eye, u, v)
    return vis


def _circles(polys):
    """Closed polylines that are nearly circular -> (cx, cy, r). Used for hole center lines."""
    out = []
    for pl in polys:
        if len(pl) < 10:
            continue
        if abs(pl[0][0] - pl[-1][0]) > 1e-3 or abs(pl[0][1] - pl[-1][1]) > 1e-3:
            continue                                       # closed curves only
        cx = sum(p[0] for p in pl) / len(pl)
        cy = sum(p[1] for p in pl) / len(pl)
        rs = [math.hypot(p[0] - cx, p[1] - cy) for p in pl]
        r = sum(rs) / len(rs)
        if r < 0.5:
            continue
        if max(abs(x - r) for x in rs) <= 0.06 * r:        # radius deviation within 6%: circle
            out.append((cx, cy, r))
    return out


def _extent(polys):
    xs = [p[0] for pl in polys for p in pl]
    ys = [p[1] for pl in polys for p in pl]
    if not xs:
        return None
    return min(xs), max(xs), min(ys), max(ys)


def _nice_scale(s: float) -> float:
    """Round the actual scale down to a standard scale (1:1, 1:2, 1:2.5, 1:5, 2:1 ...)."""
    if s <= 0:
        return 1.0
    steps = [100, 50, 20, 10, 5, 2, 1, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01]
    for cand in steps:
        if s >= cand:
            return cand
    return 0.01


def _fmt(v: float) -> str:
    return f"{v:.0f}" if abs(v - round(v)) < 0.05 else f"{v:.1f}"


def write_views_pdf(part, path: str | Path, *, title: str = "RealCAD",
                    part_number: str = "", material: str = "", projection: str = "THIRD ANGLE") -> Path | None:
    """Three-view + isometric PDF. None on failure."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle

        views = {}
        for name, (eye, u, v) in _VIEWS.items():
            vis, hid = _project_edges(part, _norm(eye), _norm(u), _norm(v))
            ext = _extent(vis + hid)
            if ext is None:
                return None
            views[name] = {"vis": vis, "hid": hid, "ext": ext}
        iso = _iso_edges(part)
        iso_ext = _extent(iso)

        fw = views["FRONT"]["ext"][1] - views["FRONT"]["ext"][0]     # X
        fh = views["FRONT"]["ext"][3] - views["FRONT"]["ext"][2]     # Z
        td = views["TOP"]["ext"][3] - views["TOP"]["ext"][2]         # Y (top view vertical)
        rd = views["RIGHT"]["ext"][1] - views["RIGHT"]["ext"][0]     # Y (right view horizontal)

        # A3 landscape 420 x 297 mm
        PW, PH = 420.0, 297.0
        margin = 14.0
        tb_w, tb_h = 185.0, 42.0                  # title block (lower right)
        gap = 32.0                                # gap between views (sheet mm)
        left_pad, bot_pad = 26.0, 24.0            # room for dimensions

        usable_w = PW - 2 * margin - left_pad - 14 - gap
        usable_h = PH - 2 * margin - bot_pad - tb_h - gap - 10
        s_raw = min(usable_w / max(fw + rd, 1e-6), usable_h / max(fh + td, 1e-6))
        s = _nice_scale(s_raw * 0.95)

        ox = margin + left_pad                                   # front view lower left (sheet mm)
        oy = margin + bot_pad + tb_h + 6
        pos = {
            "FRONT": (ox, oy),
            "TOP":   (ox, oy + fh * s + gap),
            "RIGHT": (ox + fw * s + gap, oy),
        }

        fig = plt.figure(figsize=(PW / 25.4, PH / 25.4))
        ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, PW); ax.set_ylim(0, PH)
        ax.set_aspect("equal"); ax.axis("off")

        # Sheet border
        ax.add_patch(Rectangle((margin, margin), PW - 2 * margin, PH - 2 * margin,
                               fill=False, lw=1.1, ec="#000"))

        def draw_view(name):
            vd = views[name]; px, py = pos[name]
            xmin, xmax, ymin, ymax = vd["ext"]
            def place(pl):
                return [((x - xmin) * s + px, (y - ymin) * s + py) for x, y in pl]
            for pl in vd["hid"]:
                q = place(pl); ax.plot([p[0] for p in q], [p[1] for p in q],
                                       ls=(0, (4, 2)), lw=0.45, color="#444")
            for pl in vd["vis"]:
                q = place(pl); ax.plot([p[0] for p in q], [p[1] for p in q],
                                       ls="-", lw=0.9, color="#000")
            for cx, cy, r in _circles(vd["vis"]):          # hole center marks
                gx, gy = (cx - xmin) * s + px, (cy - ymin) * s + py
                m = r * s + 2.0
                ax.plot([gx - m, gx + m], [gy, gy], ls=(0, (6, 2, 1, 2)), lw=0.4, color="#000")
                ax.plot([gx, gx], [gy - m, gy + m], ls=(0, (6, 2, 1, 2)), lw=0.4, color="#000")
            ax.text(px + (xmax - xmin) * s / 2, py - 7, name, ha="center", va="top", fontsize=9)
            return xmin, xmax, ymin, ymax

        draw_view("FRONT"); draw_view("TOP"); draw_view("RIGHT")

        # Isometric: empty upper right
        if iso_ext:
            ixmin, ixmax, iymin, iymax = iso_ext
            iw, ih = (ixmax - ixmin) * s, (iymax - iymin) * s
            ipx = ox + fw * s + gap + max(0, (rd * s - iw) / 2)
            ipy = oy + fh * s + gap
            for pl in iso:
                q = [((x - ixmin) * s + ipx, (y - iymin) * s + ipy) for x, y in pl]
                ax.plot([p[0] for p in q], [p[1] for p in q], ls="-", lw=0.7, color="#111")
            ax.text(ipx + iw / 2, ipy - 7, "ISOMETRIC", ha="center", va="top", fontsize=9)

        # Overall dimensions: width (below front, X), height (left of front, Z), depth (below right, Y)
        def dim_h(x0, x1, y, value):
            ax.annotate("", (x1, y), (x0, y), arrowprops=dict(arrowstyle="<->", lw=0.7, color="#000"))
            ax.plot([x0, x0], [y, y + 4], lw=0.4, color="#000")
            ax.plot([x1, x1], [y, y + 4], lw=0.4, color="#000")
            ax.text((x0 + x1) / 2, y - 2.5, _fmt(value), ha="center", va="top", fontsize=8)

        def dim_v(x, y0, y1, value):
            ax.annotate("", (x, y1), (x, y0), arrowprops=dict(arrowstyle="<->", lw=0.7, color="#000"))
            ax.plot([x, x + 4], [y0, y0], lw=0.4, color="#000")
            ax.plot([x, x + 4], [y1, y1], lw=0.4, color="#000")
            ax.text(x - 2.5, (y0 + y1) / 2, _fmt(value), ha="right", va="center", rotation=90, fontsize=8)

        fx, fy = pos["FRONT"]
        dim_h(fx, fx + fw * s, fy - 14, fw)
        dim_v(fx - 12, fy, fy + fh * s, fh)
        rx, ry = pos["RIGHT"]
        dim_h(rx, rx + rd * s, ry - 14, rd)

        # Title block
        tx, ty = PW - margin - tb_w, margin
        ax.add_patch(Rectangle((tx, ty), tb_w, tb_h, fill=False, lw=1.0, ec="#000"))
        ax.plot([tx, tx + tb_w], [ty + tb_h * 0.5, ty + tb_h * 0.5], lw=0.6, color="#000")
        ax.plot([tx + tb_w * 0.62, tx + tb_w * 0.62], [ty, ty + tb_h], lw=0.6, color="#000")
        ax.text(tx + 5, ty + tb_h * 0.72, title, fontsize=12, va="center", weight="bold")
        ax.text(tx + 5, ty + tb_h * 0.26,
                f"{part_number}   {material}".strip(), fontsize=8.5, va="center")
        scale_txt = "1:1" if s == 1 else (f"{int(1/s)}:1" if s < 1 else f"1:{int(s)}")
        # s = sheet/model. s<1 reduction (1:n), s>1 enlargement (n:1)
        scale_txt = "1:1" if abs(s - 1) < 1e-6 else (f"1:{_fmt(1/s)}" if s < 1 else f"{_fmt(s)}:1")
        ax.text(tx + tb_w * 0.64 + 3, ty + tb_h * 0.72, f"SCALE {scale_txt}   mm", fontsize=8.5, va="center")
        ax.text(tx + tb_w * 0.64 + 3, ty + tb_h * 0.26, projection, fontsize=8.5, va="center")

        path = Path(path)
        fig.savefig(str(path), format="pdf")
        plt.close(fig)
        return path
    except Exception:
        return None
