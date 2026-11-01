"""STEP / STL export. STL uses an explicit tolerance (print quality). build123d default unit is mm."""
from __future__ import annotations
from pathlib import Path
from build123d import Part, export_step, export_stl


def to_step(part: Part, path: str | Path) -> Path:
    path = Path(path)
    export_step(part, str(path))
    return path


def to_stl(part: Part, path: str | Path) -> Path:
    path = Path(path)
    export_stl(part, str(path), tolerance=0.01, angular_tolerance=0.1)
    _clean_degenerate(path)
    return path


def _clean_degenerate(path: Path) -> None:
    """OCC tessellation of spheres and curved faces leaves zero-area triangles at the poles, so trimesh
    sees the mesh as non-watertight. Remove just those faces (geometry and volume unchanged) to make
    the exported STL watertight. Keeps the original on failure."""
    try:
        import trimesh
        m = trimesh.load(str(path))
        if not hasattr(m, "faces"):
            return
        mask = m.area_faces > 1e-9
        if bool(mask.all()):
            return                       # No degenerate faces: keep OCC output as is
        m.update_faces(mask)
        m.remove_unreferenced_vertices()
        m.merge_vertices()
        m.export(str(path))
    except Exception:
        pass                             # Cleanup is best-effort and must not break export


def to_dxf(part: Part, path: str | Path, z: float | None = None) -> Path | None:
    """2D plan DXF (AutoCAD compatible): exports the outline of a horizontal section at height z
    (default 1 mm above the bottom) as lines. Plates and brackets come out with their holes; other
    parts give a bottom plan view. Returns None on failure (does not break export)."""
    from build123d import ExportDXF, Plane, section
    try:
        bb = part.bounding_box()
        if z is None:
            z = bb.min.Z + min(1.0, max(bb.size.Z * 0.5, 0.2))
        from build123d import Pos
        sec = section(part, section_by=Plane.XY.offset(z), height=0.0)
        if sec is None or not hasattr(sec, "faces"):
            return None
        sec = Pos(0, 0, -z) * sec                      # DXF lives in the XY plane, so move the section down to z=0
        faces = sec.faces()
        if not faces:
            return None
        ex = ExportDXF()
        ex.add_layer("OUTLINE"); ex.add_layer("HOLES")
        for f in faces:
            ex.add_shape(f.outer_wire(), layer="OUTLINE")
            for w in f.inner_wires():
                ex.add_shape(w, layer="HOLES")
        path = Path(path); ex.write(str(path))
        return path
    except Exception:
        return None
