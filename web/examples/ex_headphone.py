# Headphone stand: total height 280mm (incl. base) x base D110 x top 120mm
# Base: D110xH16 solid + 4 ribs (4x30x30) at the bottom center / post: 30x26x250 (z14-264)
# Top: plate 120x38x10 + cushion R19xL120 (top at 280) + retaining lip 6x38x12
# Cable hole nominal D12 -> D12.2 (0.2 shrink) / design wall >= 3mm (meets nozzle 0.4, min 0.8)
from build123d import *
import math
base = Pos(0, 0, 8) * Cylinder(radius=55, height=16)
column = Pos(0, 0, 139) * Box(30, 26, 250)
fin_f = Pos(0, 13, 29) * Box(4, 30, 30)
fin_b = Pos(0, -13, 29) * Box(4, 30, 30)
fin_l = Pos(13, 0, 29) * Box(30, 4, 30)
fin_r = Pos(-13, 0, 29) * Box(30, 4, 30)
top_plate = Pos(0, 0, 267) * Box(120, 38, 10)
cush_full = Pos(0, 0, 261) * Rot(0, 90, 0) * Cylinder(radius=19, height=120)
cush_box = Pos(0, 0, 271) * Box(120, 38, 18)
cush = cush_full & cush_box
stop_l = Pos(57, 0, 276) * Box(6, 38, 12)
stop_r = Pos(-57, 0, 276) * Box(6, 38, 12)
solid = base + column + fin_f + fin_b + fin_l + fin_r + top_plate + cush + stop_l + stop_r
try:
    solid = fillet(solid.edges().filter_by(Axis.Z), radius=1.5)
except Exception:
    pass
hole_tool = Pos(0, 0, 60) * Rot(90, 0, 0) * Cylinder(radius=6.1, height=60)
part = solid - hole_tool