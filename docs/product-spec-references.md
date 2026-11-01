# Product dimension sources

When a request names a product ("a bracket for a Mac mini"), RealCAD does not let the model guess its size.
It fills sizes in this order: an official size table in the code, then Muse Spark's recall with a self-reported
confidence (0.9 and up shown as certain, around 0.6 as an estimate, below that unknown), then the user's own
measurements for the other object (for example the width of the arm it hangs on).

## Recall check (muse-spark-1.3, temperature 0, 2026-10-31)
| Product | Model answer | Official | Confidence |
|---|---|---|---|
| Apple Mac mini M4 (2024) | 127 x 127 x 50 mm, 670 g | 127 x 127 x 50 mm, 670 g | 0.98 |
| Apple MacBook Air 13 M3 | 304.1 x 215 x 11.3 mm, 1240 g | same | 0.98 |
| Nintendo Switch OLED | 242 x 102 x 13.9 mm, 422 g | 242 x 102 x 13.9 mm, about 420 g | 0.9 |
| Raspberry Pi 5 | 85 x 56 x 17 mm, 52 g | board 85 x 56 mm, about 46 g | 0.6 |

At 0.9 and above the sizes matched to the millimetre; around 0.6 the secondary sizes drifted. That is why the two thresholds are 0.9 and 0.6.

## Official values in the size table
| Product | Value | Source |
|---|---|---|
| Mac mini M4 (2024) | 12.7 x 12.7 x 5.0 cm, 0.67 kg, ports front and back | Apple technical specifications, support.apple.com/en-us/121555 |
| MacBook Air 13 M3 | 30.41 x 21.5 x 1.13 cm, 1.24 kg | Apple technical specifications, support.apple.com/en-us/118551 |
| Raspberry Pi 5 | 85 x 56 mm, holes 58 x 49 mm, M2.5 | Raspberry Pi 5 mechanical drawing, datasheets.raspberrypi.com |
| Nintendo Switch OLED | 102 x 242 x 13.9 mm, about 420 g | Nintendo technical specifications |
| AA, AAA cells | 14.5 x 50.5 mm, 10.5 x 44.5 mm | IEC 60086-2 (R6, R03) |
| 18650 cell | 18.6 x 65.2 mm max | IEC 61960 |
| ID-1 card | 85.60 x 53.98 x 0.76 mm | ISO/IEC 7810 |

## Questions RealCAD asks
Only what no model can know, at most three, most important first: the size of the other object, which way the product
should face, and where it attaches. Everything else (official size, wall thickness, fit clearance) is filled in.
