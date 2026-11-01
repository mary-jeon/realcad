# base plate 60x40x9mm, M3 insert x4
# M3 insert hole nominal D4.0 depth 6.7 (5.7+1) floor 2.3mm -> FDM +0.2 = D4.2
# hole centers 6mm inset from edges -> x=+-24 y=+-14
# countersink 0.5mm chamfer at hole entrance, walls 3.9mm edge distance
from build123d import *
plate = Pos(0, 0, 4.5) * Box(60, 40, 9)
hole_r = 4.2 / 2
hole_depth = 6.7
hole_bottom = 9 - hole_depth
cyl_h = hole_depth + 1.0
cyl_zc = hole_bottom + cyl_h / 2
csk_h = 0.8
csk_bottom_r = hole_r
csk_top_r = hole_r + 0.5
csk_zc = 9 - csk_h / 2 + 0.1
part = plate
for sx in (-1, 1):
    for sy in (-1, 1):
        x = sx * 24
        y = sy * 14
        cyl = Pos(x, y, cyl_zc) * Cylinder(radius=hole_r, height=cyl_h)
        csk = Pos(x, y, csk_zc) * Cone(bottom_radius=csk_bottom_r, top_radius=csk_top_r, height=csk_h)
        part = part - cyl - csk