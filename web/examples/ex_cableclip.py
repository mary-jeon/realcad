# Cable holder 25x16x13mm, base 25x16x4mm, 3x C-clips
# Cable Dia5.0 -> hole Dia5.2 (+0.2 FDM shrink), pitch 8mm, slot 3.5mm
# Walls >=1.9mm, PLA, no screws
from build123d import *
base = Pos(0,0,2) * Box(25,16,4)
top = Pos(0,0,8.5) * Box(25,10,9)
part = base + top
hole_r = 2.6
zc = 8.5
xs = [-8,0,8]
for x in xs:
    cyl = Pos(x,0,zc) * Rot(90,0,0) * Cylinder(radius=hole_r, height=14)
    part = part - cyl
for x in xs:
    slot = Pos(x,0,11.25) * Box(3.5,14,5.5)
    part = part - slot
for x in xs:
    for s in (-1,1):
        flare = Pos(x,s*4.6,zc) * Rot(90,0,0) * Cylinder(radius=3.1, height=1.2)
        part = part - flare