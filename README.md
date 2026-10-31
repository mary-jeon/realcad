# RealCAD — prompt → CAD that actually assembles

**Describe a functional part (or show a photo) and get a 3D-printable model whose bolt holes match real fasteners, whose bolt heads don't collide, whose gears actually mesh — with every rule measured on the CAD kernel, not eyeballed.** Exports STEP · STL · 3MF · OBJ · **DXF plan view** + a bolt BOM.

Built for the **Meta Global AI Developer Hackathon** (Indie track · *Push the Frontier* / manufacturing). All code written after the Oct 26 kickoff. The only runtime AI is **Meta Muse Spark 1.3** via the Meta Model API; the CAD kernel ([build123d](https://github.com/gumyr/build123d) / OpenCascade), verification and export run locally and free.

> Most text-to-CAD tools produce shapes that *look* right but put holes where real hardware won't fit. RealCAD treats the model as a designer and the kernel as a referee: it **measures** the result (hole diameters, interference volumes, thread engagement, gear meshing, floor thickness, watertightness) and, when something fails, tells Muse Spark exactly which parameter to change.

## What you can do (web UI, `/acad.html`)
| Action | Path | What Meta does | What the kernel does |
|---|---|---|---|
| **Design** a bracket / cup / gear / Pi case / coaster / clip / ball | contract path (no code exec) | planner → JSON design contract; judge fixes parameters on failure | builds parametric part, runs the checks below, exports |
| **Assemble** the other classic CAD-exam tasks: **gear pump** (two spur gears in G7 pockets, bushed shafts, gasket, sealed cover), **drill jig** (give the workpiece size, drill Ø and hole coordinates: base, posts, jig plate with DIN 179 / KS B 1030 press-fit bushes, locating pins, side clamp), **bench vise** (lead screw + two guide posts in a triangle, nut, bushes, jaw plates, handle), **cam strap clamp** (pin, eccentric cam lever, slotted strap, 90° V-block, return spring, round workpiece) | contract path | planner → `preset: gear_pump / drill_jig / vise / cam_clamp` with only the user's numbers | KS/DIN tables for the rest; checks per task: A5 pocket centre distance + mesh, A7 motion (gears counter-rotated, jaw opened in 5 steps, cam turned 0~180°), A8 pump clearances, A9 drill path (chip gap, breakthrough hole, bush length ≥ 2d), A10 bush positions = requested hole pattern (measured), A11 guide/thread engagement at max opening, A12 clamp contact at lock and 2e clearance at release |
| **Assemble** an eccentric reciprocating device (편심왕복장치, the other classic CAD exam task): eccentric shaft, link, slider in a guide bush, top cover, box housing, pulley, bearings, seal, rings | contract path | planner → `preset: eccentric_slider` with e, link length, slider Ø | same KS tables; **A7 motion check** rotates the eccentric through 8 angles and measures interference, stroke (= 2e) and guide engagement |
| **Assemble** a power train: shaft, parallel keys, spur gear (+ pinion on a 2nd shaft), V-belt pulley, two ball bearings, housing, covers, oil seal, retaining rings, cover bolts | contract path | planner → assembly contract with only what the user said (bearing code, gear m/z, pulley type/PD, pinion teeth) | **KS tables** (keys B 1311, bearings B 2023, rings B 1336, seals B 2804, V-grooves B 1400) derive every other dimension, parts are placed with mates M1~M9, then **A1~A6** are measured (interference, mating diameters, axial location, keys, gear pair centre distance, shoulders); exports per-part STL, assembly STEP, BOM CSV and a section DXF; "분해도" gives an exploded view |
| **AnyCAD** "make me a phone stand / tumbler / keyboard / Gundam" | code path | writes build123d code; auto-repairs from kernel error messages | runs code in a sandbox, rejects unfused/floating/non-watertight results |
| **AnyCAD around a real product** "a bracket that hangs a **Mac mini M4** on my laptop stand arm" | spec lookup + code path | names the product, gives its official outer size from an **official spec table** first and from model recall second with a self-reported confidence (shown as 확실 / 추정 / 모름), lists faces to keep clear (vents, ports, power button), then asks **only what no model can know** (the stand arm width and thickness, orientation; max 3 questions) and codes with clearance | same sandbox + checks; see `docs/product-spec-references.md` for the measured recall accuracy and sources |
| **Photo** → part that fits reality | code path + vision | reads a ruler / card / coin / A4 in the photo to recover real mm, then codes | same as above |
| **Edit** "bigger, add 2 holes, thicker lid" · **Undo** (20 steps) | both | minimal contract diff / minimal code edit | re-verifies |
| **Wrap**: upload a STEP/STL of a board → sealed case with lid, standoffs, port cut-outs | kernel only | — | detects mounting holes on the imported model |
| **Split** a model bigger than your printer bed (grid / BSP / joint-aware) with dowel pins | kernel only | — | volume-conservation & fit checks |
| 2D sketch → extrude, resize, fit-tolerance presets, 8 one-click functional parts, ViewCube | UI | — | — |

## Built from what makers actually ask for
We read 100 community threads (50 from r/3Dprinting, r/functionalprint, Bambu/Prusa forums, HN; 50 from Autodesk/Onshape forums, Eng-Tips, HN text-to-CAD threads — list in `docs/community-needs.md`). The recurring asks and where RealCAD answers them:

| What people keep asking | Where it shows up | RealCAD |
|---|---|---|
| "Printed holes come out 0.1–0.3 mm small" | 17 + 14 posts on tolerance / dimension error | auto-sized holes get **+0.2 mm FDM compensation** (`hole_comp`, reported as P1); a **fit-test coupon** preset to measure your own printer |
| "How do I prepare holes for heat-set inserts?" | 11 posts | `hole_type: insert` → insert table sizes the hole, **I1** checks depth + floor, **I2** checks ≥ 2 mm wall around the insert |
| "I had to google free-fit hole sizes" (327-vote Fusion idea) | 14 posts on holes / standards | fastener + fit class → ASME B18.2.8 / ISO 273 hole; through / tapped / insert; counterbore / countersink; **the kernel re-measures the hole** (H2) |
| "The electronics were fun, the enclosure was not" | 6 posts | Pi 3B/4/5/Zero, Arduino Uno presets with **real hole patterns**, or `board: custom` with your board's size and holes (E1/E2 measured) |
| "AI mesh generators are useless for precise parts; code paths work, but I had no viewer" | 11 posts | code path writes build123d, runs in a sandbox, live viewer, "make the hole 0.3 bigger" edits, undo, and **D1** rejects collapsed/wrong-size results |
| "Fusion already knows the dimensions — why do I draw them by hand?" | 6 posts | **dimensioned DXF drawing** (overall, hole Ø and positions, fastener note, units = mm in the header so AutoCAD does not scale it) |
| "BOM is missing the fasteners" / "DXF came out 10× small" | 2 + 8 posts | bolt length / nut / washer **BOM CSV**; every export in mm |
| "There is no universe where I describe CAD in a text prompt" | HN, repeatedly | fair — RealCAD also takes **photos**, STEP uploads, 2D sketches and presets; text is one input, the kernel report is the contract |

## UI (web/acad.html) — built on what AutoCAD and slicer users already know
We studied the Autodesk help for AutoCAD's command line, status bar, ViewCube and tooltips, and the Bambu Studio / PrusaSlicer / Tinkercad docs for the slicer workflow (notes: `docs/ux-references.md`). What carried over:
- **Command line** (bottom): natural language *or* AutoCAD-style aliases (`L C REC EXT H U Z EXP V SPLIT …`), autocomplete on pause, ↑↓ history, empty Enter repeats, Esc cancels, F1/F2/F7/F8/F9, Ctrl+9 command line, Ctrl+0 clean screen. Drawing background is AutoCAD's default dark grey (RGB 33,40,48).
- **Left sidebar** in slicer order **Printer → Filament → Process**: printer presets set the build volume (white bed outline; parts that exceed it turn red and get a "split / shrink" card), material feeds the thread-engagement rule (H3) and the weight estimate, nozzle feeds the minimum-wall rule (M1), hole compensation feeds P1. Changed values get an orange dot and a ↺ reset (PrusaSlicer convention); Basic/Advanced hides the rare ones; Ctrl+F searches settings.
- **Right panel**: one green primary button (Bambu's `Slice plate` position and colour) that becomes **Export ▾** when the kernel passes, chips with size / volume / estimated grams, and the verification results as **cards** — failures first, each with the measured vs required value and a one-tap fix that is sent back to Muse Spark as an edit.
- Object list with show/hide, a vertical object toolbar (S resize, F lay flat, D centre, H hole, C split), viewport controls `[-][ISO][Shaded]`, two-stage tooltips.
- **Beginner mode is the default** (stage 3): the ribbon and tabs are hidden, the title bar keeps only Import / Undo / Advanced tools, and Enter in the command line does what the old Design button did. Pressing the green button greys it and shows a bottom-right progress card (stage name, elapsed seconds, bar, cancel) exactly like Bambu Studio's slicing notification; success turns it into a "완료 ✓" card and lights step 3 "출력", failure shows a red card, and changing a setting invalidates the result ("설정 바뀜: 재검사"). There is no start-up mode dialog: choosing a printer in the sidebar *is* 3D-printer mode, no printer is CAD mode (the only difference the server knows is the build volume).

## Verification (the differentiator) — all measured on the OCC kernel
| Code | Check | How it is measured | Standard |
|---|---|---|---|
| F0 | Requested fastener exists | table lookup; unknown → **hard fail + nearest suggestion** (never silent substitution) | — |
| H1 | Bolt head vs wall / neighbouring bolt | boolean intersection volume of the bolt solid | — |
| H2 | Hole ≥ clearance hole | **actual cylindrical-face radius of the finished solid** vs table | ASME B18.2.8-1999 |
| H3 | Thread engagement ≥ k·D (tapped holes) | ray-cast material length at the thread radius; k = 1.0 steel / 1.5 Al / 2.0 plastic | shop practice |
| H4 | Edge distance ≥ 1.5·D | hole centre to plate edge | shop practice |
| S2 | Wrench clearance between bolts | centre distance ≥ 2 × head width (warning) | — |
| G1 | Gears mesh | mate gear at theoretical centre distance, rotated half a pitch: intersection = 0 | 20° involute, 0.05 m backlash |
| E1 / E2 | Board standoffs match the real hole pattern / floor under standoff ≥ 1 mm | measured pilot-hole positions & diameters; ray-cast floor | Pi 3B/4/5/Zero, Arduino Uno |
| H5 | Tool access | a socket-OD envelope above each bolt head must not intersect the wall | socket OD table |
| H6 | Counterbore fits the head | the head solid, sunk flush, has zero intersection with the plate | B18.2.1 / ISO 4017 head |
| I1 / I2 | Heat-set insert hole | blind hole depth ≥ insert length + 1 mm, floor ≥ 1 mm (ray-cast); ≥ 2 mm wall around the insert | insert maker tables |
| P1 | FDM hole compensation | +0.2 mm (configurable) on auto-sized holes, never on tapped holes; shown in the report | community measurements |
| D1 | Dimension fidelity (code path) | the overall size the model declared in its own header comment vs the measured bounding box (±60 %) | — |
| M2 | Watertight | OCC validity **and** the exported mesh is watertight | printable |
| M3 | Overhang | area of downward faces steeper than 45° (warning above 10 %) | FDM rule of thumb |
| C1 | No overlapping-but-unfused solids, no floating pieces | pairwise solid intersection; detached solids must rest on z = 0 | printable |
| A1 | Assembly interference | intersection volume of every part pair whose bounding boxes overlap (same definition as Inventor's Interference Analysis) | 0 mm³ |
| A2 | Mating diameters match | the cylindrical faces of BOTH parts of each fit (bearing bore ↔ shaft seat, bearing OD ↔ housing bore, gear/pulley bore ↔ seat, cover spigot ↔ bore) are measured on the finished solids | KS B 0401 fits (H7/k5, H7/h6) |
| A3 | Axial location chain | each bearing's inner ring (shoulder + retaining ring / collar) and outer ring (housing lip + cover lip) are stopped on both sides | textbook assembly practice |
| A4 | Key fit | t1 + t2 − h ≥ 0.1 mm, key length ≤ hub width − 2, measured key top below the hub groove floor | KS B 1311 |
| A5 | Gear pair | housing bore centre distance measured from the bore cylinders = m(z1+z2)/2; gear ∩ pinion ≈ 0 at that distance | 20° involute, 0.05 m backlash |
| A6 | Bearing shoulders | shaft shoulder Ø within [da min, da max], housing lip Ø ≤ Da max | NSK 6204/6205 values |
| A8 | Pump clearances (gear pump) | pocket Ø ≥ gear tip Ø, pocket depth + gasket ≥ gear width | 153LAB exam analysis (Ø39 G7/h6, 28 + 1.0 = 29) |
| A9 | Drill path (drill jig) | chip gap ≥ 0.5 d, breakthrough hole Ø d+2 measured in the base, bush length ≥ 2 d | jig design practice, DIN 179 lengths |
| A10 | Hole pattern (drill jig) | every requested hole centre has a bush bore cylinder measured within ±0.05 mm | user input |
| A11 | Engagement at max opening (vise) | guide post stays ≥ bush length inside the bush, screw ≥ 1.5 d in the nut | shop practice |
| A12 | Clamping (cam clamp) | strap bottom = workpiece top at 180°, clearance = 2e at 0° | eccentric cam lift Rc − e cosθ |
| A7 | Motion (eccentric preset) | link, slider, pin and the rotated shaft are placed at 0°, 45° … 315° and intersected with every fixed part; pin travel must equal 2e; slider rod must stay ≥ 5 mm above the bush | stroke = 2e |

Fastener table: UNC/UNF #4–1/2 and ISO M2–M12 with B18.2.8 clearance holes, B18.2.1 / B18.6.3 / ISO 4017 head sizes, nut heights, washers, socket OD, standard lengths, and heat-set insert hole sizes. Holes can be through (+nut), tapped, or heat-set insert; plain, counterbored or countersunk. The **BOM** picks a standard bolt length from grip + washer + nut + 2 pitches (or mate thickness + engagement for tapped holes).

## Evaluation
**Seeded-error detection** (`examples/eval_seeded.py`, kernel only, 5 s): correct designs × planted faults (hole smaller than the clearance hole, hole too close to the edge, wall through the bolt head, bolts touching, unsupported fastener, tapped plate thinner than the engagement) → **93 / 93 caught, 0 false alarms on the 12 correct designs** (12 designs × 8 faults incl. thin insert boss, wall inside the socket radius).

**End-to-end with Muse Spark** (`examples/eval_smoke.py --set wide`, 20 prompts in Korean and English, Oct 29 2026): see the table at the bottom of this file (regenerated by the script). "Pass" means the result executed, is a valid watertight solid with no unfused/floating pieces and passed every HARD check — not that it is beautiful.

## Quickstart
```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"        # or: -r requirements.lock
echo "META_API_KEY=..." > .env                               # Meta Model API key (dev.meta.ai)

# kernel-only demo (no API): verification of a wall bracket, fixed by moving a hole
PYTHONPATH=src .venv/bin/python examples/poc_bracket.py
# seeded-error detection matrix (no API)
PYTHONPATH=src .venv/bin/python examples/eval_seeded.py
# web UI
PYTHONPATH=src .venv/bin/python -m uvicorn realcad.web.app:app --host 127.0.0.1 --port 8750
open http://127.0.0.1:8750/            # → acad.html
# tests
PYTHONPATH=src .venv/bin/python -m pytest -q
```
Optional env: `REALCAD_TOKEN` (require `X-RealCAD-Token` on `/api/*` when you expose the server), `THINGIVERSE_TOKEN` (library search), `REALCAD_ENABLE_EXTERNAL=1` (opt-in external text-to-3D; **off by default — runtime AI is Meta only**).

## How a request flows
```
prompt (+ photo)
  → clarify   [Muse Spark]  ask at most one essential question
  → spec      [Muse Spark]  named product → official size table, else model recall + confidence; ask only the counterpart's measurements
  → planner   [Muse Spark]  design contract (JSON)        ─┐  contract path: no code execution
  → builder   [build123d]   part + standard fasteners      │
  → verify    [OCC kernel]  F0 H1 H2 H3 H4 S2 G1 E1 E2 M2 C1 · assembly: A1 A2 A3 A4 A5 A6
  → judge     [Muse Spark]  parameter fixes on failure (≤3 loops)
  → export    STEP · STL · 3MF · OBJ · bolt BOM (CSV)
  or
  → codegen   [Muse Spark]  build123d code  → sandbox (AST allow-list, isolated process, CPU/RSS/time limits,
                             unfused / floating / non-watertight rejected) → auto-repair from the error (≤3 loops)
```
See [ARCHITECTURE.md](ARCHITECTURE.md) for modules, the sandbox design and what is *not* implemented yet.

## Security notes
Generated code runs in a separate `python -I` process with an allow-listed namespace (only build123d's own geometry API — no `os`, `sys`, `ctypes`, file or network functions, no `export_*`/`import_*`, no dunder access or `str.format`), CPU / wall-clock / memory limits, and result gates. The web app binds to localhost, disables `/docs`, validates upload types and sizes, clamps every numeric contract value, and can require a token. It is still a local developer tool — do not expose it unauthenticated.

## Limitations / roadmap
Assembly: six presets (power train with one or two parallel shafts, eccentric slider, gear pump, drill jig, bench vise, cam strap clamp); threads, springs and bearings are simplified solids (bought parts); no helical/bevel gears, no belt, threads are not modelled (bolt holes use the nominal diameter), tolerances are nominal (fit classes are reported, not applied as deviations). Only 6203/6204/6205 bearing shoulder values and the 20×35×7 seal were cross-checked against maker catalogues, the rest are ISO 15 / JIS series values. True edge distance against arbitrary outlines, multi-axis splitting, more board presets, wrench-swing (open-end) clearance, teardrop holes for horizontal axes, snap-fit beam sizing. Organic high-detail figures are out of scope (parametric CAD ≠ sculpting).

## License
MIT © 2026 Mary Jeon

---
### Latest end-to-end run (auto-filled)
<!-- EVAL_TABLE_START -->
Set `wide` · 2026-10-30 · **20/20 passed** (12 on the first attempt, 8 after auto-repair) · mean 36 s per design

| # | path | result | tries | s | prompt |
|---|---|---|---|---|---|
| 0 | code | ✅ | 3 | 44 | a coffee mug with a handle, 350 ml |
| 1 | code | ✅ | 1 | 23 | 휴대폰 거치대, 폰 두께 9mm, 각도 60도 |
| 2 | code | ✅ | 1 | 33 | M3 볼트 4개로 벽에 거는 라즈베리파이 4 케이스 (포트 구멍 포함) |
| 3 | code | ✅ | 1 | 22 | a spur gear, 24 teeth, module 2, 8 mm bore, 10 mm thick |
| 4 | code | ✅ | 1 | 38 | 에어팟 프로 케이스 홀더, 책상 모서리에 끼우는 클립형 (책상 두께 25mm) |
| 5 | code | ✅ | 1 | 44 | a wall-mount bracket with two 1/4-20 bolt holes, 80x40x5 mm, with a 30 mm lip |
| 6 | code | ✅ | 1 | 16 | 펜 6자루 꽂는 육각 연필통 |
| 7 | code | ✅ | 2 | 70 | 건담 피규어 180mm |
| 8 | param | ✅ | 1 | 12 | a wall-mount bracket with two 1/4-20 bolt holes |
| 9 | param | ✅ | 1 | 12 | pencil holder, 80mm diameter, 100mm tall, 3 compartments |
| 10 | param | ✅ | 1 | 5 | case for raspberry pi 5 |
| 11 | param | ✅ | 1 | 3 | 24 tooth spur gear module 1.5 bore 6 |
| 12 | code | ✅ | 2 | 32 | USB-C 케이블 정리 클립 5구 |
| 13 | code | ✅ | 1 | 28 | a hex nut M8 and a matching bolt, separate pieces |
| 14 | code | ✅ | 2 | 47 | 도어 스토퍼 쐐기, 고무패드 홈 포함 |
| 15 | code | ✅ | 2 | 26 | a 100x100 VESA monitor arm adapter plate, M4 holes |
| 16 | code | ✅ | 1 | 31 | a chibi cat figure |
| 17 | code | ✅ | 2 | 51 | 벽걸이 열쇠 걸이, 고리 4개, 나사 2개 |
| 18 | code | ✅ | 3 | 63 | a snap-fit box with lid, 60x40x30 inner |
| 19 | code | ✅ | 4 | 129 | a watering can 1.5L |
<!-- EVAL_TABLE_END -->
