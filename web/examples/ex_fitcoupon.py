# Coupon 60x25x4mm, top z=4, pins 10mm above (total 14mm)
# Holes nominal D3,4,5,6,8 -> modeled D+0.2 (3.2,4.2,5.2,6.2,8.2) through Z
# Hole pitch 11mm at x=-22,-11,0,11,22 y=-6; pin D5-0.1/0.2/0.3/0.4=4.9,4.8,4.7,4.6 at x=-16.5,-5.5,5.5,16.5 y=6.5 h=10
# Grooves: hole ID 3/4/5/6/8 ticks, pin ID 1/2/3/4 ticks, w0.8 d0.7 l2.5/1.8 top engrave
from build123d import *
plate = Pos(0, 0, 2) * Box(60, 25, 4)
pin_xs = [-16.5, -5.5, 5.5, 16.5]
pin_ds = [4.9, 4.8, 4.7, 4.6]
pin_y = 6.5
body = plate
for px, pd in zip(pin_xs, pin_ds):
    pin = Pos(px, pin_y, 2) * Cylinder(radius=pd / 2, height=12)
    body = body + pin
hole_ds = [3, 4, 5, 6, 8]
hole_xs = [-22, -11, 0, 11, 22]
hole_y = -6
for hx, hd in zip(hole_xs, hole_ds):
    body = body - Pos(hx, hole_y, 2) * Cylinder(radius=(hd + 0.2) / 2, height=10)
for hx, hd in zip(hole_xs, hole_ds):
    n = int(hd)
    for j in range(n):
        tx = hx + (j - (n - 1) / 2) * 1.5
        body = body - Pos(tx, 0.5, 3.8) * Box(0.8, 2.5, 1.0)
for k, px in enumerate(pin_xs):
    n = k + 1
    for j in range(n):
        tx = px + (j - (n - 1) / 2) * 1.5
        body = body - Pos(tx, 10.8, 3.8) * Box(0.8, 1.8, 1.0)
part = body