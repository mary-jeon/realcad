"""Concept sheet for shapes with no fixed dimensions (figures, animals, characters).

Meta Muse Image draws a front + side reference sheet, Muse Spark builds the part while looking at it,
and the outline of the sheet is compared with the outline of the built part (silhouette IoU, 1.0 = identical).
"""
from __future__ import annotations

import base64
import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import meta_client

STYLE = ("Reference sheet for a 3D printable figure: the same object twice, FRONT view on the left and SIDE view "
         "on the right, side by side, both full body and the same height, plain pure white background, flat even "
         "lighting, no shadow on the ground, simple chunky printable shapes, no text, no labels, no weapons.")

IOU_MIN = 0.7          # below this the outline is treated as not matching the sheet
_SIZE = 200            # outlines are compared at this height in pixels


def draw(request: str, out_png) -> Path:
    """Request text -> reference sheet PNG (one Muse Image call)."""
    p = Path(out_png)
    p.write_bytes(meta_client.image(f"{request.strip()}. {STYLE}"))
    return p


def data_url(png, max_px: int = 1024) -> str:
    """Reference sheet -> JPEG data URL small enough for the vision model."""
    im = Image.open(png).convert("RGB")
    im.thumbnail((max_px, max_px))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _fill(mask: np.ndarray) -> np.ndarray:
    try:
        from scipy.ndimage import binary_fill_holes
        return binary_fill_holes(mask)
    except Exception:
        return mask


def _runs(flags) -> list[tuple[int, int]]:
    out, start = [], None
    for i, f in enumerate(list(flags) + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            out.append((start, i)); start = None
    return out


def sheet_masks(png) -> tuple[np.ndarray, np.ndarray] | None:
    """Reference sheet -> (front mask, side mask), split at the empty gap between the two drawings."""
    im = np.asarray(Image.open(png).convert("RGB")).astype(np.int16)
    fg = np.abs(im - 255).max(axis=2) > 28
    cols = fg.sum(axis=0) > max(2, int(fg.shape[0] * 0.004))
    runs = _runs(cols)
    gap = max(3, int(fg.shape[1] * 0.004))     # the two drawings can sit very close (a tail reaching toward the other view)
    merged: list[list[int]] = []
    for a, b in runs:
        if merged and a - merged[-1][1] < gap:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    merged = [r for r in merged if r[1] - r[0] > fg.shape[1] * 0.05]
    if len(merged) < 2:
        return None
    merged.sort(key=lambda r: r[1] - r[0], reverse=True)
    left, right = sorted(merged[:2])
    return _fill(fg[:, left[0]:left[1]]), _fill(fg[:, right[0]:right[1]])


def _project(m, axes: tuple[int, int], px: int = 400) -> np.ndarray:
    v = np.asarray(m.vertices)[:, axes]
    mn, mx = v.min(axis=0), v.max(axis=0)
    s = (px - 4) / max(float((mx - mn).max()), 1e-6)
    w, h = int((mx[0] - mn[0]) * s) + 5, int((mx[1] - mn[1]) * s) + 5
    img = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(img)
    for tri in v[np.asarray(m.faces)]:
        d.polygon([(float((x - mn[0]) * s + 2), float(h - ((y - mn[1]) * s + 2))) for x, y in tri], fill=255)
    return np.asarray(img) > 127


def part_masks(stl) -> tuple[np.ndarray, np.ndarray]:
    """Built part -> (front outline seen from -Y, side outline seen from +X)."""
    import trimesh
    m = trimesh.load(str(stl), force="mesh")
    return _project(m, (0, 2)), _project(m, (1, 2))


def _norm(mask: np.ndarray) -> np.ndarray:
    ys, xs = np.nonzero(mask)
    crop = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = crop.shape
    im = Image.fromarray((crop * 255).astype(np.uint8)).resize((max(1, round(w * _SIZE / h)), _SIZE), Image.NEAREST)
    return np.asarray(im) > 127


def _aligned(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Scale both outlines to the same height, centre them, try b mirrored too; return the best pair and its IoU."""
    A, B = _norm(a), _norm(b)
    best = (None, None, -1.0)
    for BB in (B, B[:, ::-1]):
        w = max(A.shape[1], BB.shape[1])
        pa = np.zeros((_SIZE, w), bool); pb = np.zeros((_SIZE, w), bool)
        oa, ob = (w - A.shape[1]) // 2, (w - BB.shape[1]) // 2
        pa[:, oa:oa + A.shape[1]] = A
        pb[:, ob:ob + BB.shape[1]] = BB
        v = float((pa & pb).sum()) / max(float((pa | pb).sum()), 1.0)
        if v > best[2]:
            best = (pa, pb, v)
    return best


def iou(a: np.ndarray, b: np.ndarray) -> float:
    """Outline overlap after scaling both to the same height and centring them (mirror is tried too)."""
    if not a.any() or not b.any():
        return 0.0
    return _aligned(a, b)[2]


def _pairs(sheet_png, stl):
    ref = sheet_masks(sheet_png)
    if ref is None:
        return None
    front, side = part_masks(stl)
    return {"front": _aligned(ref[0], front), "side": _aligned(ref[1], side)}


def score(sheet_png, stl) -> dict | None:
    """{"front": 0..1, "side": 0..1} for the built part against the reference sheet, or None."""
    try:
        pr = _pairs(sheet_png, stl)
        return {k: round(v[2], 2) for k, v in pr.items()} if pr else None
    except Exception:
        return None


def diff_png(sheet_png, stl, out_png) -> Path | None:
    """Overlay of the two outlines for each view: grey = both, red = in the sheet but missing in the part,
    blue = in the part but not in the sheet. This is what the repair request looks at."""
    try:
        pr = _pairs(sheet_png, stl)
        if not pr:
            return None
        panels = []
        for name in ("front", "side"):
            ref, part, v = pr[name]
            img = np.full(ref.shape + (3,), 255, np.uint8)
            img[ref & part] = (150, 150, 150)
            img[ref & ~part] = (220, 40, 40)
            img[part & ~ref] = (40, 90, 220)
            im = Image.fromarray(img).resize((ref.shape[1] * 2, ref.shape[0] * 2), Image.NEAREST)
            canvas = Image.new("RGB", (im.width + 20, im.height + 34), "white")
            canvas.paste(im, (10, 30))
            ImageDraw.Draw(canvas).text((10, 8), f"{name.upper()}  match {round(v * 100)}%  red=missing  blue=extra", fill="black")
            panels.append(canvas)
        W = sum(p.width for p in panels) + 10
        out = Image.new("RGB", (W, max(p.height for p in panels)), "white")
        x = 0
        for p in panels:
            out.paste(p, (x, 0)); x += p.width + 10
        out.save(out_png)
        return Path(out_png)
    except Exception:
        return None


def profile_text(sheet_png, stl, tol: float = 0.12) -> str:
    """Width of the outline at nine heights, sheet vs part, as a share of the height. Only rows that differ are listed."""
    try:
        pr = _pairs(sheet_png, stl)
    except Exception:
        pr = None
    if not pr:
        return ""
    lines = []
    for name in ("front", "side"):
        ref, part, _v = pr[name]
        H = ref.shape[0]
        for f in (0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1):
            row = H - 1 - int(f * (H - 1))
            def width(m):
                xs = np.nonzero(m[row])[0]
                return (xs.max() - xs.min() + 1) / H if xs.size else 0.0
            wr, wp = width(ref), width(part)
            if wr > 0.02 and abs(wp - wr) / wr > tol:
                lines.append(f"{name.upper()} at {round(f * 100)}% height: sheet width {wr:.2f}H, part {wp:.2f}H "
                             f"({'too narrow' if wp < wr else 'too wide'} by {round(abs(wp - wr) / wr * 100)}%)")
            elif wr <= 0.02 < wp:
                lines.append(f"{name.upper()} at {round(f * 100)}% height: the sheet is empty here but the part sticks out")
    return "\n".join(lines[:14])


def low(sc: dict | None) -> bool:
    return bool(sc) and min(sc["front"], sc["side"]) < IOU_MIN
