"""Visual review: render the result in 4 views, show it to the vision model, and ask whether it matches
the request and whether any part is missing, buried, or facing the wrong way.

Catches cases where the code runs and checks pass but the shape differs from the request (a face looking
backward, a laptop screen buried in the body). The kernel checks "was it built"; this step checks "is it what was asked".
"""
from __future__ import annotations
import base64
import json
import math
import re
import tempfile
from pathlib import Path

from .meta_client import chat

# View convention: Z up, viewer on the -Y side (front). Same as the RealCAD 3D view and the 3-view PDF.
_VIEWS = [
    ("FRONT (viewer at -Y, looking +Y)", (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    ("RIGHT (viewer at +X, looking -X)", (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    ("TOP (viewer above, looking down)", (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
    ("ISO (front-right-top)", (-0.577, 0.577, -0.577), (0.0, 0.0, 1.0)),
]


def _norm(v):
    m = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / m for c in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _mesh(step_path=None, stl_path=None):
    """Coarse mesh for rendering (fast). Re-tessellate from STEP if present, else use the STL."""
    import trimesh
    if step_path and Path(step_path).exists():
        from build123d import import_step, export_stl
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "r.stl"
            export_stl(import_step(str(step_path)), str(p), tolerance=0.25, angular_tolerance=0.35)
            return trimesh.load(str(p), force="mesh")
    return trimesh.load(str(stl_path), force="mesh")


def render_views(png_path, step_path=None, stl_path=None, title: str = "") -> Path | None:
    """One 2x2 shaded image of 4 views. None on failure."""
    try:
        import numpy as np
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.collections import PolyCollection
        m = _mesh(step_path, stl_path)
        if not hasattr(m, "faces") or len(m.faces) == 0:
            return None
        V = np.asarray(m.vertices, float); F = np.asarray(m.faces); N = np.asarray(m.face_normals, float)
        V = V - (V.min(0) + V.max(0)) / 2
        fig, axes = plt.subplots(2, 2, figsize=(10, 8), facecolor="#ffffff")
        for ax, (label, d, up) in zip(axes.ravel(), _VIEWS):
            d = np.array(_norm(d)); up = np.array(_norm(up))
            right = np.array(_norm(_cross(d, up)))
            upv = np.cross(right, d)
            uv = np.stack([V @ right, V @ upv], 1)
            depth = (V @ d)[F].mean(1)
            facing = N @ d < 0                      # only faces toward the viewer
            light = np.array(_norm(tuple(-d * 0.8 + upv * 0.6)))
            inten = 0.30 + 0.70 * np.clip(N @ light, 0, 1)
            idx = np.where(facing)[0]
            idx = idx[np.argsort(-depth[idx])]       # far to near (painter's algorithm)
            polys = uv[F[idx]]
            base = np.array([0.36, 0.56, 0.78])
            cols = np.clip(base[None, :] * inten[idx, None] + 0.08, 0, 1)
            ax.add_collection(PolyCollection(polys, facecolors=cols, edgecolors=cols, linewidths=0.2))
            lo, hi = uv.min(0), uv.max(0); pad = (hi - lo).max() * 0.06 + 1
            ax.set_xlim(lo[0] - pad, hi[0] + pad); ax.set_ylim(lo[1] - pad, hi[1] + pad)
            ax.set_aspect("equal"); ax.axis("off"); ax.set_title(label, fontsize=11)
        if title and title.isascii():                 # without a Korean font the glyphs render as boxes and only confuse the model
            fig.suptitle(title[:90], fontsize=10)
        plt.tight_layout()
        png_path = Path(png_path); fig.savefig(str(png_path), dpi=90); plt.close(fig)
        return png_path
    except Exception:
        return None


REVIEW_SYSTEM = """You are a strict CAD design reviewer for a prompt-to-CAD tool. You get the user's request,
the build123d code that was run, and ONE image with 4 shaded renders of the result:
FRONT (viewer stands at -Y), RIGHT (viewer at +X), TOP (from above), ISO (front-right-top). Z is up.
Judge ONLY big, visible mismatches with the request:
- a requested component is missing or hidden/buried inside another part
- something faces the wrong way (e.g. a face, screen, or opening that should face the viewer faces away)
- a part floats, sticks out absurdly, or proportions are clearly wrong for what was asked
Ignore faceting, smoothness, colour, tiny cosmetic details, and anything the request did not ask for.
If it reasonably matches, say so: do not invent problems.
Return ONLY JSON:
{"matches": true|false,
 "problems": ["short concrete problem, written in plain Korean, use commas (never the middle dot or dashes)", ...],
 "fix": "concrete code-level instructions in English that name the variables and coordinates to change"}"""


def _png_data_url(p) -> str:
    return "data:image/png;base64," + base64.b64encode(Path(p).read_bytes()).decode()


def _parse(text: str) -> dict:
    t = (text or "").strip()
    m = re.search(r"\{.*\}", t, re.S)
    try:
        d = json.loads(m.group(0) if m else t)
    except Exception:
        return {"matches": True, "problems": [], "fix": "", "unparsed": t[:300]}
    clean = lambda x: re.sub(r"\s*[·—]\s*", ", ", str(x)).strip()[:160]   # on-screen text uses commas instead of middle dots and dashes
    probs = [clean(x) for x in (d.get("problems") or []) if str(x).strip()][:6]
    return {"matches": bool(d.get("matches", not probs)) and not probs, "problems": probs, "fix": str(d.get("fix") or "")[:2500]}


def review_once(request: str, code: str, png_path, ref_image_url: str | None = None, extra: str = "") -> dict:
    """One 4-view image + request + code -> {"matches", "problems" (Korean), "fix" (English)}."""
    content = [{"type": "text", "text": f"User request:\n{request[:3000]}\n\nbuild123d code that was run:\n{code[:8000]}\n\n"
                                        "Rendered result (4 views in one image):"},
               {"type": "image_url", "image_url": {"url": _png_data_url(png_path)}}]
    if ref_image_url:
        content += [{"type": "text", "text": "Reference image the user gave (match its look and layout):"},
                    {"type": "image_url", "image_url": {"url": ref_image_url}}]
    if extra:
        content.append({"type": "text", "text": extra})
    out, _usage = chat([{"role": "system", "content": REVIEW_SYSTEM}, {"role": "user", "content": content}],
                       json_mode=True, temperature=0.0, max_tokens=6000)
    return _parse(out)


def fix_note(rv: dict) -> str:
    """Visual review result -> code fix request (goes in the error slot of the auto-repair loop)."""
    probs = "\n".join(f"- {p}" for p in rv.get("problems") or [])
    return ("The code RAN and passed the geometry checks, but a visual review of the rendered result "
            "(4 views) found these problems:\n" + probs +
            ("\nSuggested fix: " + rv["fix"] if rv.get("fix") else "") +
            "\nFix ONLY these problems. Keep every other part, size and position the same. "
            "Keep ONE fused watertight solid with a flat bottom.")
