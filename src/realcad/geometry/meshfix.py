"""Clean an imported mesh before anything measures, splits or exports it.

Meshes from other tools often carry zero-area triangles, duplicated triangles, loose vertices and
flipped faces. CAD programs can stall for minutes on such a file (the import sits at 0% CPU), and
measurements on it come out wrong. Removing those defects does not change the shape. A mesh with an open gap
is then closed (fill_holes); that adds the volume of the patch, so the report says when it happened.
"""
from __future__ import annotations

AREA_EPS = 1e-9        # mm², triangles smaller than this are treated as zero-area


def clean(m):
    """trimesh.Trimesh -> (cleaned mesh, report dict). The input is not modified. Never raises."""
    rep = {"faces_in": 0, "faces_out": 0, "degenerate": 0, "duplicate": 0, "merged_vertices": 0,
           "unreferenced_vertices": 0, "normals_fixed": False, "holes_filled": False,
           "watertight_before": False, "watertight_after": False, "changed": False}
    try:
        import numpy as np
        out = m.copy()
        rep["faces_in"] = int(len(out.faces))
        rep["watertight_before"] = bool(out.is_watertight)
        v0 = len(out.vertices)

        out.merge_vertices()
        rep["merged_vertices"] = int(v0 - len(out.vertices))

        keep = out.area_faces > AREA_EPS
        rep["degenerate"] = int((~keep).sum())
        if rep["degenerate"]:
            out.update_faces(keep)

        srt = np.sort(out.faces, axis=1)
        _, first = np.unique(srt, axis=0, return_index=True)
        dup = len(out.faces) - len(first)
        rep["duplicate"] = int(dup)
        if dup:
            mask = np.zeros(len(out.faces), bool); mask[first] = True
            out.update_faces(mask)

        v1 = len(out.vertices)
        out.remove_unreferenced_vertices()
        rep["unreferenced_vertices"] = int(v1 - len(out.vertices))

        before = out.faces.copy()
        try:
            import trimesh
            trimesh.repair.fix_normals(out)
            rep["normals_fixed"] = bool(len(before) == len(out.faces) and (before != out.faces).any())
            if not out.is_watertight:
                rep["holes_filled"] = bool(trimesh.repair.fill_holes(out)) and out.is_watertight
        except Exception:
            pass

        rep["faces_out"] = int(len(out.faces))
        rep["watertight_after"] = bool(out.is_watertight)
        if out.is_watertight:
            rep["volume_mm3"] = round(float(abs(out.volume)), 2)     # filling a gap adds the volume it closes
        rep["changed"] = bool(rep["degenerate"] or rep["duplicate"] or rep["merged_vertices"]
                              or rep["unreferenced_vertices"] or rep["normals_fixed"] or rep["holes_filled"])
        return out, rep
    except Exception as e:
        rep["error"] = type(e).__name__
        return m, rep


def load_clean(path):
    """Load any mesh file as one trimesh and clean it -> (mesh, report)."""
    import trimesh
    return clean(trimesh.load(str(path), force="mesh"))


def note(rep: dict) -> str:
    """One Korean line for the screen, or "" when nothing changed."""
    if not rep or not rep.get("changed"):
        return ""
    bits = []
    if rep.get("degenerate"): bits.append(f"넓이 0 삼각형 {rep['degenerate']}개")
    if rep.get("duplicate"): bits.append(f"겹친 삼각형 {rep['duplicate']}개")
    if rep.get("merged_vertices"): bits.append(f"겹친 점 {rep['merged_vertices']}개")
    if rep.get("unreferenced_vertices"): bits.append(f"떠 있는 점 {rep['unreferenced_vertices']}개")
    if rep.get("normals_fixed"): bits.append("뒤집힌 면 방향")
    line = ("가져온 메시 정리: " + ", ".join(bits) + " 고침") if bits else ""
    if rep.get("holes_filled"):
        line += ("" if not line else ". ") + "뚫린 틈을 메웠어요 (메운 만큼 부피가 늘 수 있어요" + \
            (f", 정리 후 {rep['volume_mm3'] / 1000:.2f} cm³)" if rep.get("volume_mm3") is not None else ")")
    return line
