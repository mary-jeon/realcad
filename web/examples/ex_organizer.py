# Tray 150x100x45mm, wall 2mm, floor 2mm
# Interior 146x96x43mm, dividers 2mm x2 along Y, 3 compartments X ~47.33mm each
# FDM hole oversize 0.2mm N/A - no holes in this part
from build123d import *
outer = Pos(0, 0, 22.5) * Box(150, 100, 45)
inner = Pos(0, 0, 27) * Box(146, 96, 50)
tray = outer - inner
d1 = Pos(-24.6666667, 0, 22.75) * Box(2, 99, 44.5)
d2 = Pos(24.6666667, 0, 22.75) * Box(2, 99, 44.5)
part = tray + d1 + d2