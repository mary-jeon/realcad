# RealCAD: CAD by voice and text, all the way to a real assembly

**Describe a part by voice, text or a photo and get a real 3D model: bolt holes that match real fasteners, bolt heads that do not collide, gears that actually mesh, every rule measured on the CAD engine, not eyeballed.** Use it as CAD (STEP, DXF, a 3-view drawing PDF, bolt list) or send it straight to a printer (STL, 3MF, OBJ). Before you print, it also tells you how thin the thinnest wall is and which way to lay the part so it needs the least support. Built after reading 100 community threads about 3D printing and CAD.

Built for the **Meta Global AI Developer Hackathon** (Indie track, *Push the Frontier* / manufacturing), all code written after the Oct 26 kickoff. The only runtime AI is **Meta Muse Spark 1.3** via the Meta Model API; the CAD engine ([build123d](https://github.com/gumyr/build123d) / OpenCascade), verification and export run locally.

> RealCAD treats the model as a designer and the engine as a referee: it **measures** the result (hole diameters, interference volumes, thread engagement, gear meshing, floor thickness, watertightness) and, when something fails, tells Muse Spark exactly which parameter to change.

## What you can do (web UI, `/acad.html`)
| Action | Path | What Meta does | What the engine does |
|---|---|---|---|
| **Design** a bracket / cup / gear / Pi case / coaster / clip / ball | contract path (no code exec) | planner → JSON design contract; judge fixes parameters on failure | builds parametric part, runs the checks below, exports |
| **Assemble** the other classic CAD-exam tasks: **gear pump** (two spur gears in G7 pockets, bushed shafts, gasket, sealed cover), **drill jig** (give the workpiece size, drill Ø and hole coordinates: base, posts, jig plate with DIN 179 / KS B 1030 press-fit bushes, locating pins, side clamp), **bench vise** (lead screw + two guide posts in a triangle, nut, bushes, jaw plates, handle), **cam strap clamp** (pin, eccentric cam lever, slotted strap, 90° V-block, return spring, round workpiece) | contract path | planner → `preset: gear_pump / drill_jig / vise / cam_clamp` with only the user's numbers | KS/DIN tables for the rest; checks per task: A5 pocket centre distance + mesh, A7 motion (gears counter-rotated, jaw opened in 5 steps, cam turned 0~180°), A8 pump clearances, A9 drill path (chip gap, breakthrough hole, bush length ≥ 2d), A10 bush positions = requested hole pattern (measured), A11 guide/thread engagement at max opening, A12 clamp contact at lock and 2e clearance at release |
| **Assemble** an eccentric reciprocating device (the other classic CAD exam task): eccentric shaft, link, slider in a guide bush, top cover, box housing, pulley, bearings, seal, rings | contract path | planner → `preset: eccentric_slider` with e, link length, slider Ø | same KS tables; **A7 motion check** rotates the eccentric through 8 angles and measures interference, stroke (= 2e) and guide engagement |
| **Assemble** a power train: shaft, parallel keys, spur gear (+ pinion on a 2nd shaft), V-belt pulley, two ball bearings, housing, covers, oil seal, retaining rings, cover bolts | contract path | planner → assembly contract with only what the user said (bearing code, gear m/z, pulley type/PD, pinion teeth) | **KS tables** (keys B 1311, bearings B 2023, rings B 1336, seals B 2804, V-grooves B 1400) derive every other dimension, parts are placed with mates M1~M9, then **A1~A6** are measured (interference, mating diameters, axial location, keys, gear pair centre distance, shoulders); exports per-part STL, assembly STEP, BOM CSV and a section DXF; asking for an "exploded view" spreads the parts apart |
| **AnyCAD** "make me a phone stand / tumbler / keyboard / robot figure" | code path | writes build123d code; auto-repairs from engine error messages | runs code in a sandbox, rejects unfused/floating/non-watertight results |
| **AnyCAD around a real product** "a bracket that hangs a **Mac mini M4** on my laptop stand arm" | spec lookup + code path | names the product, gives its official outer size from an **official spec table** first and from model recall second with a self-reported confidence (shown as certain / estimate / unknown), lists faces to keep clear (vents, ports, power button), then asks **only what no model can know** (the stand arm width and thickness, orientation; max 3 questions) and codes with clearance | same sandbox + checks; see `docs/product-spec-references.md` for the measured recall accuracy and sources |
| **Photo** → part that fits reality | code path + vision | reads a ruler / card / coin / A4 in the photo to recover real mm, then codes | same as above |
| **Edit** "bigger, add 2 holes, thicker lid" , **Undo** (20 steps) | both | minimal contract diff / minimal code edit | re-verifies |
| **Wrap**: upload a STEP/STL of a board → sealed case with lid, standoffs, port cut-outs | engine only | not used | detects mounting holes on the imported model |
| **Split** a model bigger than your printer bed (grid / BSP / joint-aware) with dowel pins | engine only | not used | volume-conservation & fit checks |
| 2D sketch → extrude, resize, fit-tolerance presets, 8 one-click parts, view cube | UI | not used | not used |

## UI (web/acad.html): built on what CAD and slicer users already know
We studied how CAD programs do the command line, status bar, view cube and tooltips, and how slicers lay out their workflow. What carried over:
- **Command line** (bottom): natural language *or* CAD-style aliases (`L C REC EXT H U Z EXP V SPLIT …`), autocomplete on pause, ↑↓ history, empty Enter repeats, Esc cancels, F1/F2/F7/F8/F9, Ctrl+9 command line, Ctrl+0 clean screen. Drawing background is the dark grey CAD users expect (RGB 33,40,48).
- **Left sidebar** in slicer order **Printer → Filament → Process**: printer presets set the build volume (white bed outline; parts that exceed it turn red and get a "split / shrink" card), material feeds the thread-engagement rule (H3) and the weight estimate, nozzle feeds the minimum-wall rule (M1), hole compensation feeds P1. Changed values get an orange dot and a ↺ reset (the usual slicer convention); Basic/Advanced hides the rare ones; Ctrl+F searches settings.
- **Right panel**: one green primary button (where a slicer puts its slice button, same colour) that becomes **Export ▾** when the engine passes, chips with size / volume / estimated grams, and the verification results as **cards**, failures first, each with the measured vs required value and a one-tap fix that is sent back to Muse Spark as an edit.
- Object list with show/hide, a vertical object toolbar (S resize, F lay flat, D centre, H hole, C split), viewport controls `[-][ISO][Shaded]`, two-stage tooltips.
- **Two workspaces**, switched at the left of the tool bar. **CAD** starts on a 2D sketch on the top plane and Extrude turns it into a solid (Sketch, Features, Evaluate and File tabs). **3D Printer** shows slicer-style tiles: printer and material, place, orient, fit, split, wall check, export. Pressing the green button shows a progress card (stage, elapsed seconds, cancel) that turns into a done or failed card, and changing a setting marks the result as needing a new check.

## What gets checked (all measured on the engine)
The hole fits the actual bolt (ASME B18.2.8 / ISO 273 clearance tables); bolt heads clear the wall and each other, and a socket can still reach them; threads bite deep enough for the material; holes are not too close to the edge; counterbores fit the head; heat-set insert holes have enough depth and wall around them; gears mesh at the right centre distance; board holes match the real Raspberry Pi / Arduino pattern; the part is watertight with no floating or unfused pieces; overhangs that will need support are reported. For assemblies: no two parts overlap, mating diameters match (bearing to shaft, bearing to housing, gear to seat), bearings are held on both sides, keys and gears sit where they should, pump clearances, drill-jig bush positions and vise or clamp engagement are measured, and moving parts clear everything through their travel.

Fastener table: UNC/UNF #4–1/2 and ISO M2–M12 with B18.2.8 clearance holes, B18.2.1 / B18.6.3 / ISO 4017 head sizes, nut heights, washers, socket OD, standard lengths, and heat-set insert hole sizes. Holes can be through (+nut), tapped, or heat-set insert; plain, counterbored or countersunk. The **BOM** picks a standard bolt length from grip + washer + nut + 2 pitches (or mate thickness + engagement for tapped holes).

## Evaluation
**Seeded-error detection** (`examples/eval_seeded.py`, engine only, 5 s): correct designs × planted faults (hole smaller than the clearance hole, hole too close to the edge, wall through the bolt head, bolts touching, unsupported fastener, tapped plate thinner than the engagement) → **93 / 93 caught, 0 false alarms on the 12 correct designs** (12 designs × 8 faults incl. thin insert boss, wall inside the socket radius).

**End-to-end with Muse Spark** (`examples/eval_smoke.py --set wide`, 20 prompts in Korean and English, Oct 30 2026): **20 / 20 passed** (12 on the first attempt, 8 after auto-repair, mean 36 s per design).

## Quickstart
```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"        # or: -r requirements.lock
echo "META_API_KEY=..." > .env                               # Meta Model API key (dev.meta.ai)

# engine-only demo (no API): verification of a wall bracket, fixed by moving a hole
PYTHONPATH=src .venv/bin/python examples/poc_bracket.py
# seeded-error detection matrix (no API)
PYTHONPATH=src .venv/bin/python examples/eval_seeded.py
# web UI
PYTHONPATH=src .venv/bin/python -m uvicorn realcad.web.app:app --host 127.0.0.1 --port 8750
open http://127.0.0.1:8750/            # → acad.html
# tests
PYTHONPATH=src .venv/bin/python -m pytest -q
```
Optional env: `REALCAD_TOKEN` (require `X-RealCAD-Token` on `/api/*` when you expose the server). The only runtime AI is Meta Muse Spark.

## Security notes
Generated code runs in a separate `python -I` process with an allow-listed namespace (only build123d's own geometry API, no `os`, `sys`, `ctypes`, file or network functions, no `export_*`/`import_*`, no dunder access or `str.format`), CPU / wall-clock / memory limits, and result gates. The web app binds to localhost, disables `/docs`, validates upload types and sizes, clamps every numeric contract value, and can require a token. It is still a local developer tool, do not expose it unauthenticated.

## Limitations / roadmap
Assembly: six presets (power train with one or two parallel shafts, eccentric slider, gear pump, drill jig, bench vise, cam strap clamp); threads, springs and bearings are simplified solids (bought parts); no helical/bevel gears, no belt, threads are not modelled (bolt holes use the nominal diameter), tolerances are nominal (fit classes are reported, not applied as deviations). Only 6203/6204/6205 bearing shoulder values and the 20×35×7 seal were cross-checked against maker catalogues, the rest are ISO 15 / JIS series values. True edge distance against arbitrary outlines, multi-axis splitting, more board presets, wrench-swing (open-end) clearance, teardrop holes for horizontal axes, snap-fit beam sizing. Organic high-detail figures are out of scope (parametric CAD ≠ sculpting).

## License
MIT © 2026 Mary Jeon
