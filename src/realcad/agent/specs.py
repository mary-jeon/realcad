"""Real-world spec and structure hints for known objects. Injected into the codegen prompt so the model
builds to known standard dimensions instead of making them up.

Matching uses Korean/English keywords. No match -> None, and only the prompt is sent.
Dimensions are realistic defaults, not ground truth (user-given numbers take precedence).
"""
from __future__ import annotations

# (keywords, hint): keywords compare lowercase; most specific first.
_SPECS: list[tuple[tuple[str, ...], str]] = [
    (("키보드", "keyboard", "키자판", "키 자판", "자판"),
     """SPEC — computer keyboard. Use these REAL standard dimensions, do NOT guess:
- Key pitch (center-to-center spacing of adjacent keys) = 19.05 mm in BOTH X and Y. Industry standard — use exactly.
- Keycap: a slightly tapered cap, ~18 mm at the base and ~14 mm at the top, ~9 mm tall. A simple Box(16.5, 16.5, 9) per key is fine (a light top chamfer looks nicer but is optional).
- Layout: a compact tenkeyless-style grid, 14 columns x 5 rows of keycaps on the 19.05 mm pitch.
  Key field = 14*19.05 = 266.7 mm (X) by 5*19.05 = 95.25 mm (Y). Center the grid on the origin.
- Case/base plate under the keys with about an 8 mm bezel all around -> roughly 283 x 111 mm, ~11 mm thick. Keycaps sit on top and embed ~1 mm into the case so they merge.
- Build the case, then LOOP over the 14x5 grid to place every keycap at its pitch position.
- IMPORTANT (time limit 45 s): do NOT boolean-fuse all ~70 keys one by one. Collect the case plus all keycaps and return them as ONE Compound (overlapping solids — a slicer prints them as a single object). Assign that Compound to `part`.
- The result must be clearly recognizable as a keyboard with a correct 19.05 mm key grid."""),

    (("너트", "hex nut", "육각너트"),
     """SPEC — hex nut (ISO 4032): across-flats (AF) and thickness. M3: AF=5.5, thick=2.4, hole=3.0. M4: AF=7, thick=3.2, hole=4. M5: AF=8, thick=4.7, hole=5. M6: AF=10, thick=5.2, hole=6. M8: AF=13, thick=6.8, hole=8. Build a RegularPolygon(side_count=6) whose inradius=AF/2 (across-flats), extrude to thickness, subtract the center hole. Default M6 if no size given."""),

    (("와셔", "washer", "워셔"),
     """SPEC — flat washer (ISO 7089): outer_d (OD), inner_d (ID), thickness (t). M3: OD=7, ID=3.2, t=0.5. M4: OD=9, ID=4.3, t=0.8. M5: OD=10, ID=5.3, t=1.0. M6: OD=12, ID=6.4, t=1.6. M8: OD=16, ID=8.4, t=1.6. M10: OD=20, ID=10.5, t=2.0. Build Cylinder(radius=OD/2, height=t) minus Cylinder(radius=ID/2, height=t+1). Default M6 if no size given."""),

    (("볼트", "bolt", "나사", "스크류", "screw", "machine screw"),
     """SPEC — metric hex-head bolt (ISO 4014). Head across-flats (AF) and head height (hh), shank diameter (d) = nominal, length (L) = user value or default 20 mm (shank only, under the head). M3: d=3, AF=5.5, hh=2. M4: d=4, AF=7, hh=2.8. M5: d=5, AF=8, hh=3.5. M6: d=6, AF=10, hh=4. M8: d=8, AF=13, hh=5.3. M10: d=10, AF=16, hh=6.4. Build: hex head = extrude RegularPolygon(side_count=6, inradius=AF/2) to hh; shank = Cylinder(radius=d/2, height=L) below the head; fuse. (Skip modeling the helical thread — a plain cylindrical shank is the standard printable representation.) Default M6, L=20."""),

    (("육각렌치", "육각 렌치", "allen key", "hex key", "l렌치", "육각키"),
     """SPEC — hex (Allen) key, L-shaped: hex bar across-flats = the key size s. Common: 2, 2.5, 3, 4, 5, 6, 8 mm. Long arm length ~ 9*s, short arm ~ 3.5*s. Build two hexagonal prisms (RegularPolygon side_count=6, inradius=s/2, extruded) meeting at a right angle; a small fillet at the corner is nice. Default s=5 if not given."""),
]


def spec_hint(prompt: str) -> str | None:
    """Spec hint string if the prompt mentions a known object, else None."""
    p = prompt.lower()
    for keys, hint in _SPECS:
        if any(k.lower() in p for k in keys):
            return hint
    return None
