# RealCAD architecture

Text, voice or a photo goes in; a part that really fits and assembles comes out (STEP, STL, 3MF, OBJ, DXF, PDF drawing).
Meta Muse Spark designs, the CAD engine (build123d on OpenCascade) measures. All code was written after the Oct 26 kickoff.

## Runtime AI: Meta Muse Spark 1.3 only
| Stage | Module | What Muse Spark does |
|---|---|---|
| Clarify | `agent/clarify.py` | asks one essential question at most, usually none |
| Product spec | `agent/product_spec.py` | named product: official size table first, model recall with a confidence second; asks only for what no model can know (max 3 questions). Sources: `docs/product-spec-references.md` |
| Planner | `agent/planner.py` | request or photo to a design contract (JSON) |
| Coder | `agent/codegen.py` | anything the contract kinds cannot express becomes build123d code; photos are scaled from a card, A4 sheet, coin or ruler |
| Judge | `agent/judge.py` | reads the engine's failure report and changes contract parameters |
| Visual review | `agent/review.py` | looks at four rendered views of the finished part and fixes what is missing, buried, floating or facing the wrong way |
| Editor | `agent/editor.py` | follow-up requests ("bigger", "add 2 holes") as a minimal contract or code change |

## Two paths
```
A. Contract path (no code execution)
   prompt -> planner -> DesignContract -> geometry/builder -> verify -> judge loop (max 3) -> export
B. Code path (sandboxed)
   prompt or photo -> codegen -> build123d code -> sandbox -> repair loop (max 3, with engine diagnosis)
                   -> visual review (render 4 views, Muse Spark checks, fix once, check again) -> export
```
Path A covers the parametric kinds (plate, container, gear, enclosure, profile, clamp, ball, assembly).
Path B covers everything else. Photos go to path B first.

## Verification (measured on the engine)
| Group | Checks |
|---|---|
| Fasteners | F0 known fastener, H1 head interference, H2 clearance hole (measured cylinder), H3 thread engagement (ray cast), H4 edge distance, S2 wrench room, H5 socket access, H6 counterbore fit, I1 and I2 heat-set inserts, P1 FDM hole allowance |
| Shape | G1 gear mesh, E1 and E2 board holes and floor, D1 declared vs measured size, M1 minimum wall, M2 watertight, M3 overhang, C1 unfused or floating solids |
| Assembly | A1 interference, A2 mating diameters, A3 axial location, A4 keys, A5 gear pair, A6 bearing shoulders, A7 motion, A8 pump clearances, A9 drill path, A10 hole pattern, A11 vise engagement, A12 clamping |
| Printability | thinnest wall by ray casting and the orientation needing the least support (`verify/dfam.py`) |

When a code-path build fails with a fuse error or a floating piece, `sandbox.diagnose` rebuilds the final
`part = a + b + ...` one part at a time in the same sandbox and names the part that breaks it; that goes into the repair request.

## Sandbox (`agent/sandbox.py`)
1. Static check: imports limited to `math` and `build123d`; file, network, eval and dunder access are rejected.
2. Separate `python -I` process with only build123d's own geometry objects and safe builtins.
3. Limits: 25 s CPU, 45 s wall clock, 3 GB memory watched by the parent.
4. Result gates: empty, zero volume, unfused, floating or non-watertight results come back as readable errors for the repair loop.

The web app binds to localhost and can require a token (`REALCAD_TOKEN`).

## Package layout
```
src/realcad/
  fasteners/standards.py  UNC/UNF and ISO M2 to M12: clearance holes, heads, nuts, washers, socket OD, lengths, inserts
  contract/schema.py      DesignContract kinds and options, value range guard
  geometry/               part builders, hole detection on imported STEP
  mech/                   KS/DIN tables and six assembly presets (power train, eccentric slider, gear pump, drill jig, vise, cam clamp)
  verify/                 single-part checks, assembly checks, thread engagement, printability (dfam)
  agent/                  meta_client, clarify, product_spec, planner, codegen, review, judge, editor, sandbox, faceops, sketchops
  export/                 STEP and STL, DXF plan view, 3-view PDF drawing (views.py), BOM, face map for picking
  printing/               split to fit the bed with dowel pins (grid, recursive planes, joint aware)
  web/app.py              FastAPI endpoints
  mcp_server.py           MCP wrapper so agent tools can call RealCAD
web/acad.html             the web UI (CAD and 3D printer workspaces)
examples/                 demos and evaluations
tests/                    pytest suite
```

## Cost
One design is one planner call (plus up to 3 judge calls) or one code call (plus up to 3 repairs and up to 2 visual reviews).
The engine, checks and exports run locally and free.
