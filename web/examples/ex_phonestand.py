# Simple desk phone stand (base 85x72x6, back 70x6x90, angle 65 deg from horizontal)
# Backrest 65 deg = tilted back 25 deg from vertical, phone slot 12mm -> 12.4mm (0.2/side FDM shrink)
# Front lip 70x8x12 (on the base), cable groove 14 wide x 6 high (through the center), single PLA solid
from build123d import *
import math
tilt_deg = 25
tilt = math.radians(tilt_deg)
Tb = 6.0
Wb = 70.0
Lb = 90.0
Yb = -5.0
Zbot = 4.5
Zc = Zbot + (Lb / 2.0) * math.cos(tilt)
Yc = Yb + (Lb / 2.0) * math.sin(tilt)
slot = 12.4
Yfront = Yb - (Tb / 2.0) * math.cos(tilt)
Yrear_lip = Yfront - slot
Tl = 8.0
Ylip = Yrear_lip - Tl / 2.0
base = Pos(0, 0, 3) * Box(85, 72, 6)
back = Pos(0, Yc, Zc) * Rot(-tilt_deg, 0, 0) * Box(Wb, Tb, Lb)
lip_raw = Pos(0, Ylip, 4.5 + 13.5 / 2.0) * Box(70, Tl, 13.5)
cable = Pos(0, Ylip, 5 + 7 / 2.0) * Box(14, 10, 7)
lip = lip_raw - cable
part = base + back + lip