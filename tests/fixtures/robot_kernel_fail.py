# Toy robot figure 180mm tall on z=0 W106xD64xH180 (written by Muse Spark from a reference sheet).
# Its later unions make the CAD kernel fail with a Null shape, which the sandbox must survive in mesh mode.
# head 30x28x22 z148-170 top180 crest, chest 62x38x36 z112-148, hip 64x40x28 z88-116
# pauldrons 28 wide span106, arms, thigh28 shin30, feet 26x44x16 z0-16, pack 48x22x32
from build123d import *
import math
footL = Pos(19, 4, 8) * Box(26, 44, 16)
ankleL = Pos(19, 0, 19) * Cylinder(radius=7, height=14)
shinL = Pos(19, 0, 45) * Box(28, 30, 50)
kneeL = Pos(19, 16, 62) * Box(20, 10, 24)
thighL = Pos(19, 0, 85) * Box(28, 30, 40)
hip = Pos(0, 0, 102) * Box(64, 40, 28)
thighR = Pos(-19, 0, 85) * Box(28, 30, 40)
kneeR = Pos(-19, 16, 62) * Box(20, 10, 24)
shinR = Pos(-19, 0, 45) * Box(28, 30, 50)
ankleR = Pos(-19, 0, 19) * Cylinder(radius=7, height=14)
footR = Pos(-19, 4, 8) * Box(26, 44, 16)
skirtF = Pos(0, 20, 96) * Box(16, 8, 24)
skirtL = Pos(24, 8, 96) * Box(18, 24, 22)
skirtR = Pos(-24, 8, 96) * Box(18, 24, 22)
chest = Pos(0, 0, 130) * Box(62, 38, 36)
chestFront = Pos(0, 19, 130) * Box(20, 8, 20)
pack = Pos(0, -27, 132) * Box(48, 22, 32)
thrL = Pos(15, -31, 112) * Cylinder(radius=8, height=16)
thrR = Pos(-15, -31, 112) * Cylinder(radius=8, height=16)
neck = Pos(0, 0, 148) * Cylinder(radius=6, height=12)
headMain = Pos(0, 1, 159) * Box(30, 28, 22)
headRound = Pos(0, 0, 162) * Sphere(radius=16)
chin = Pos(0, 13, 151) * Box(12, 8, 10)
crest = Pos(0, 0, 173) * Box(10, 30, 14)
antL = Pos(12, 0, 167) * Cylinder(radius=2.5, height=24)
antR = Pos(-12, 0, 167) * Cylinder(radius=2.5, height=24)
paulL = Pos(39, 0, 133) * Box(28, 34, 32)
uarmL = Pos(39, 0, 113) * Box(16, 18, 30)
elbL = Pos(39, 0, 99) * Cylinder(radius=7.5, height=14)
farmL = Pos(41, 0, 80) * Box(22, 24, 34)
fistL = Pos(41, 2, 60) * Box(14, 16, 18)
paulR = Pos(-39, 0, 133) * Box(28, 34, 32)
uarmR = Pos(-39, 0, 113) * Box(16, 18, 30)
elbR = Pos(-39, 0, 99) * Cylinder(radius=7.5, height=14)
farmR = Pos(-41, 0, 80) * Box(22, 24, 34)
fistR = Pos(-41, 2, 60) * Box(14, 16, 18)
part = footL
part = part + ankleL
part = part + shinL
part = part + kneeL
part = part + thighL
part = part + footR
part = part + ankleR
part = part + shinR
part = part + kneeR
part = part + thighR
part = part + hip
part = part + skirtF
part = part + skirtL
part = part + skirtR
part = part + chest
part = part + chestFront
part = part + pack
part = part + thrL
part = part + thrR
part = part + neck
part = part + headMain
part = part + headRound
part = part + chin
part = part + crest
part = part + antL
part = part + antR
part = part + paulL
part = part + uarmL
part = part + elbL
part = part + farmL
part = part + fistL
part = part + paulR
part = part + uarmR
part = part + elbR
part = part + farmR
part = part + fistR