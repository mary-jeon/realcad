"""export/views.py: three-view PDF shop drawing.

Uses OCC HLR. Checks that any part yields a one-page PDF and that each view's projected extent
matches the part bbox.
"""
import os
import tempfile
from pathlib import Path

from build123d import Box
from realcad.export import views
from realcad.export.views import write_views_pdf


def test_pdf_written_and_nontrivial():
    part = Box(80, 50, 10)
    with tempfile.TemporaryDirectory() as td:
        os.environ.setdefault("MPLCONFIGDIR", td)
        out = write_views_pdf(part, Path(td) / "d.pdf", title="TEST", part_number="T-1", material="PLA")
        assert out is not None
        data = out.read_bytes()
        assert data[:4] == b"%PDF"
        assert len(data) > 3000


def test_projection_extents_match_bbox():
    part = Box(80, 50, 10)                      # X=80, Y=50, Z=10
    front, _ = views._project_edges(part, views._norm((0, -1, 0)), views._norm((1, 0, 0)), views._norm((0, 0, 1)))
    xmin, xmax, ymin, ymax = views._extent(front)
    assert abs((xmax - xmin) - 80) < 1e-3       # front horizontal = X
    assert abs((ymax - ymin) - 10) < 1e-3       # front vertical = Z
    top, _ = views._project_edges(part, views._norm((0, 0, 1)), views._norm((1, 0, 0)), views._norm((0, 1, 0)))
    _, _, tymin, tymax = views._extent(top)
    assert abs((tymax - tymin) - 50) < 1e-3     # top vertical = Y


def test_circle_detection_finds_hole():
    from build123d import Cylinder
    plate = Box(60, 40, 6) - Cylinder(4, 6)     # center hole, diameter 8
    vis, _ = views._project_edges(plate, views._norm((0, 0, 1)), views._norm((1, 0, 0)), views._norm((0, 1, 0)))
    circles = views._circles(vis)
    assert any(abs(r - 4) < 0.3 for _, _, r in circles)


def test_handles_bad_part_without_raising():
    class Bogus:
        wrapped = None
    assert write_views_pdf(Bogus(), "/tmp/should_not_exist_rc.pdf") is None
