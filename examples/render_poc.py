"""PoC 시각화: 불량(볼트 머리가 벽에 박힘) vs 수정(볼트가 깔끔히 앉음) 렌더 PNG."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import trimesh

from realcad.fasteners.standards import get
from realcad.geometry import builder as g
from realcad.export import exporters as ex

L, W, T = 80.0, 50.0, 6.0
WALL_X, WALL_T, WALL_H = 30.0, 6.0, 25.0
f = get("1/4-20")
out = Path(__file__).resolve().parents[1] / "out"
out.mkdir(exist_ok=True)


def bracket():
    return g.plate(L, W, T) + g.wall(WALL_X, W, WALL_H, WALL_T)


def scene_stls(tag, holes, hole_dia):
    part = bracket()
    for (x, y) in holes:
        part = g.drill(part, x, y, hole_dia, T)
    bolts = None
    for (x, y) in holes:
        b = g.place(g.hex_bolt_solid(f, 20), x, y)
        bolts = b if bolts is None else bolts + b
    ex.to_stl(part, out / f"{tag}_bracket.stl")
    ex.to_stl(bolts, out / f"{tag}_bolts.stl")


scene_stls("naive", [(34.0, 0.0)], f.nominal_dia_mm)
scene_stls("fixed", [(10.0, 12.0), (10.0, -12.0)], f.clearance("normal"))


def add(ax, path, color, alpha):
    m = trimesh.load(str(path))
    pc = Poly3DCollection(m.vertices[m.faces], alpha=alpha, facecolors=color,
                          edgecolors="none")
    ax.add_collection3d(pc)


fig = plt.figure(figsize=(12, 5))
for i, (tag, title) in enumerate([("naive", "NAIVE: bolt head hits wall  (H1/H2/H4 FAIL)"),
                                  ("fixed", "FIXED: no interference  (VERIFIED -> STEP/STL)")], 1):
    ax = fig.add_subplot(1, 2, i, projection="3d")
    add(ax, out / f"{tag}_bracket.stl", "#aebfcc", 0.4)
    add(ax, out / f"{tag}_bolts.stl", "#d1495b", 1.0)
    ax.set_title(title, fontsize=11)
    ax.set_box_aspect((L, W, 40))
    ax.set_xlim(-45, 45); ax.set_ylim(-28, 28); ax.set_zlim(-8, 30)
    ax.view_init(elev=22, azim=-60); ax.set_axis_off()

plt.tight_layout()
png = out / "poc_compare.png"
plt.savefig(png, dpi=130, bbox_inches="tight")
print(f"saved {png}")
