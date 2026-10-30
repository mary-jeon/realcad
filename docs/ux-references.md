# UX references (2026-10-30)

The web UI was reworked against two source-backed anatomy studies kept outside the repo (Korean):
- AutoCAD 2024–2026: command line (AutoComplete, mid-string search, Esc/Enter, F2 history), Status Bar Quick Reference (F7/F8/F9, blue ON, ≡ customisation), Viewport Controls, ViewCube opacity, COLORTHEME and the default 2D background RGB 33,40,48, two-stage tooltips. Sources: Autodesk Help (help.autodesk.com), Autodesk Knowledge Network, Autodesk forums, CADTutor.
- Bambu Studio (wiki.bambulab.com: Prepare/Preview/Device sections, Printer → Filament → Process sidebar, Object List columns, top toolbar order, Slice plate at top right, auto switch to Preview, Cut panel failure messages, CapsuleButton colours #00AE42 / #EBF9F0), PrusaSlicer (help.prusa3d.com: Simple/Advanced/Expert, Ctrl+F settings search, orange reset arrows #ED6B21, Measurement tool, Export G-code position), Tinkercad (Shapes panel, Inspector, Snap Grid, D/W/R/L/M/C keys).

Decision table (pattern → why → what RealCAD does): see the project's planning folder, `UX개편_결정표_20261030.md`. Patterns deliberately **not** copied: layer/path sliders, paint-on supports, multi-plate (slicer-only), AutoCAD Dynamic Input (natural language is the primary input here).
