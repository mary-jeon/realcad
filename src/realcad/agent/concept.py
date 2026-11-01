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


def iou(a: np.ndarray, b: np.ndarray) -> float:
    """Outline overlap after scaling both to the same height and centring them (mirror is tried too)."""
    if not a.any() or not b.any():
        return 0.0
    A, B = _norm(a), _norm(b)
    best = 0.0
    for BB in (B, B[:, ::-1]):
        w = max(A.shape[1], BB.shape[1])
        pa = np.zeros((_SIZE, w), bool); pb = np.zeros((_SIZE, w), bool)
        oa, ob = (w - A.shape[1]) // 2, (w - BB.shape[1]) // 2
        pa[:, oa:oa + A.shape[1]] = A
        pb[:, ob:ob + BB.shape[1]] = BB
        best = max(best, float((pa & pb).sum()) / max(float((pa | pb).sum()), 1.0))
    return best


def score(sheet_png, stl) -> dict | None:
    """{"front": 0..1, "side": 0..1} for the built part against the reference sheet, or None."""
    try:
        ref = sheet_masks(sheet_png)
        if ref is None:
            return None
        front, side = part_masks(stl)
        return {"front": round(iou(ref[0], front), 2), "side": round(iou(ref[1], side), 2)}
    except Exception:
        return None


def low(sc: dict | None) -> bool:
    return bool(sc) and min(sc["front"], sc["side"]) < IOU_MIN
