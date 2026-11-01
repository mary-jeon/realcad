# Wall hook 45(X)x32(Z)x5(Y) plate back Y0 front Y5, holes 2x M4 nom D4.5->D4.7 (0.2 FDM)
# Hook D8(r4) root Z10 to Y36 +up to Z30, outer Y40 = 35mm from front, tip sphere
# PLA 0.4 nozzle, one fused solid, csk D8.7 depth2 front
from build123d import *
plate = Pos(0, 2.5, 16) * Box(45, 5, 32)
boss = Pos(0, 3, 10) * Rot(90, 0, 0) * Cylinder(radius=7, height=6)
rib = Pos(0, 13, 5) * Box(6, 20, 10)
horiz = Pos(0, 18, 10) * Rot(90, 0, 0) * Cylinder(radius=4, height=36)
elbow = Pos(0, 36, 10) * Sphere(radius=4)
vert = Pos(0, 36, 20) * Cylinder(radius=4, height=20)
tip = Pos(0, 36, 30) * Sphere(radius=4)
base = plate + boss + rib + horiz + elbow + vert + tip
for x in (-15, 15):
    cut = Pos(x, 2.5, 16) * Rot(90, 0, 0) * Cylinder(radius=2.35, height=12)
    base = base - cut
    csk = Pos(x, 4, 16) * Rot(-90, 0, 0) * Cone(bottom_radius=2.35, top_radius=4.35, height=2.0)
    base = base - csk
part = base