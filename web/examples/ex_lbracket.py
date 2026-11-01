# L-bracket 45x32x45mm wings 45Lx32Wx5T central tri-rib leg30x5T
# Holes nominal D4.5 -> modeled D4.7 (+0.2 dia FDM shrink, r2.35)
# ISO4014 M4 ref d4 AF7 hh2.8 / M6 d6 AF10 hh4 L20; bracket suits M4
# Single solid L-angle, 2 holes/wing diagonal (15,8)-(35,24) to clear rib
from build123d import *
import math
horiz = Pos(22.5, 16, 2.5) * Box(45, 32, 5)
vert = Pos(2.5, 16, 22.5) * Box(5, 32, 45)
with BuildPart() as rb:
    with BuildSketch(Plane(origin=(5, 16, 5), z_dir=(0, 1, 0))):
        with BuildLine():
            Line((0, 0), (30, 0))
            Line((30, 0), (0, 30))
            Line((0, 30), (0, 0))
        make_face()
    extrude(amount=2.5, both=True)
rib = rb.part
base = horiz + vert + rib
hr = 2.35
csr = 3.05
csh = 0.8
hpts = [(15, 8), (35, 24)]
vpts = [(8, 15), (24, 35)]
cut = None
for px, py in hpts:
    c = Pos(px, py, 2.5) * Cylinder(radius=hr, height=20)
    cut = c if cut is None else cut + c
    ct = Pos(px, py, 4.6) * Cone(bottom_radius=hr, top_radius=csr, height=csh)
    cb = Pos(px, py, 0.4) * Cone(bottom_radius=csr, top_radius=hr, height=csh)
    cut = cut + ct + cb
for py, pz in vpts:
    c = Pos(2.5, py, pz) * Rot(0, 90, 0) * Cylinder(radius=hr, height=20)
    cut = cut + c
    co = Pos(0.4, py, pz) * Rot(0, 90, 0) * Cone(bottom_radius=csr, top_radius=hr, height=csh)
    ci = Pos(4.6, py, pz) * Rot(0, 90, 0) * Cone(bottom_radius=hr, top_radius=csr, height=csh)
    cut = cut + co + ci
part = base - cut