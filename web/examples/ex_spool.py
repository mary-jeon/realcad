# Spool holder: rod D50xL110 fused, legs trapezoid base120 top80 H136 t8
# Feet 30x120x6, axle Z101, spool D200 clears 1mm, PLA nozzle 0.4mm
# Rod fused to legs = 1 solid (spool bore clearance not modeled)
from build123d import *
axle_Z = 101
left_plane = Plane(origin=(-55, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
right_plane = Plane(origin=(47, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
left_face = left_plane * Polygon((-60, 4.5), (60, 4.5), (40, 136), (-40, 136))
right_face = right_plane * Polygon((-60, 4.5), (60, 4.5), (40, 136), (-40, 136))
left_plate = extrude(left_face, amount=8)
right_plate = extrude(right_face, amount=8)
left_boss_face = Plane(origin=(-58, 0, axle_Z), x_dir=(0, 1, 0), z_dir=(1, 0, 0)) * Circle(35)
right_boss_face = Plane(origin=(44, 0, axle_Z), x_dir=(0, 1, 0), z_dir=(1, 0, 0)) * Circle(35)
left_boss = extrude(left_boss_face, amount=14)
right_boss = extrude(right_boss_face, amount=14)
left_foot = Pos(-51, 0, 0) * Box(30, 120, 6, align=(Align.CENTER, Align.CENTER, Align.MIN))
right_foot = Pos(51, 0, 0) * Box(30, 120, 6, align=(Align.CENTER, Align.CENTER, Align.MIN))
rod_face = Plane(origin=(-55, 0, axle_Z), x_dir=(0, 1, 0), z_dir=(1, 0, 0)) * Circle(25)
rod = extrude(rod_face, amount=110)
part = left_plate + left_boss + left_foot + right_plate + right_boss + right_foot + rod