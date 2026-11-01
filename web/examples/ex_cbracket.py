# Bracket plate 100x50x10mm, 2x holes pitch 70mm (x=+-35, y=0)
# M5 ISO4014: d=5 AF=8 hh=3.5, shank L default 20 (holes only, bolts not modeled)
# FDM shrink +0.2 on diameters: shank hole D5.2, hex corner 9.24 -> round counterbore D10.0 depth 5.0 (head buried 1.5 below top)
# PLA 0.4 nozzle min wall 0.8, plate walls >5, watertight single solid, bottom z=0
from build123d import *
plate = Box(100, 50, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
for x in (-35, 35):
    plate = plate - Pos(x, 0, -1) * Cylinder(radius=5.2 / 2, height=12, align=(Align.CENTER, Align.CENTER, Align.MIN))
    plate = plate - Pos(x, 0, 5) * Cylinder(radius=10.0 / 2, height=5.5, align=(Align.CENTER, Align.CENTER, Align.MIN))
part = plate
part = chamfer(part.edges().filter_by(GeomType.CIRCLE).group_by(Axis.Z)[-1], length=0.5)