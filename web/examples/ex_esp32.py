# ESP32 DevKit 51.5x28, holes 3mm inset 4x M2.5 -> modeled D2.7 (+0.2 FDM)
# Cavity 51.9x28.4 (0.2/side), outer 55.9x32.4, floor2 wall2 pillar-OD6xH4, board1.6+top18=total25.6
# Open long wall Y- (51.5 side) for USB + USB slot 12x8 on X- short wall, ISO4014 holes-only
from build123d import *
BW,BD=51.5,28.0
inset=3.0
hole_nom=2.5
hole_d=hole_nom+0.2
CW,BWc=BW+0.4,BD+0.4
CW,CD=51.9,28.4
t_wall=2.0
t_floor=2.0
p_h=4.0
p_od=6.0
board_t=1.6
top_space=18.0
Htot=t_floor+p_h+board_t+top_space
Wh=Htot-t_floor
OW=CW+2*t_wall
OD=CD+2*t_wall
floor=Box(OW,OD,t_floor)
x_wall=CW/2+t_wall/2
wall_xp=Pos(x_wall,0,t_floor)*Box(t_wall,OD,Wh)
wall_xm=Pos(-x_wall,0,t_floor)*Box(t_wall,OD,Wh)
y_wall=CD/2+t_wall/2
wall_yp=Pos(0,y_wall,t_floor)*Box(OW,t_wall,Wh)
hx=(BW-2*inset)/2
hy=(BD-2*inset)/2
pillars=None
for sx in (-1,1):
    for sy in (-1,1):
        c=Pos(sx*hx,sy*hy,t_floor)*Cylinder(radius=p_od/2,height=p_h)
        pillars=c if pillars is None else pillars+c
body=floor+wall_xp+wall_xm+wall_yp+pillars
cuts=None
for sx in (-1,1):
    for sy in (-1,1):
        h=Pos(sx*hx,sy*hy,1.0)*Cylinder(radius=hole_d/2,height=10.0)
        cuts=h if cuts is None else cuts+h
body=body-cuts
usb_cut=Pos(-x_wall,0,4.0)*Box(t_wall+0.5,12.0,8.0)
body=body-usb_cut
part=body