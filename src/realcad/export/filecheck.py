"""Check every exported file after it is written: not empty, opens again, and its fingerprint (sha256).

A STEP or STL can be written as an empty or broken file without any exception (a failed boolean,
a crashed tessellation). Re-reading each file catches that: STEP is imported again (solids, volume), meshes are
loaded (triangles, closed or not), DXF is parsed (entities), PDF must have its header, end marker and pages.
A file that fails is taken off the download list. This shows the file is whole, not that the shape is right;
the sha256 lets anyone confirm later that the file they have is the one that was checked.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_step(p: Path) -> tuple[bool, str]:
    from build123d import import_step
    shape = import_step(str(p))
    solids = shape.solids()
    if not solids:
        return False, "다시 열었더니 입체가 없어요 / no solid after re-import"
    vol = sum(abs(s.volume) for s in solids)
    if vol <= 1e-6:
        return False, "다시 열었더니 부피가 0이에요 / zero volume after re-import"
    return True, f"입체 {len(solids)}개, 부피 {vol / 1000:.2f} cm³ / {len(solids)} solid(s)"


def _check_mesh(p: Path) -> tuple[bool, str]:
    import trimesh
    m = trimesh.load(str(p), force="mesh")
    n = int(len(getattr(m, "faces", [])))
    if n == 0:
        return False, "다시 열었더니 삼각형이 없어요 / no triangles after re-import"
    return True, f"삼각형 {n}개" + (", 닫힌 메시 / watertight" if m.is_watertight else ", 열린 메시 / not watertight")


def _check_text(p: Path, must: str | None) -> tuple[bool, str]:
    t = p.read_text(encoding="utf-8", errors="replace")
    if must and must not in t:
        return False, f"'{must}' 표시가 없어요 / missing {must!r}"
    return True, f"{len(t.splitlines())}줄 / lines"


def _check_pdf(p: Path) -> tuple[bool, str]:
    b = p.read_bytes()
    if b[:5] != b"%PDF-":
        return False, "PDF 머리가 없어요 / not a PDF"
    if b"%%EOF" not in b[-2048:]:
        return False, "PDF 끝 표시가 없어요, 중간에 끊긴 파일 / truncated PDF"
    pages = b.count(b"/Type /Page") + b.count(b"/Type/Page") - b.count(b"/Type /Pages") - b.count(b"/Type/Pages")
    if pages <= 0:
        return False, "PDF에 쪽이 없어요 / no pages"
    return True, f"PDF {pages}쪽 / page(s)"


def _check_dxf(p: Path) -> tuple[bool, str]:
    try:
        import ezdxf
    except ImportError:                                  # without the parser: at least the DXF section and end markers
        t = p.read_text(encoding="utf-8", errors="replace")
        ok = "SECTION" in t and t.rstrip().endswith("EOF")
        return ok, ("DXF 표시 확인 / DXF markers" if ok else "DXF 표시가 없어요 / not a DXF")
    doc = ezdxf.readfile(str(p))
    n = len(doc.modelspace())
    if n == 0:
        return False, "DXF를 열었더니 그려진 선이 없어요 / no entities"
    return True, f"DXF 도형 {n}개 / entities"


def check_file(path, kind: str | None = None) -> dict:
    """One file -> {"file", "kind", "bytes", "sha256", "ok", "msg"}. Never raises."""
    p = Path(path)
    kind = (kind or p.suffix.lstrip(".")).upper()
    out = {"file": p.name, "kind": kind, "bytes": 0, "sha256": "", "ok": False, "msg": ""}
    try:
        if not p.exists():
            out["msg"] = "파일이 없어요 / file missing"
            return out
        out["bytes"] = p.stat().st_size
        if out["bytes"] == 0:
            out["msg"] = "0바이트 파일이에요 / empty file"
            return out
        out["sha256"] = sha256(p)
        if kind in ("STEP", "STP"):
            ok, msg = _check_step(p)
        elif kind in ("STL", "OBJ", "3MF", "PLY"):
            ok, msg = _check_mesh(p)
        elif kind == "DXF":
            ok, msg = _check_dxf(p)
        elif kind == "CSV":
            ok, msg = _check_text(p, None)
        elif kind == "PDF":
            ok, msg = _check_pdf(p)
        else:
            ok, msg = True, "크기만 확인 / size only"
        out["ok"], out["msg"] = bool(ok), msg
    except Exception as e:
        out["msg"] = f"다시 열기 실패 / re-open failed: {type(e).__name__}"
    return out


def check_downloads(downloads: dict, root) -> list[dict]:
    """Response "downloads" ({"STEP": "gen/x.step", ...}) -> one check per file, relative to root (the web folder)."""
    root = Path(root)
    out = []
    for label, rel in (downloads or {}).items():
        if not rel or str(rel).startswith("http"):
            continue
        c = check_file(root / rel)                 # the kind comes from the file itself, not the button label
        c["label"] = label
        out.append(c)
    return out


def summary(checks: list[dict]) -> dict:
    bad = [c for c in checks if not c["ok"]]
    return {"ok": not bad, "checked": len(checks), "failed": [f"{c['file']} ({c['kind']}): {c['msg']}" for c in bad]}
