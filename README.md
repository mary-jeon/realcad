# RealCAD

**Prompt → CAD that actually assembles.** Describe a functional part in plain language and get a 3D model whose bolt holes match real fasteners, whose bolt heads don't collide, and that exports to **STEP / STL** — with every assembly rule checked on the geometry kernel, not eyeballed.

Most text-to-CAD tools make shapes that *look* right but put bolt holes where real hardware won't fit and never check head clearance, tool access, or edge distance. RealCAD treats the generation model as a designer and the kernel as a referee: it verifies, and when something fails it tells the model exactly which parameter to change.

## How it works

```
prompt (+ photo / PDF)
  → planner   [Meta Muse Spark]   → design contract (JSON)
  → builder   [build123d / OCC]   → part + standard fasteners
  → verify    [kernel measurement] → interference · clearance · thread engagement · edge distance
  → judge     [Meta Muse Spark]   → parameter fixes on failure (loop)
  → export    STEP · STL · bolt BOM
```

The thinking steps run on the **Meta Model API** (`muse-spark-1.3`). The CAD kernel, verification and export run locally and free.

## Verification (the differentiator)

All measured on the OCC kernel:

| Code | Check | Standard |
|------|-------|----------|
| H1 | Bolt-head / neighbor interference (boolean volume > 0) | — |
| H2 | Hole ≥ standard clearance hole | ASME B18.2.8 |
| H3 | Thread engagement ≥ k·D | — |
| H4 | Edge distance ≥ 1.5·D | — |
| S2 | Hole spacing for wrench access | — |

US inch fasteners (UNC/UNF) by default, ISO metric supported.

## Quickstart

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python build123d trimesh
echo "META_API_KEY=..." > .env      # your Meta Model API key

.venv/bin/python examples/poc_bracket.py   # kernel verification demo (no API)
.venv/bin/python examples/meta_run.py "a wall-mount bracket with two 1/4-20 bolt holes"
```

## Layout

```
src/realcad/
  fasteners/  standard bolt library (UNC/UNF + ISO, clearance holes)
  contract/   design-contract schema
  geometry/   build123d part/assembly builder
  verify/     kernel checks + thread engagement
  agent/      Meta Model API client, planner, (judge/loop)
  export/     STEP / STL
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design.

---
Built for the Meta Global AI Developer Hackathon.
