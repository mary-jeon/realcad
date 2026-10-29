"""코드생성 CAD — LLM이 build123d 코드를 직접 짜서 임의의 기계부품을 만든다.

기본형 메뉴(plate/container/...)로는 못 하는 "뭐든 다"를 푸는 경로.
플래너가 kind 를 고르는 대신, 모델이 그때그때 build123d 파이썬 코드를 생성하고
sandbox 에서 격리 실행한다. 깨지면 에러를 되먹여 자동 재시도(auto-repair)한다.

유기적 조각 형상(건담·피규어·동물)은 여기서도 못 만든다(파라메트릭 한계) — 그건 retrieval/Meshy.
여기는 기계·기하 부품(뚜껑 텀블러·거치대·나사·기어·브래킷·케이스·정리함 등) 전담.
"""
from __future__ import annotations
import json
import re
from .meta_client import chat
from . import sandbox
from . import specs

SYSTEM = r"""You write build123d (v0.13, algebra mode) Python that builds ONE 3D-printable
part. The part may be simple or may have many repeated sub-features (keys, teeth, slots, ribs).
Output CODE ONLY — no prose, no markdown fences, no comments-as-explanation.

HARD RULES
- Assign the final result to a variable named exactly `part` (a Part/Solid/Compound).
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
  at least 1.5 mm (overlap the shared volume) — a part that only kisses the surface stays a separate
  solid. Position features to sink INTO the body (e.g. a foot's top goes 1.5 mm above the base's
  bottom; a spout's wide end sits 1.5 mm inside the funnel cone). Then `body = body + foot + spout +
  handle` fuses to exactly ONE solid. After building, mentally check: is every piece sharing volume
  with another? If yes you get 1 solid. Only a genuinely separate piece (a removable lid/cap) is 2.
- PERFORMANCE (hard 45 s limit): fusing a few dozen solids is fine and is the default. ONLY when you
  have MANY identical repeated features (roughly 40+, e.g. a keyboard's ~70 keys) does one-by-one
  fusing get too slow — THEN collect those repeats into a `Compound` (overlapping solids still print
  as one object). For a handful of features (ribs, a handle, a lid seat), always fuse — never Compound.
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

MECHA / ROBOT / GUNDAM (hard-surface humanoid) — this is build123d's STRENGTH: boxes, cylinders,
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
- Optional weapon/shield: beam rifle = Cylinder barrel + Box body + grip in a fist; shield = large
  chamfered plate on a forearm.
- Chamfer edges ~1.5-2 for the mech look, but DON'T chamfer every tiny edge (slow). Overlap each
  part into its neighbor >=2 mm and fuse to ONE solid (joints stay connected for printing). If the
  fuse count gets large/slow, group repeated/small parts into a Compound.
- BODY FIRST, accessories LAST. ALWAYS build the COMPLETE standing humanoid (head, torso, both
  arms, hips, both legs with feet on z=0) FIRST and make it coherent; ONLY THEN attach backpack /
  fin-funnels / weapon / shield. Do NOT start from the weapon or lead with many accessories — piling
  rifle+shield+funnels into one pass breaks the body into floating boxes. If asked for lots of gear,
  keep the body solid and add at most a backpack + one held item; the rest can be added later by edit.
This applies to any mech/robot/gundam/EVA/mobile-suit request. Make it clearly humanoid, not a box.

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
    # ```python ... ``` 펜스 제거
    if "```" in t:
        m = re.search(r"```(?:python|py)?\s*\n?(.*?)```", t, re.DOTALL)
        if m:
            t = m.group(1)
    return t.strip()


def generate_code(prompt: str, prior_code: str | None = None,
                  error: str | None = None) -> tuple[str, dict]:
    """프롬프트(+직전 실패 코드/에러) → build123d 코드 문자열, usage."""
    if prior_code and error:
        user = (f"User request: {prompt}\n\n" +
                _REPAIR.format(code=prior_code, error=error))
    else:
        hint = specs.spec_hint(prompt)
        user = f"{prompt}\n\n{hint}" if hint else prompt
        if _is_mecha(prompt):
            user += ("\n\nMECHA/ROBOT: build a FULL recognizable humanoid robot per the MECHA/GUNDAM "
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
    r"\b(mecha|mech|robot|gundam|mobile suit|mobilesuit|eva|evangelion|android|droid|exosuit|"
    r"건담|건프라|로봇|로보트|메카|메크|모빌슈트|기동전사|이바|에바|안드로이드)\b")
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


# 사진 스케일 역산용 기준물 실측 치수(mm). 한국 동전·국제 동전·표준 카드·용지.
# 가장 신뢰: 자/캘리퍼(눈금·판독값 직접 읽음) > 카드/용지(큰 평면) > 동전(작아 오차 큼).
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
    """사진에서 기준물로 실물 치수(mm)를 역산 → 구조화 dict. 실패 시 {} 반환."""
    text = _MEASURE_INSTR + (f"\n\nUser note (may name the reference or target size): {note.strip()}"
                             if note.strip() else "")
    user = [{"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": image_url}}]
    try:
        content, _u = chat(
            [{"role": "system", "content": "You are a precise metrologist. Output JSON only."},
             {"role": "user", "content": user}],
            json_mode=False, temperature=0.0, max_tokens=8000,   # reasoning 모델 — 추론 토큰 여유
        )
        return _parse_json(content)
    except Exception:
        return {}


def _parse_json(text: str) -> dict:
    """느슨한 JSON 추출 — 펜스/잡텍스트 섞여도 첫 {..} 블록을 파싱."""
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
    """측정 dict → codegen user 메시지에 넣을 '정확히 이 치수로 만들라' 지시문."""
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


def generate_code_photo(image_url: str, note: str = "", measured: str = "") -> tuple[str, dict]:
    """사진(+메모+실측치수) → build123d 코드. 멀티모달 Muse Spark. 기계·기하 물체용.

    주의: 사진 모드에선 specs.spec_hint(고정 레이아웃)를 주입하지 않는다 — 사진에 보이는
    실제 배치(예: 풀사이즈 104키 vs TKL)를 따라야 하므로. measured(치수 추정 단계 결과)가
    있으면 그 mm 값을 정확히 쓰도록 강제한다.
    """
    text = _PHOTO_INSTR
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
    """사진 → 치수추정 → 코드생성·실행·자동수정. 결과에 measure(치수 리포트) 포함."""
    desc = (note.strip() or "the object in the photo")
    measure = estimate_dimensions_photo(image_url, note)   # 1) 기준물로 실물 mm 역산
    measured_txt = _measure_to_text(measure)
    code, _u = generate_code_photo(image_url, note, measured_txt)   # 2) 그 치수로 생성
    last_code, error = code, None
    for it in range(max_iters + 1):
        if it > 0:
            code, _u = generate_code(desc, last_code, error)
            last_code = code
        try:
            info = sandbox.execute_to_files(code, stl_path, step_path)
            return {"ok": True, "code": code, "info": info, "measure": measure,
                    "findings": _findings(info), "iters": it, "fixed": it > 0}
        except sandbox.SandboxError as e:
            error = str(e)
            if it == max_iters:
                return {"ok": False, "error": error, "code": code, "iters": it,
                        "findings": [], "measure": measure}
    return {"ok": False, "error": error or "unknown", "code": code or "", "iters": max_iters,
            "findings": [], "measure": measure}


def _findings(info: dict) -> list[dict]:
    """sandbox 측정 정보 → 웹 응답용 finding dict(기존 _finding 모양과 호환)."""
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
        "message": f"솔리드 개수 / solids = {nsolids} (겹친 미융합 솔리드 없음 — 실행 단계에서 검사)",
        "actual": float(nsolids), "required": 1.0,
        "standard": "1개=단일부품, 2개↑=조립/뚜껑분리", "suggestion": {},
    })
    bb = info.get("bbox") or [0, 0, 0]
    out.append({
        "code": "C2", "severity": "SOFT", "ok": all(0 < d <= 500 for d in bb),
        "message": f"크기 / size {bb[0]}×{bb[1]}×{bb[2]} mm",
        "actual": None, "required": None,
        "standard": "일반 프린터 빌드볼륨 참고", "suggestion": {},
    })
    return out


def design_code(prompt: str, stl_path, step_path, max_iters: int = 3) -> dict:
    """프롬프트 → 코드생성·실행·자동수정 루프. 성공 시 stl_path/step_path 에 파일 생성.

    반환:
      성공 {"ok":True,"code":str,"info":dict,"findings":[...],"iters":int,"fixed":bool}
      실패 {"ok":False,"error":str,"code":str,"iters":int,"findings":[]}
    """
    code = None
    error = None
    last_code = ""
    for it in range(max_iters + 1):
        code, _usage = generate_code(prompt, last_code if error else None, error)
        last_code = code
        try:
            info = sandbox.execute_to_files(code, stl_path, step_path)
            return {"ok": True, "code": code, "info": info,
                    "findings": _findings(info), "iters": it, "fixed": it > 0}
        except sandbox.SandboxError as e:
            error = str(e)
            if it == max_iters:
                return {"ok": False, "error": error, "code": code,
                        "iters": it, "findings": []}
    return {"ok": False, "error": error or "unknown", "code": code or "",
            "iters": max_iters, "findings": []}
