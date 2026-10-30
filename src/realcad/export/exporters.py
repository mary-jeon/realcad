"""STEP / STL 내보내기. STL은 공차 명시(맥>공모전 권고). build123d 기본 단위 mm."""
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
    """OCC 구/곡면 테셀레이션은 극점에 0넓이 삼각형을 남겨 trimesh가 non-watertight로 본다.
    그 면만 제거해(기하 불변, 부피 동일) 내보낸 STL을 watertight로 정리. 실패해도 원본 유지."""
    try:
        import trimesh
        m = trimesh.load(str(path))
        if not hasattr(m, "faces"):
            return
        mask = m.area_faces > 1e-9
        if bool(mask.all()):
            return                       # 퇴화면 없음 → OCC 출력 그대로
        m.update_faces(mask)
        m.remove_unreferenced_vertices()
        m.merge_vertices()
        m.export(str(path))
    except Exception:
        pass                             # 정리는 best-effort, 내보내기를 깨지 않음


def to_dxf(part: Part, path: str | Path, z: float | None = None) -> Path | None:
    """2D 평면도 DXF(AutoCAD 호환) — 지정 높이(z, 기본: 바닥에서 1 mm 위)의 수평 단면 윤곽을 선으로 내보낸다.
    판·브래킷은 구멍까지 그대로 나오고, 임의 부품은 바닥 평면도. 실패하면 None(내보내기를 깨지 않음)."""
    from build123d import ExportDXF, Plane, section
    try:
        bb = part.bounding_box()
        if z is None:
            z = bb.min.Z + min(1.0, max(bb.size.Z * 0.5, 0.2))
        from build123d import Pos
        sec = section(part, section_by=Plane.XY.offset(z), height=0.0)
        if sec is None or not hasattr(sec, "faces"):
            return None
        sec = Pos(0, 0, -z) * sec                      # DXF 는 XY 평면 → 단면을 z=0 으로 내린다
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
