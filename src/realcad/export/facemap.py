"""B-rep face map: splits the display mesh into triangles per real B-rep face and returns triangle -> face index plus face info (plane, cylinder diameter, axis).

Why: picking faces by guessing from mesh triangle angles missed small holes (e.g. diameter 3) and
coarsely tessellated round faces. Picking by kernel faces, as real CAD does, needs no guessing.
"""
from __future__ import annotations

import json
from pathlib import Path


def build(step_path: Path, out_stl: Path, out_json: Path, tol: float = 0.05, ang: float = 0.15) -> bool:
    import numpy as np
    import trimesh
    from build123d import import_step, GeomType, Vector
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder

    shape = import_step(str(step_path))
    verts, tris, tri_face, faces = [], [], [], []
    for i, f in enumerate(shape.faces()):
        try:
            vs, ts = f.tessellate(tol, ang)
        except Exception:
            continue
        base = len(verts)
        verts.extend((v.X, v.Y, v.Z) for v in vs)
        tris.extend((base + a, base + b, base + c) for a, b, c in ts)
        tri_face.extend([len(faces)] * len(ts))
        info = {"t": f.geom_type.name, "a": round(f.area, 2)}
        try:
            c = f.center()
            info["c"] = [round(c.X, 3), round(c.Y, 3), round(c.Z, 3)]
        except Exception:
            pass
        if f.geom_type == GeomType.PLANE:
            n = f.normal_at()
            info["n"] = [round(n.X, 5), round(n.Y, 5), round(n.Z, 5)]
        else:
            try:
                s = BRepAdaptor_Surface(f.wrapped)
                if s.GetType() == GeomAbs_Cylinder:
                    cy = s.Cylinder()
                    ax = cy.Axis()
                    lo, di = ax.Location(), ax.Direction()
                    P, D = Vector(lo.X(), lo.Y(), lo.Z()), Vector(di.X(), di.Y(), di.Z())
                    p = f.position_at(0.5, 0.5)
                    nn = f.normal_at(p)
                    radial = (p - P) - D * ((p - P).dot(D))
                    info.update({"r": round(cy.Radius(), 4), "ax": [round(D.X, 5), round(D.Y, 5), round(D.Z, 5)],
                                 "p": [round(P.X, 3), round(P.Y, 3), round(P.Z, 3)],
                                 "cc": bool(nn.dot(radial) < 0)})          # Concave = inner wall of a hole
            except Exception:
                pass
        faces.append(info)
    if not tris:
        return False
    m = trimesh.Trimesh(np.array(verts, dtype=float), np.array(tris, dtype=np.int64), process=False)
    out_stl.write_bytes(m.export(file_type="stl"))
    out_json.write_text(json.dumps({"tri_face": tri_face, "faces": faces}, separators=(",", ":")))
    return True
