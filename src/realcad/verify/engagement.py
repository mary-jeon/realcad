"""H3 thread engagement depth measurement.

engagement_raycast: raycasts the bolt axis into the tapped body to get the internal length
"""
from __future__ import annotations
from build123d import Part

EPS = 1e-6


def engagement_raycast(tapped_part: Part, axis_point, axis_dir) -> float:
    """Raycast the bolt axis into tapped_part. Sum of enter/exit pair lengths (mm). Fast, no booleans.
    Pass only the single tapped body as tapped_part so washers, nuts and other bodies on the axis are not hit.
    """
    from OCP.gp import gp_Pnt, gp_Dir, gp_Lin
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    shape = tapped_part.wrapped if hasattr(tapped_part, "wrapped") else tapped_part
    inter = IntCurvesFace_ShapeIntersector()
    inter.Load(shape, 1e-7)
    line = gp_Lin(gp_Pnt(*axis_point), gp_Dir(*axis_dir))
    inter.Perform(line, -1e9, 1e9)
    if not inter.IsDone() or inter.NbPnt() == 0:
        return 0.0
    params = sorted(inter.WParameter(i) for i in range(1, inter.NbPnt() + 1))
    if len(params) % 2 != 0:          # touching a boundary: give up
        return 0.0
    return sum(params[i + 1] - params[i] for i in range(0, len(params), 2))
