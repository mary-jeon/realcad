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
