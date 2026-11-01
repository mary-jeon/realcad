# Holder cup: outer D80xH100, wall 2.5, closed 3 floor (watertight), open top
# Nominal inner D75 + FDM shrink 0.2 -> D75.2 (R37.6), effective wall 2.4
# FDM PLA nozzle 0.4, meets 0.8 min wall, Z0 flat on the bed
from build123d import *
Ro=40.0
H=100.0
wall_nom=2.5
floor_t=3.0
Ri=(80.0-2.0*wall_nom+0.2)/2.0
outer=Cylinder(radius=Ro,height=H,align=(Align.CENTER,Align.CENTER,Align.MIN))
inner_tool=Cylinder(radius=Ri,height=H,align=(Align.CENTER,Align.CENTER,Align.MIN))
inner=Pos(0,0,floor_t)*inner_tool
part=outer-inner
part=fillet(part.edges().group_by(Axis.Z)[1],radius=2.0)
part=chamfer(part.edges().group_by(Axis.Z)[-1],length=0.8)
part=chamfer(part.edges().group_by(Axis.Z)[0],length=0.8)