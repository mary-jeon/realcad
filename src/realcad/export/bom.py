"""Bolt BOM: pick standard lengths for through (nut + washer stack) and tapped joints, plus CSV."""
from __future__ import annotations
import csv
from pathlib import Path
from ..fasteners.standards import Fastener, std_length


def bolt_length(f: Fastener, grip_mm: float, hole_type: str, washer: bool, nut: bool,
                engage_mm: float | None = None) -> tuple[float, float, str]:
    """(standard length, required length, description). Through = grip + washer + nut + 2 pitches of protrusion. Tapped = grip (mating part) + engagement depth."""
    if hole_type == "tapped":
        need = grip_mm + (f.washer_t_mm if washer else 0.0) + float(engage_mm or 0.0)
        why = f"상대부재 {grip_mm:.1f} + 체결 {float(engage_mm or 0):.1f}" + (" + 와셔" if washer else "")
    else:
        need = grip_mm + (f.washer_t_mm if washer else 0.0) + (f.nut_height_mm if nut else 0.0) + 2.0 * f.pitch_mm
        why = f"그립 {grip_mm:.1f}" + (" + 와셔" if washer else "") + (" + 너트" if nut else "") + " + 2피치 돌출"
    return std_length(f, need), round(need, 2), why


def make_bom(contract, f: Fastener, hole_dia_mm: float, engage_mm: float | None = None) -> list[dict]:
    """Contract -> list of BOM rows (bolts, nuts, washers)."""
    c = contract
    n = len(c.holes)
    if n == 0:
        return []
    if c.hole_type == "tapped":
        grip = float(c.mate_thickness or 0.0)
        L, need, why = bolt_length(f, grip, "tapped", c.washer, False, engage_mm or c.plate.thickness)
    else:
        grip = c.plate.thickness + float(c.mate_thickness or 0.0)
        L, need, why = bolt_length(f, grip, "through", c.washer, c.nut)
    unit = "mm" if f.is_metric else "in"
    disp = f"{L:.0f} mm" if f.is_metric else f'{L / 25.4:.3g}" ({L:.1f} mm)'
    rows = [{"item": "bolt", "spec": f.name, "qty": n, "length_mm": L, "length": disp,
             "required_mm": need, "basis": why, "hole_dia_mm": round(hole_dia_mm, 2),
             "hole_type": c.hole_type}]
    if c.hole_type != "tapped" and c.nut:
        rows.append({"item": "hex nut", "spec": f.name, "qty": n, "height_mm": round(f.nut_height_mm, 2)})
    if c.washer:
        rows.append({"item": "flat washer", "spec": f.name, "qty": n * (2 if (c.hole_type != "tapped" and c.nut) else 1),
                     "od_mm": round(f.washer_od_mm, 1), "t_mm": round(f.washer_t_mm, 2)})
    return rows


def write_bom_csv(rows: list[dict], path: str | Path) -> Path:
    path = Path(path)
    keys = ["item", "spec", "qty", "length", "length_mm", "required_mm", "basis", "hole_dia_mm", "hole_type", "height_mm", "od_mm", "t_mm"]
    with path.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path
