# RealCAD architecture

Text, voice or a photo goes in; a part that really fits and assembles comes out (STEP, STL, 3MF, OBJ, DXF, PDF drawing).
Meta Muse Spark designs, the CAD engine (build123d on OpenCascade) measures. All code was written after the Oct 26 kickoff.

## Runtime AI: Meta only (Muse Spark 1.3, Muse Image 1.0)
| Stage | Module | What Muse Spark does |
|---|---|---|
| Clarify | `agent/clarify.py` | asks one essential question at most, usually none |
| Product spec | `agent/product_spec.py` | named product: official size table first, model recall with a confidence second; asks only for what no model can know (max 3 questions). Sources: `docs/product-spec-references.md` |
| Planner | `agent/planner.py` | request or photo to a design contract (JSON) |
| Coder | `agent/codegen.py` | anything the contract kinds cannot express becomes build123d code; photos are scaled from a card, A4 sheet, coin or ruler |
| Judge | `agent/judge.py` | reads the engine's failure report and changes contract parameters |
| Reference sheet | `agent/concept.py` | Muse Image draws front and side views of a figure; RealCAD measures the outline match of the built part against it |
| Visual review | `agent/review.py` | looks at seven standard views (front, back, left, right, top, bottom, isometric) of the finished part and fixes what is missing, buried, floating or facing the wrong way |
| Editor | `agent/editor.py` | follow-up requests ("bigger", "add 2 holes") as a minimal contract or code change; with `dry_run` the change is built and shown as a plan, and only that plan id can be applied, once |
| Mate planner | `agent/mate_planner.py` | reads the measured feature table of each part (P* faces, H* holes, B* pins) and picks coincident, distance and concentric mates; gets the measurements back once if a mate cannot be met |

## Two paths
```
A. Contract path (no code execution)
   prompt -> planner -> DesignContract -> geometry/builder -> verify -> judge loop (max 3) -> export
B. Code path (sandboxed)
   prompt or photo -> codegen -> build123d code -> sandbox -> repair loop (max 3, with engine diagnosis)
                   -> visual review (render 7 views, Muse Spark checks, fix once, check again) -> export
C. Figures (code path with a reference sheet)
   prompt -> Muse Image front + side sheet -> user OK -> codegen looking at the sheet -> sandbox
          -> visual review + outline match (below 70 % forces one fix, a worse fix is reverted) -> export
D. Mate assembly (parts made earlier)
   parts + instruction -> feature tables -> mate planner -> solver (geometry/mates.py) -> J1 J3 J2 A1 B1 B2 -> STEP, STL, BOM
```
Path A covers the parametric kinds (plate, container, gear, enclosure, profile, clamp, ball, assembly).
Path B covers everything else. Photos go to path B first.

## Verification (measured on the engine)
| Group | Checks |
|---|---|
| Fasteners | F0 known fastener, H1 head interference, H2 clearance hole (measured cylinder), H3 thread engagement (ray cast), H4 edge distance, S2 wrench room, H5 socket access, H6 counterbore fit, I1 and I2 heat-set inserts, P1 FDM hole allowance |
| Shape | G1 gear mesh, E1 and E2 board holes and floor, D1 declared vs measured size, M1 minimum wall, M2 watertight, M3 overhang, C1 unfused or floating solids |
| Assembly | A1 interference, A2 mating diameters, A3 axial location, A4 keys, A5 gear pair, A6 bearing shoulders, A7 motion, A8 pump clearances, A9 drill path, A10 hole pattern, A11 vise engagement, A12 clamping |
| Mates | J1 every mate measured again after placing (0.02 mm, 0.05°), J3 every part connected to the fixed part (HARD), J2 parts that can still slide or spin (SOFT) |
| BOM audit | B1 material and spec present, B2 quantity = solids modelled, B3 model parts and BOM rows match (`verify/audit.py`); mass from measured volume and typical density (`export/asm_bom.py`) |
| Files | every exported file is opened again with its size and sha256 (`export/filecheck.py`); imported meshes are cleaned first (`geometry/meshfix.py`) |
| Printability | thinnest wall by ray casting and the orientation needing the least support (`verify/dfam.py`) |
| Motion (viewer) | the motion function the A7 check steps through is sampled over the input range; each moving part's move is read from its B-rep placement (or fitted on its vertices when rebuilt) and sent with the measured slide and turn (`mech/animate.py`) |

When a code-path build fails with a fuse error or a floating piece, `sandbox.diagnose` rebuilds the final
`part = a + b + ...` one part at a time in the same sandbox and names the part that breaks it (separation is judged only
on the finished union); that goes into the repair request.

When the CAD kernel itself fails a union (a Null shape, or a non-watertight result), the sandbox reruns the same code in
mesh mode: every `+`, `-` and `&` is done on closed triangle meshes (manifold3d), and the result is sewn back into a STEP solid.

## Sandbox (`agent/sandbox.py`)
1. Static check: imports limited to `math` and `build123d`; file, network, eval and dunder access are rejected.
2. Separate `python -I` process with only build123d's own geometry objects and safe builtins.
3. Limits: 25 s CPU, 45 s wall clock, 3 GB memory watched by the parent.
4. Result gates: empty, zero volume, unfused, floating or non-watertight results come back as readable errors for the repair loop
   (a kernel union failure is first retried in mesh mode).

The web app binds to localhost and can require a token (`REALCAD_TOKEN`).

## Package layout
```
src/realcad/
  fasteners/standards.py  UNC/UNF and ISO M2 to M12: clearance holes, heads, nuts, washers, socket OD, lengths, inserts
  contract/schema.py      DesignContract kinds and options, value range guard
  geometry/               part builders, hole detection on imported STEP, mate solver (mates.py), mesh cleanup (meshfix.py)
  mech/                   KS/DIN tables, six assembly presets (power train, eccentric slider, gear pump, drill jig, vise, cam clamp), motion frames for the viewer (animate.py)
  verify/                 single-part checks, assembly checks, BOM audit, thread engagement, printability (dfam)
  agent/                  meta_client, clarify, product_spec, planner, codegen, review, judge, editor, mate_planner, sandbox, faceops, sketchops
  export/                 STEP and STL, DXF plan view, 3-view PDF drawing (views.py), bolt BOM, assembly BOM with mass, file re-check, face map
  mate_assembly.py        mate assembly pipeline: solve, check, write files
  printing/               split to fit the bed with dowel pins (grid, recursive planes, joint aware)
  web/app.py              FastAPI endpoints
  mcp_server.py           MCP wrapper so agent tools can call RealCAD
web/acad.html             the web UI (CAD and 3D printer workspaces)
examples/                 demos, evaluations, record_tour.py (films the viewer tour)
tests/                    pytest suite
```

## Cost
One design is one planner call (plus up to 3 judge calls) or one code call (plus up to 3 repairs and up to 2 visual reviews).
The engine, checks and exports run locally and free.
