"""또렷한 3D 렌더(음영+모서리). 데모·텔레그램 미리보기용. (실시간 뷰어는 웹의 three.js)"""
from __future__ import annotations
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def _shaded(ax, mesh, color, alpha=1.0, light=(0.4, 0.55, 0.9), edge=True):
    n = mesh.face_normals
    l = np.array(light, float); l /= np.linalg.norm(l)
    inten = 0.42 + 0.58 * np.clip(n @ l, 0, 1)          # 면 법선 기반 음영
    base = np.array(mcolors.to_rgb(color))
    fc = np.clip(base[None, :] * inten[:, None], 0, 1)
    pc = Poly3DCollection(mesh.vertices[mesh.faces], facecolors=fc,
                          edgecolors=("#1a1a1a" if edge else "none"),
                          linewidths=0.3, alpha=alpha)
    ax.add_collection3d(pc)


def render(parts, path, title="", elev=26, azim=-58, edges=False):
    """parts: [(trimesh, color, alpha), ...]"""
    fig = plt.figure(figsize=(8, 6))
    ax = fig.add_subplot(111, projection="3d")
    allv = np.vstack([m.vertices for m, _, _ in parts])
    for m, c, a in parts:
        _shaded(ax, m, c, alpha=a, edge=edges)
    mn, mx = allv.min(0), allv.max(0)
    ctr = (mn + mx) / 2
    r = (mx - mn).max() / 2 * 1.05
    ax.set_xlim(ctr[0] - r, ctr[0] + r)
    ax.set_ylim(ctr[1] - r, ctr[1] + r)
    ax.set_zlim(ctr[2] - r, ctr[2] + r)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    if title:
        ax.set_title(title, fontsize=11)
    plt.tight_layout()
    plt.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path
