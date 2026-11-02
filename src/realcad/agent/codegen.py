"""Code-generation CAD: the LLM writes build123d code directly to make arbitrary parts.

This path covers what the fixed primitive menu (plate/container/...) cannot.
Instead of the planner choosing a kind, the model writes build123d Python code
that runs isolated in the sandbox. On failure the error is fed back for an
automatic retry (auto-repair).

Used for mechanical parts (stands, screws, gears, brackets, cases, organizers)
as well as free-form shapes such as figurines.
"""
from __future__ import annotations
import json
import os
import re
import shutil
from pathlib import Path
from .meta_client import chat
from . import sandbox
from . import specs

SYSTEM = r"""You write build123d (v0.13, algebra mode) Python that builds ONE 3D-printable
part. The part may be simple or may have many repeated sub-features (keys, teeth, slots, ribs).
Output CODE ONLY — no prose, no markdown fences, no comments-as-explanation.

HARD RULES
- Assign the final result to a variable named exactly `part` (a Part/Solid/Compound).
- ORIENTATION: +Z is up and the object stands on z=0. The FRONT of the object (a face, eyes, a screen,
  buttons, the side a person looks at) faces -Y, toward the viewer of the front view.
- Units are millimeters. Design for FDM 3D printing: walls >= 1.6 mm, no feature thinner
  than ~1.2 mm, avoid knife edges, keep it watertight (a single fused solid unless the user
  clearly asked for separate pieces like a body + a removable lid).
- You MAY `from build123d import *` and `import math`. NOTHING else — no os, sys, files, network.
- No input()/open()/eval()/exec(). No reading or writing files. Pure geometry.
- BUILD TO REAL DIMENSIONS. When the requested object has well-known real-world sizes, use those
  EXACT standard values — do not invent a rough size. (If the prompt includes a `SPEC —` block,
  treat its dimensions as authoritative.) Make the result the right overall size and proportions.
- DIMENSION DISCIPLINE (do this first): BEGIN your output with a short comment block (lines starting
  with `#`) that lists the object's real-world dimensions in mm BEFORE any code — overall size and
  each main sub-part, naming every standard you rely on (e.g. `# A4 = 210x297`, `# VESA = 100x100`,
  `# key pitch = 19.05`, `# 2L bottle ~ Ø90 x 300`). Then write code that uses exactly those numbers.
  If the object's name is AMBIGUOUS (e.g. "물통" = slim water bottle vs handled jug; "컵" = mug vs
  tumbler), state in the comment which common interpretation you chose, then build that. Keep the
  comment to a few lines; after it, code only.
- CLEARANCE / FIT DISCIPLINE (so printed parts actually fit): when the part MATES with something —
  fits ONTO a peg/shaft/post, INTO a hole/slot/socket, AROUND a device/box/pipe, a lid/cap ONTO a
  container, a bracket ONTO a rail — you MUST add FDM printing clearance; a part built at the raw
  nominal size will NOT fit (FDM holes shrink, surfaces bulge). Rule of thumb (PLA/PETG), where
  "per side" is the gap on EACH mating face:
    · press/영구  ~0.075 mm/side   · snug/딱맞음  0.15 mm/side
    · normal/보통(DEFAULT)  0.2 mm/side   · loose·moving/헐렁·힌지  0.4 mm/side
  Apply it as: a HOLE/socket that receives a nominal Ø D peg → model it Ø (D + 2*side). A PEG that
  inserts into a nominal Ø D hole → model it Ø (D − 2*side). A CAVITY that wraps an object measured
  W×H → make it (W + 2*side)×(H + 2*side) THEN add walls around that. A LID over a box of outer
  W×L → inner opening (W + 2*side)×(L + 2*side). Default to NORMAL(0.2) unless the request says
  tight/press(꽉·압입) or loose/moving(헐렁·힌지·돌아가게). If a `[FIT …]` directive is present, use its value.
  IMPORTANT: when MEASURED dimensions describe the OBJECT this part must fit around/into (not the part
  itself), do NOT build at the raw measured size — add the clearance. Also chamfer hole/opening
  entrances ~0.5 mm (counters the squashed first-layer "elephant foot" lip). In the dimension comment,
  note nominal vs clearance-applied (e.g. `# shaft Ø8 → hole Ø8.4 (0.2/side)`).
- STRUCTURE, don't flatten. If the object is inherently made of repeated features (a keyboard's
  keys, a gear's teeth, a grille's slots, a rack of holes), GENERATE them with a loop at the
  correct pitch. Never collapse a structured object into one featureless block.
- SOLID COUNT = number of physically SEPARATE pieces. One object is ONE fused watertight solid.
  FUSE (a + b) every feature that belongs to the same physical piece — ribs, rim, foot, handle,
  spout, lugs all fuse INTO the body so the result is a single solid. Only make 2+ solids when the
  user clearly wants separate pieces (a bottle body + a removable lid/cap = exactly 2 solids;
  a case + a snap cover = 2). Do NOT leave attachments as loose overlapping solids.
  WELD RELIABLY: for a single-piece object, EVERY attached feature must deeply EMBED into the body,
  not just touch it. Make each foot, leg, spout, handle, rib, boss, knob penetrate its neighbor by
  at least 2 mm (overlap the shared volume) — a part that only kisses the surface stays a separate
  solid. Position features to sink INTO the body (e.g. a foot's top goes 2 mm above the base's
  bottom; a spout's wide end sits 2 mm inside the funnel cone). Then `body = body + foot + spout +
  handle` fuses to exactly ONE solid. After building, mentally check: is every piece sharing volume
  with another? If yes you get 1 solid. Only a genuinely separate piece (a removable lid/cap) is 2.
- PERFORMANCE (hard 45 s limit): fusing a few dozen solids is fine and is the default. ONLY when you
  have MANY identical repeated features (roughly 40+, e.g. a keyboard's ~70 keys) does one-by-one
  fusing get too slow — THEN collect those repeats into a `Compound` (overlapping solids still print
  as one object). For a handful of features (ribs, a handle, a lid seat), always fuse — never Compound.
- SCREW HOLE SIZES (use these, do not guess): clearance holes (normal fit) M3 3.4 / M4 4.5 / M5 5.5 / M6 6.6 / M8 9.0 mm;
  heat-set insert holes M2 3.2 / M2.5 3.4 / M3 4.0 / M4 5.6 / M5 6.4 / M6 8.0 mm, depth = insert length + 1 mm
  (M3 insert 5.7 long → 6.7 mm deep blind hole, keep ≥1 mm floor); counterbore for a socket-head cap screw
  Ø = head Ø + 1 mm (M3 6.5 / M4 8 / M5 9.5 / M6 11), depth = head height (M3 3 / M4 4 / M5 5 / M6 6).
- FASTENERS: when a part is "screwed/bolted to a wall" or "has N screws", model the HOLES for them in the
  part — do NOT model the screws/bolts/nuts themselves as separate solids (they are bought hardware), unless the
  user explicitly asks for a bolt or nut as the product. "Hooks"/"pegs"/"handles" belong to the body: fuse them.
- Keep it robust. Prefer primitives + boolean + revolve/extrude/loft/sweep + fillet/chamfer
  over exotic operations. If unsure of a size, pick a sensible real-world default.

ALGEBRA-MODE CHEATSHEET (these are reliable in 0.13)
- Primitives (centered at origin): Box(l,w,h), Cylinder(radius=r, height=h), Sphere(radius=r),
  Cone(bottom_radius=a, top_radius=b, height=h), Torus(major_radius=R, minor_radius=r).
- Move / rotate: Pos(x,y,z) * shape , Rot(0,0,90) * shape . Combine: Pos(0,0,10)*Rot(90,0,0)*shape.
- Booleans: a + b (fuse), a - b (cut), a & b (intersect).
- ONLY for 40+ identical repeats (keyboard keys, pin arrays): wrap them in a Compound to skip slow fuses.
    keys = [Pos(x, y, z) * Box(16.5, 16.5, 9) for x in xs for y in ys]   # ~70 keys
    part = Compound(children=[case, *keys])   # overlapping solids; a slicer prints them as one
  For a handful of features (ribs, handle, lid seat), FUSE instead (body = body + rib + handle), so
  the result is a single solid. Compound is the exception for big arrays, not the default.
- Round edges: part = fillet(part.edges().filter_by(Axis.Z), radius=2)  # pick edges then fillet
  chamfer(edges, length=1). Use .edges().group_by(Axis.Z)[-1] for "top" edges, [0] for bottom.
- Sketch then extrude/revolve (builder-free algebra):
    from build123d import *
    prof = Rectangle(40, 20)            # or Circle(radius=10), RegularPolygon(radius=10, side_count=6)
    body = extrude(prof, amount=30)     # extrude a 2D sketch to a solid
  Revolve a profile around Y axis (profile must be on the XZ/positive side):
    with BuildPart() as bp:             # for revolve, builder mode is easiest:
        with BuildSketch(Plane.XZ) as s:
            with BuildLine():
                # draw a closed half-section polyline here
                ...
            make_face()
        revolve(axis=Axis.Z)
    part = bp.part
- A hole: part = part - Pos(x,y,0)*Cylinder(radius=d/2, height=tall).
- Hollow a solid (make a cup/vessel): outer - inner, e.g.
    outer = Cylinder(radius=Ro, height=H)
    inner = Pos(0,0,wall_base) * Cylinder(radius=Ro-wall, height=H)   # leaves a floor of wall_base
    part = outer - inner

ORGANIC / CURVED FORMS (animals, figures, characters, busts, smooth blobby shapes) — NO external
libraries, pure build123d/OCC. Do NOT box these up; build them smooth and rounded:
- Ellipsoid (head, body, berry): scale(Sphere(r), (sx, sy, sz)).  A squashed/stretched sphere.
- Smooth body by LOFTING cross-sections along a spine: place ellipse/circle sections on planes
  stepped along an axis, varying their size, then loft them into one skin:
    secs = []
    spine = [(0,8),(30,12),(60,13),(90,9),(115,5)]   # (x along body, z height of center)
    radii = [8,16,18,14,7]
    for (x,z), r in zip(spine, radii):
        secs.append(Plane(origin=(x,0,z), z_dir=(1,0,0)) * Ellipse(r, r*0.8))
    body = loft(secs)                                  # one smooth watertight solid
- Limbs/neck/tail/horn: short Cylinders/Cones, or sweep a Circle along a Spline path for a curved
  horn/tail. Legs: Pos(x,0,0)*Cylinder(radius=4, height=16).
- Head/snout/ears: ellipsoids (scaled spheres) positioned to OVERLAP the body by >=2 mm, then fuse.
- BLEND the joints so it looks organic, not a snowman: fuse everything, then fillet the seams:
    part = body + head + ear_l + ear_r + leg1 + leg2 + leg3 + leg4
    part = fillet(part.edges().filter_by(GeomType.CIRCLE), radius=2)   # rounds the seams
  Keep fillet radius small (1.5-3 mm) and target only seam edges; filleting every edge is slow/fails.
- Symmetric figures/vases: draw a half-silhouette with a Spline in BuildLine, make_face, revolve.
- Make it STAND for printing: ensure a flat-ish bottom (sink the lowest part to z=0 or add a thin
  base disc), so it has a bed contact. Result must be ONE fused watertight solid.

MECHA / ROBOT FIGURE (hard-surface humanoid) — this is build123d's STRENGTH: boxes, cylinders,
chamfers, angular panels. Build a FULL recognizable robot standing upright, symmetric L/R. Plan it as
a skeleton with real coordinates (Z up, head on top), then build each part as a chamfered box/cyl and
fuse. Mirror the right side from the left with mirror(..., Plane.YZ). A good ~180 mm figure:
- HEAD (z~158-174): box ~18x16x16, chamfer edges 2. Add a thin visor slot (cut a shallow box),
  two small eye boxes, and a V-FIN: two thin angled fins (Rot about X/Y) meeting on the forehead.
- NECK: short Cylinder r4 h6 at z~153.
- TORSO: chest Box ~46x24x30 (z 120-150) chamfered; angled air-intake boxes on the upper chest;
  an abdomen Box ~30x20x18 below (z 104-122); a waist/hip Box ~42x22x16 (z 92-104).
- SHOULDERS: angular pauldron Box ~22x24x22 at x=±30, z~140 (chamfered, outer-top corner cut).
- ARMS (mirror L/R): upper arm Box/Cyl ~14x14x34, elbow cyl, forearm Box ~16x16x30, fist Box ~12.
- LEGS (mirror L/R): thigh tapered Box ~18x20x40 (z 52-92), knee cyl, shin tapered Box ~18x22x44
  (z 8-52), foot angular Box ~22x34x12 flat on z=0 so it STANDS.
- BACKPACK: Box ~40x12x40 on the back (+Y side of torso) + two thruster Cylinders below it.
- Optional hand prop: a held tool = Cylinder shaft + Box body + grip in a fist; optional arm plate = large
  chamfered plate on a forearm.
- Chamfer edges ~1.5-2 for the mech look, but DON'T chamfer every tiny edge (slow). Overlap each
  part into its neighbor >=2 mm and fuse to ONE solid (joints stay connected for printing). If the
  fuse count gets large/slow, group repeated/small parts into a Compound.
- BODY FIRST, accessories LAST. ALWAYS build the COMPLETE standing humanoid (head, torso, both
  arms, hips, both legs with feet on z=0) FIRST and make it coherent; ONLY THEN attach backpack /
  fins / hand prop / arm plate. Do NOT start from the accessories or lead with many of them: piling
  prop+plate+fins into one pass breaks the body into floating boxes. If asked for lots of gear,
  keep the body solid and add at most a backpack + one held item; the rest can be added later by edit.
This applies to any mech/robot figure request. Make it clearly humanoid, not a box.

CHARACTER / CHIBI (anime, game, mascot figures) — soft organic, so build a STYLIZED CHIBI (2-3
heads tall): a BIG head (scaled sphere ~ as wide as the body), a small rounded body (loft or
ellipsoid), short stubby arms/legs (capsules = cylinder + sphere caps), and HAIR as a few overlapping
scaled spheres/lofted locks on top of the head. Add tiny facial hints (shallow-cut eyes). Fuse to one
solid, flat bottom to stand. Recognizable as a character, not photoreal — detailed faces are beyond
parametric, so keep it cute and simple.

WORKED EXAMPLE — a simple mug (shows the `part` convention and hollowing):
from build123d import *
Ro, H, wall, base = 40, 95, 3, 4
outer = Cylinder(radius=Ro, height=H)
inner = Pos(0, 0, base) * Cylinder(radius=Ro - wall, height=H)
body = outer - inner
handle = Pos(Ro, 0, H/2) * Rot(90, 0, 0) * Torus(major_radius=16, minor_radius=4)
part = body + (handle & (Pos(Ro, 0, H/2) * Box(40, 40, H)))   # trim handle to body side

Now produce code for the user's request. CODE ONLY."""

_REPAIR = """The previous code FAILED. Here is the code and the exact error. Fix it and return
the COMPLETE corrected code (code only, no fences, no prose). Keep the same intent.

--- previous code ---
{code}
--- error ---
{error}
--- end ---
Return corrected code only."""


def _strip(text: str) -> str:
    t = text.strip()
    # strip ```python ... ``` fences
    if "```" in t:
        m = re.search(r"```(?:python|py)?\s*\n?(.*?)```", t, re.DOTALL)
        if m:
            t = m.group(1)
    return t.strip()


def generate_code(prompt: str, prior_code: str | None = None,
                  error: str | None = None, image_url: str | list | None = None) -> tuple[str, dict]:
    """Prompt (plus the previous failing code and error) -> (build123d code string, usage).
    With image_url (a photo or a reference sheet) a repair also sees that image."""
    if prior_code and error and image_url:
        text = f"User request: {prompt}\n\n" + _REPAIR.format(code=prior_code, error=error)
        urls = image_url if isinstance(image_url, list) else [image_url]
        content, usage = chat([{"role": "system", "content": SYSTEM},
                               {"role": "user", "content": [{"type": "text", "text": text}] +
                                [{"type": "image_url", "image_url": {"url": u}} for u in urls]}],
                              json_mode=False, temperature=0.0, max_tokens=12000)
        return _strip(content), usage
    if prior_code and error:
        user = (f"User request: {prompt}\n\n" +
                _REPAIR.format(code=prior_code, error=error))
    else:
        hint = specs.spec_hint(prompt)
        user = f"{prompt}\n\n{hint}" if hint else prompt
        if _is_mecha(prompt):
            user += ("\n\nMECHA/ROBOT: build a FULL recognizable humanoid robot per the MECHA/ROBOT FIGURE "
                     "recipe — head with V-fin + eyes, chest with air intakes, pauldrons, arms, "
                     "hips, tapered legs with feet flat on z=0 so it stands, backpack with thrusters, "
                     "symmetric L/R via mirror(..., Plane.YZ), chamfered panels. Clearly humanoid, "
                     "~180 mm tall, standing. Fuse to one watertight solid (Compound if slow).")
        elif _is_character(prompt):
            user += ("\n\nCHARACTER: build a STYLIZED CHIBI figure per the CHARACTER/CHIBI recipe — "
                     "big head, small rounded body, stubby capsule arms/legs, hair as overlapping "
                     "scaled spheres, tiny cut eyes. Cute and recognizable, flat bottom to stand. "
                     "One fused watertight solid.")
        elif _is_organic(prompt):
            user += ("\n\nORGANIC FORM: build this as a SMOOTH, ROUNDED organic shape — use the "
                     "ORGANIC/CURVED FORMS recipe (loft elliptical cross-sections for the body, "
                     "scaled spheres/ellipsoids for head and limbs overlapping the body, sweep a "
                     "spline for tail/horn, then fillet the seams). Do NOT make it blocky. Give it a "
                     "flat-ish bottom so it stands. ONE fused watertight solid.")
    return _gen(user)


_MECHA_RE = re.compile(
    r"\b(mecha|mech|robot|gundam|android|droid|exosuit|"
    r"건담|건프라|로봇|로보트|메카|메크|안드로이드)\b")
_CHAR_RE = re.compile(
    r"\b(character|chibi|anime|manga|game character|mascot character|figure of a (girl|boy|man|woman)|"
    r"캐릭터|치비|애니|애니메|만화|게임\s*캐릭터|미소녀|피규어)\b")


def _is_mecha(p: str) -> bool:
    return bool(_MECHA_RE.search(p.lower()))


def _is_character(p: str) -> bool:
    return bool(_CHAR_RE.search(p.lower()))


_ORGANIC_RE = re.compile(
    r"\b(figure|figurine|character|mascot|doll|toy|statue|sculpture|bust|animal|creature|"
    r"dragon|dino|dinosaur|dog|puppy|cat|kitten|bird|duck|owl|fish|whale|dolphin|bear|rabbit|"
    r"bunny|fox|pig|cow|horse|elephant|lion|tiger|frog|turtle|snake|snail|bee|butterfly|"
    r"flower|rose|tree|mushroom|face|head|person|human|baby|angel|ghost|skull|heart|"
    r"피규어|인형|캐릭터|동물|공룡|강아지|고양이|새|오리|물고기|곰|토끼|여우|돼지|말|코끼리|"
    r"사자|호랑이|개구리|거북|뱀|달팽이|나비|꽃|장미|나무|버섯|얼굴|사람|아기|천사|유령|해골|하트|조각상|흉상)\b")


def _is_organic(prompt: str) -> bool:
    return bool(_ORGANIC_RE.search(prompt.lower()))


def _gen(user: str) -> tuple[str, dict]:
    content, usage = chat(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": user}],
        json_mode=False, temperature=0.0, max_tokens=12000,
    )
    return _strip(content), usage


# Real sizes (mm) of reference objects for inferring photo scale: Korean and international coins, standard cards, paper.
# Most reliable: ruler/caliper (scale read directly) > card/paper (large flat area) > coin (small, larger error).
_REFERENCE_SIZES = (
    "KNOWN REFERENCE SIZES (use whichever is visible, most reliable first):\n"
    "- Ruler / tape measure: read the mm/cm marks directly (BEST).\n"
    "- Digital caliper LCD: the displayed number IS the measurement in mm (BEST).\n"
    "- ISO/IEC 7810 ID-1 card (credit/debit/transit/ID card): 85.60 x 53.98 mm (very reliable, large flat).\n"
    "- A4 paper: 210 x 297 mm. US Letter: 215.9 x 279.4 mm.\n"
    "- Korean coins (diameter): 10원 18.0, 50원 21.6, 100원 24.0, 500원 26.5 mm.\n"
    "- US coins (diameter): penny 19.05, nickel 21.21, quarter 24.26 mm. 1 Euro 23.25 mm. 100 JPY 22.6 mm.\n"
    "- Common objects (rough, last resort): AA battery 50.5x14.5, standard pencil ~19cm, "
    "LEGO stud pitch 8.0 mm, US/EU keycap pitch 19.05 mm."
)

_MEASURE_INSTR = (
    "You are measuring a real object from a photo so it can be 3D-printed to fit reality.\n\n"
    + _REFERENCE_SIZES +
    "\n\nMETHOD (reference-object scaling):\n"
    "1. Find a reference of known size in the frame that lies on the SAME flat plane as the target "
    "and close to it. Prefer a ruler/caliper reading, then a card, then a coin.\n"
    "2. From the reference's pixel size vs its real mm, get the scale, then measure the target's "
    "overall width/depth/height and any important features (hole diameters, wall thickness, slot "
    "widths, spacing) in mm.\n"
    "3. SELF-CHECK: re-measure the reference as if unknown — you must recover its true size. If a "
    "rectangle looks trapezoidal the shot is angled and scale varies: say so and give your best estimate.\n"
    "4. If NO reference is visible, estimate from typical real sizes for that kind of object and mark "
    "found_reference=false, confidence=\"low\".\n\n"
    "Return ONLY JSON, no prose, no markdown fence:\n"
    '{"found_reference": true|false, "reference": "what you used", "reference_mm": <number or null>, '
    '"overall_mm": {"w": <number>, "d": <number>, "h": <number>}, '
    '"features": [{"name": "...", "mm": <number>}], '
    '"confidence": "high"|"medium"|"low", "notes": "angle/plane warnings, assumptions"}'
)


def estimate_dimensions_photo(image_url: str, note: str = "") -> dict:
    """Infer real dimensions (mm) from a reference object in the photo -> structured dict. Returns {} on failure."""
    text = _MEASURE_INSTR + (f"\n\nUser note (may name the reference or target size): {note.strip()}"
                             if note.strip() else "")
    user = [{"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": image_url}}]
    try:
        content, _u = chat(
            [{"role": "system", "content": "You are a precise metrologist. Output JSON only."},
             {"role": "user", "content": user}],
            json_mode=False, temperature=0.0, max_tokens=8000,   # reasoning model: leave room for reasoning tokens
        )
        return _parse_json(content)
    except Exception:
        return {}


def _parse_json(text: str) -> dict:
    """Lenient JSON extraction: parse the first {...} block even with fences or stray text around it."""
    try:
        return json.loads(text)
    except Exception:
        pass
    s, e = text.find("{"), text.rfind("}")
    if s >= 0 and e > s:
        try:
            return json.loads(text[s:e + 1])
        except Exception:
            return {}
    return {}


def _measure_to_text(m: dict) -> str:
    """Measurement dict -> instruction for the codegen user message to build at exactly these dimensions."""
    if not m or not m.get("overall_mm"):
        return ""
    o = m["overall_mm"]
    lines = [f"MEASURED real-world dimensions (build to THESE exact mm, do not guess):",
             f"- overall W x D x H = {o.get('w')} x {o.get('d')} x {o.get('h')} mm"]
    for f in (m.get("features") or []):
        if f.get("name") and f.get("mm") is not None:
            lines.append(f"- {f['name']} = {f['mm']} mm")
    if m.get("reference"):
        lines.append(f"(scaled from reference: {m['reference']}; confidence {m.get('confidence','?')})")
    return "\n".join(lines)


_PHOTO_INSTR = ("Build the object shown in this photo as a single 3D-printable build123d part. "
                "Follow DIMENSION DISCIPLINE (comment the sizes first). If MEASURED dimensions are "
                "given below, use them EXACTLY. Otherwise estimate from any reference visible, else "
                "typical real sizes. CODE ONLY.")


def generate_code_photo(image_url: str, note: str = "", measured: str = "", instr: str | None = None) -> tuple[str, dict]:
    """Photo (+ note + measured dimensions) -> build123d code. Multimodal; for mechanical and geometric objects.

    Note: photo mode does not inject specs.spec_hint (a fixed layout), because the code must
    follow the actual layout visible in the photo (e.g. full-size 104-key vs TKL). If `measured`
    (the dimension estimation result) is given, its mm values are enforced exactly.
    """
    text = instr or _PHOTO_INSTR
    if measured.strip():
        text += "\n\n" + measured.strip()
    if note.strip():
        text += f"\n\nUser note: {note.strip()}"
    user = [{"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": image_url}}]
    content, usage = chat(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": user}],
        json_mode=False, temperature=0.0, max_tokens=12000,
    )
    return _strip(content), usage


def design_code_photo(image_url: str, note: str, stl_path, step_path, max_iters: int = 3) -> dict:
    """Photo -> dimension estimate -> generate, run, auto-repair. The result includes `measure` (dimension report)."""
    desc = (note.strip() or "the object in the photo")
    measure = estimate_dimensions_photo(image_url, note)   # 1) infer real mm from the reference object
    measured_txt = _measure_to_text(measure)
    code, _u = generate_code_photo(image_url, note, measured_txt)   # 2) generate at those dimensions
    last_code, error = code, None
    diags: list = []
    for it in range(max_iters + 1):
        if it > 0:
            code, _u = generate_code(desc, last_code, error, image_url=image_url)
            last_code = code
        try:
            info = sandbox.execute_to_files(code, stl_path, step_path)
            d1 = dimension_check(code, info)
            if d1:
                raise sandbox.SandboxError(d1)
            code, info, rv = _visual_review(desc, code, info, stl_path, step_path, ref_image_url=image_url)   # also compare against the photo
            return {"ok": True, "code": code, "info": info, "measure": measure,
                    "findings": _findings(info), "iters": it, "fixed": it > 0, "review": rv, "diag": diags}
        except sandbox.SandboxError as e:
            error = _diag_note(code, str(e), diags)
            if it == max_iters:
                return {"ok": False, "error": str(e) + (f" (엔진 진단: {diags[-1]})" if diags else ""), "code": code, "iters": it,
                        "findings": [], "measure": measure, "diag": diags}
    return {"ok": False, "error": error or "unknown", "code": code or "", "iters": max_iters,
            "findings": [], "measure": measure, "diag": diags}


def _concept_review(prompt: str, code: str, info: dict, stl_path, step_path, sheet_png, sheet_url: str):
    """Review loop for parts built from a reference sheet. Each round shows Muse Spark the 7-view render, the sheet,
    an overlay of both outlines (red = missing, blue = extra) and the widths at nine heights, asks for a fix, and keeps
    the fix only if the measured outline match goes up. Stops when the review passes and the outline is close enough,
    when a fix does not help, or after REALCAD_FIX_ROUNDS rounds (default 3). Returns (code, info, review)."""
    if os.environ.get("REALCAD_VISUAL_REVIEW", "1") == "0":
        return code, info, None
    from . import concept as _cc, review as _rv
    stl_path, step_path = Path(stl_path), Path(step_path)
    tok = stl_path.name.split("_")[0]
    rounds = max(0, int(os.environ.get("REALCAD_FIX_ROUNDS", "3")))
    rv = {"rounds": [], "fixed": False, "images": [], "iou": [], "tries": 0, "kept": 0}
    made = []

    def look(c, stl, step, n):
        png = stl.with_name(f"{tok}_review{n}.png")
        if not _rv.render_views(png, step_path=step, stl_path=stl, title=prompt[:80]):
            return None, None, None
        sc = _cc.score(sheet_png, stl)
        r = _rv.review_once(prompt, c, png, sheet_url, extra=_outline_text(sc))
        if _cc.low(sc):
            r = {**r, "matches": False, "problems": (r.get("problems") or []) +
                 [f"윤곽이 참고 그림과 덜 맞아요 (정면 {round(sc['front'] * 100)}%, 옆 {round(sc['side'] * 100)}%)"]}
        return png, sc, r

    try:
        png, sc, r = look(code, stl_path, step_path, 1)
        if png is None:
            return code, info, None
        rv["images"].append(png.name); rv["rounds"].append(r)
        if sc:
            rv["iou"].append(sc)
        best = {"code": code, "info": info, "sc": sc, "r": r}
        for k in range(rounds):
            if best["r"]["matches"] and not _cc.low(best["sc"]):
                break
            diff = stl_path.with_name(f"{tok}_outline{k + 1}.png")
            urls = [sheet_url]
            if _cc.diff_png(sheet_png, stl_path, diff):
                rv.setdefault("outlines", []).append(diff.name)
                urls.append(_rv._png_data_url(diff))
            prof = _cc.profile_text(sheet_png, stl_path)
            note = _rv.fix_note(best["r"]) + (
                "\nThe second image overlays the outline of the reference sheet and of your part, scaled to the same height: "
                "grey = both, RED = in the sheet but missing in your part (add or enlarge there), "
                "BLUE = your part sticks out where the sheet has nothing (shrink or move there)." if len(urls) > 1 else "") + (
                "\nMeasured widths (H = height of the figure):\n" + prof if prof else "")
            rv["tries"] += 1
            new_code, _u = generate_code(prompt, best["code"], note, image_url=urls)
            t_stl, t_step = stl_path.with_name(f"{tok}_try{k + 1}_part.stl"), step_path.with_name(f"{tok}_try{k + 1}.step")
            made += [t_stl, t_step]
            try:
                info2 = sandbox.execute_to_files(new_code, t_stl, t_step)
            except sandbox.SandboxError as e:
                rv.setdefault("fix_errors", []).append(str(e)[:200])
                continue
            png2, sc2, r2 = look(new_code, t_stl, t_step, k + 2)
            if png2 is None:
                continue
            rv["images"].append(png2.name)
            if sc2:
                rv["iou"].append(sc2)
            better = (_mean(sc2) > _mean(best["sc"]) + 0.005) if (sc2 and best["sc"]) else \
                     (len(r2["problems"]) < len(best["r"]["problems"]))
            if not better:
                rv["rejected"] = rv.get("rejected", 0) + 1
                break
            shutil.copyfile(t_stl, stl_path); shutil.copyfile(t_step, step_path)
            best = {"code": new_code, "info": info2, "sc": sc2, "r": r2}
            rv["fixed"] = True; rv["kept"] = k + 1
            rv["rounds"] = [rv["rounds"][0], r2]
        rv["best"] = best["sc"]
        return best["code"], best["info"], rv
    except Exception as e:
        rv["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        return code, info, rv
    finally:
        for p in made:
            try: p.unlink()
            except Exception: pass


_CONCEPT_INSTR = ("This image is a reference sheet drawn for the user's request: the FRONT view on the left and the "
                  "SIDE view on the right, of the same object. Build it as ONE 3D-printable figure that matches BOTH "
                  "views: the same parts, proportions and pose. Put its front toward -Y. If the request gives a size, use "
                  "it; otherwise make the tallest dimension about 100 mm. Every attached part (ears, eyes, arms, legs, "
                  "tail, wings) must sink at least 2 mm into its neighbour so everything fuses into ONE solid. Follow "
                  "DIMENSION DISCIPLINE (comment the sizes first). CODE ONLY.")


def design_code_concept(request: str, sheet_png, stl_path, step_path, max_iters: int = 3) -> dict:
    """Reference sheet drawn by Muse Image -> code that matches it, auto-repair with the sheet in view,
    then the visual review with the measured outline match."""
    from . import concept
    url = concept.data_url(sheet_png)
    code, _u = generate_code_photo(url, request, "", instr=_CONCEPT_INSTR)
    last_code, error = code, None
    diags: list = []
    for it in range(max_iters + 1):
        if it > 0:
            code, _u = generate_code(request, last_code, error, image_url=url)
            last_code = code
        try:
            info = sandbox.execute_to_files(code, stl_path, step_path)
            # figures have no authoritative size comment, so the declared-size check (D1) is not used here
            code, info, rv = _concept_review(request, code, info, stl_path, step_path, sheet_png, url)
            return {"ok": True, "code": code, "info": info, "findings": _findings(info), "iters": it,
                    "fixed": it > 0, "review": rv, "diag": diags}
        except sandbox.SandboxError as e:
            error = _diag_note(code, str(e), diags)
            if it == max_iters:
                return {"ok": False, "error": str(e) + (f" (엔진 진단: {diags[-1]})" if diags else ""), "code": code,
                        "iters": it, "findings": [], "diag": diags}
    return {"ok": False, "error": error or "unknown", "code": code or "", "iters": max_iters, "findings": [], "diag": diags}


_DIM_LINE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*[x×X*]\s*(\d+(?:\.\d+)?)(?:\s*(?:mm)?\s*[x×X*]\s*(\d+(?:\.\d+)?))?")
_DIA_LINE = re.compile(r"[Øø⌀]\s*(\d+(?:\.\d+)?)|\b(?:dia|diameter|지름)\s*[=:]?\s*(\d+(?:\.\d+)?)", re.I)
_H_LINE = re.compile(r"\b(?:height|tall|H|높이)\s*[=:≈~]?\s*(\d+(?:\.\d+)?)\s*(?:mm)?", re.I)


def declared_overall_mm(code: str) -> float | None:
    """Extract the overall size (max dimension, mm) the model declared in the code header (DIMENSION DISCIPLINE).
    Matches forms like 'overall 250 x 150 x 300', 'Ø90 x 300', 'height 250'. None if absent."""
    head = [l.strip("# ").strip() for l in code.splitlines()[:25] if l.strip().startswith("#")]
    cands = []
    for l in head:
        low = l.lower()
        pri = 2 if any(k in low for k in ("overall", "total", "전체", "bounding", "envelope")) else 1
        for m in _DIM_LINE.finditer(l):
            nums = [float(x) for x in m.groups() if x]
            if nums and max(nums) >= 5:
                cands.append((pri, max(nums)))
        for m in _DIA_LINE.finditer(l):
            v = float(next(g for g in m.groups() if g))
            if v >= 5: cands.append((pri, v))
        for m in _H_LINE.finditer(l):
            v = float(m.group(1))
            if v >= 5: cands.append((pri, v))
    if not cands:
        return None
    top = max(p for p, _ in cands)
    return max(v for p, v in cands if p == top)


def dimension_check(code: str, info: dict, tol: float = 0.6) -> str | None:
    """D1 dimension fidelity: error string (retry input) if the declared overall size and the bounding box max differ by more than tol."""
    bb = info.get("bbox") or []
    if not bb:
        return None
    built = max(bb)
    decl = declared_overall_mm(code)
    if decl is None:
        if built < 8.0:
            return (f"결과가 너무 작습니다(최대 {built:.1f} mm). 실물 크기(mm)로 만드세요. 코드 첫 줄 주석에 전체 크기를 적고 그대로 쓰세요.")
        return None
    if built < decl * (1 - tol) or built > decl * (1 + tol):
        return (f"치수 불일치: 주석에 전체 크기 {decl:.0f} mm 라고 선언했는데 실제 바운딩박스 최대 치수는 {built:.1f} mm 입니다 "
                f"(bbox {bb}). 선언한 실물 치수대로 좌표와 크기를 다시 계산하세요. 형상을 작게 뭉개서 통과시키지 마세요.")
    return None


def _findings(info: dict) -> list[dict]:
    """Sandbox measurement info -> finding dicts for the web response (same shape as _finding)."""
    out = []
    nsolids = info.get("nsolids", 0)
    wt = info.get("watertight")
    out.append({
        "code": "M2", "severity": "HARD", "ok": bool(info.get("is_valid", False)) and (wt is not False),
        "message": "매니폴드 / watertight valid solid" + ("" if wt is not None else " (메시 검사 생략)"),
        "actual": None, "required": None, "standard": "출력 가능", "suggestion": {},
    })
    out.append({
        "code": "C1", "severity": "HARD", "ok": nsolids >= 1,
        "message": f"솔리드 개수 / solids = {nsolids} (겹친 미융합 솔리드 없음, 실행 단계에서 검사)",
        "actual": float(nsolids), "required": 1.0,
        "standard": "1개=단일부품, 2개↑=조립/뚜껑분리", "suggestion": {},
    })
    bb = info.get("bbox") or [0, 0, 0]
    out.append({
        "code": "D1", "severity": "HARD", "ok": True,
        "message": "치수 충실도 / declared size ≈ built size (±60%)",
        "actual": float(max(bb)), "required": None, "standard": "코드 주석의 선언 치수 vs 커널 bbox", "suggestion": {},
    })
    out.append({
        "code": "C2", "severity": "SOFT", "ok": all(0 < d <= 500 for d in bb),
        "message": f"크기 / size {bb[0]}×{bb[1]}×{bb[2]} mm",
        "actual": None, "required": None,
        "standard": "일반 프린터 빌드볼륨 참고", "suggestion": {},
    })
    return out


def _diag_note(code: str, error: str, diags: list) -> str:
    """For shape errors such as a failed union or floating pieces, append the engine diagnosis (union parts one at a time)."""
    if not error or not sandbox.DIAG_TRIGGER.search(error):
        return error
    try:
        d = sandbox.diagnose(code)
    except Exception:
        d = None
    if d and d.get("kind") != "OK":
        diags.append(d["ko"])
        return error + "\n\n" + d["en"]
    return error


def _outline_text(sc: dict | None) -> str:
    if not sc:
        return ""
    return (f"Outline match against the reference sheet, measured by RealCAD (1.0 = identical outline): "
            f"FRONT {sc['front']:.2f}, SIDE {sc['side']:.2f}. Below 0.70 means the proportions or pose clearly differ.")


def _mean(sc: dict | None) -> float:
    return (sc["front"] + sc["side"]) / 2 if sc else 0.0


def _visual_review(prompt: str, code: str, info: dict, stl_path, step_path, ref_image_url: str | None = None,
                   ref_png=None, check_dims: bool = True):
    """Visual check: show a 7-view render to the vision model and, if it reports problems, fix once and re-check.
    Reverts to the first result if the fix fails or the re-check finds more problems. Returns (code, info, review|None)."""
    if os.environ.get("REALCAD_VISUAL_REVIEW", "1") == "0":
        return code, info, None
    from . import review as _rv
    stl_path, step_path = Path(stl_path), Path(step_path)
    tok = stl_path.name.split("_")[0]
    rv = {"rounds": [], "fixed": False, "images": []}
    made = []
    try:
        png1 = stl_path.with_name(f"{tok}_review1.png")
        if not _rv.render_views(png1, step_path=step_path, stl_path=stl_path, title=prompt[:80]):
            return code, info, None
        rv["images"].append(png1.name)
        from . import concept as _cc
        sc1 = _cc.score(ref_png, stl_path) if ref_png else None
        if sc1:
            rv["iou"] = [sc1]
        r1 = _rv.review_once(prompt, code, png1, ref_image_url, extra=_outline_text(sc1))
        if _cc.low(sc1):                                   # the measured outline overrides a lenient "looks fine"
            note = f"윤곽이 참고 그림과 덜 맞아요 (정면 {round(sc1['front'] * 100)}%, 옆 {round(sc1['side'] * 100)}%)"
            r1 = {**r1, "matches": False, "problems": (r1.get("problems") or []) + [note],
                  "fix": (r1.get("fix") or "") + " Make the outline match the reference sheet: compare the width and height "
                         "of head, body, arms, legs and tail in the FRONT and SIDE views and correct the proportions and pose."}
        rv["rounds"].append(r1)
        if r1["matches"] or not r1["problems"]:
            return code, info, rv
        new_code, _u = generate_code(prompt, code, _rv.fix_note(r1))
        tmp_stl, tmp_step = stl_path.with_name(f"{tok}_rvfix_part.stl"), step_path.with_name(f"{tok}_rvfix.step")
        made += [tmp_stl, tmp_step]
        try:
            info2 = sandbox.execute_to_files(new_code, tmp_stl, tmp_step)
            d1 = dimension_check(new_code, info2) if check_dims else None
            if d1:
                raise sandbox.SandboxError(d1)
        except sandbox.SandboxError as e:
            rv["fix_error"] = str(e)[:300]
            return code, info, rv                      # fix failed: keep the original result
        bak_stl, bak_step = stl_path.with_name(f"{tok}_rvorig_part.stl"), step_path.with_name(f"{tok}_rvorig.step")
        made += [bak_stl, bak_step]
        shutil.copyfile(stl_path, bak_stl); shutil.copyfile(step_path, bak_step)
        shutil.copyfile(tmp_stl, stl_path); shutil.copyfile(tmp_step, step_path)
        old = (code, info)
        code, info = new_code, info2
        rv["fixed"] = True
        if os.environ.get("REALCAD_REVIEW_CONFIRM", "1") != "0":
            png2 = stl_path.with_name(f"{tok}_review2.png")
            if _rv.render_views(png2, step_path=step_path, stl_path=stl_path, title=prompt[:80]):
                rv["images"].append(png2.name)
                sc2 = _cc.score(ref_png, stl_path) if ref_png else None
                if sc2:
                    rv.setdefault("iou", []).append(sc2)
                r2 = _rv.review_once(prompt, code, png2, ref_image_url, extra=_outline_text(sc2))
                rv["rounds"].append(r2)
                worse = (not r2["matches"] and len(r2["problems"]) > len(r1["problems"])) or \
                        (sc1 is not None and sc2 is not None and _mean(sc2) < _mean(sc1) - 0.05)
                if worse:   # got worse: revert
                    shutil.copyfile(bak_stl, stl_path); shutil.copyfile(bak_step, step_path)
                    code, info = old
                    rv["fixed"] = False; rv["reverted"] = True
    except Exception as e:
        rv["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        for p in made:
            try: p.unlink()
            except Exception: pass
    return code, info, rv


def design_code(prompt: str, stl_path, step_path, max_iters: int = 3) -> dict:
    """Prompt -> generate, run, auto-repair loop -> visual check. On success writes stl_path/step_path.

    Returns:
      success {"ok":True,"code":str,"info":dict,"findings":[...],"iters":int,"fixed":bool,"review":dict|None,"diag":[str]}
      failure {"ok":False,"error":str,"code":str,"iters":int,"findings":[],"diag":[str]}
    """
    code = None
    error = None
    last_code = ""
    diags: list = []
    for it in range(max_iters + 1):
        code, _usage = generate_code(prompt, last_code if error else None, error)
        last_code = code
        try:
            info = sandbox.execute_to_files(code, stl_path, step_path)
            d1 = dimension_check(code, info)
            if d1:
                raise sandbox.SandboxError(d1)
            code, info, rv = _visual_review(prompt, code, info, stl_path, step_path)
            return {"ok": True, "code": code, "info": info,
                    "findings": _findings(info), "iters": it, "fixed": it > 0, "review": rv, "diag": diags}
        except sandbox.SandboxError as e:
            error = _diag_note(code, str(e), diags)
            if it == max_iters:
                return {"ok": False, "error": str(e) + (f" (엔진 진단: {diags[-1]})" if diags else ""), "code": code,
                        "iters": it, "findings": [], "diag": diags}
    return {"ok": False, "error": error or "unknown", "code": code or "",
            "iters": max_iters, "findings": [], "diag": diags}
