# Recorded runs

Live runs recorded from a running server, for anyone who wants to see the results without a Meta API key. Each folder has:

- `trace.json`: the request, every Meta model call with its token count and cost as logged by the running server, the number of fix rounds and every check result.
- `part.step` and `part.stl`: the files the run produced. Open them in any CAD tool or slicer.

| Run | Request | Meta models called | Result |
|---|---|---|---|
| `voice_plate_autofix` | Spoken: mounting plate, two 1/4-20 bolts, 9 mm apart. The voice is synthetic | Muse Voice Transcribe, Muse Spark | Bolt heads collide at 9 mm, the numbers go back to Muse Spark, and it moves the bolts. One fix round. One warning stays: less wrench room than recommended |
| `pi_case` | Typed: Raspberry Pi 4 case with a lid held on by four M3 bolts | Muse Spark | Passed first try |
| `robot_figure` | Typed: small robot figurine, about 60 mm tall | Muse Image, Muse Spark | `reference_sheet.png` is the drawing it built from. One fix round |

All checks are measured by the CAD engine. Costs are computed from the token counts at list price.
