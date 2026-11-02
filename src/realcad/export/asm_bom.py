"""Assembly bill of materials: one row per placed part (top level) and one row per kind of part (flat),
with volume measured on the solid and an estimated mass from a typical density for the material.

Densities are typical handbook values (g/cm³), so the mass is an estimate for planning, not a weighed value.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

# Typical densities in g/cm³. Keys are matched against the start of the material name (case-insensitive).
DENSITY = [
    ("SUJ", 7.83),                       # bearing steel (KS D 3525)
    ("SUS", 7.93), ("STS", 7.93),        # stainless steel
    ("SM", 7.85), ("SCM", 7.85), ("SK", 7.85), ("STC", 7.85), ("SWP", 7.85), ("SS", 7.85), ("SC", 7.85),
    ("STEEL", 7.85), ("강", 7.85),
    ("GC", 7.20), ("FC", 7.20),          # grey cast iron
    ("PBC", 8.80), ("BC", 8.70), ("BRONZE", 8.80), ("청동", 8.80),
    ("C36", 8.50), ("BRASS", 8.50), ("황동", 8.50),
    ("AL", 2.70), ("A60", 2.70), ("A50", 2.68), ("ALUMINUM", 2.70), ("알루미늄", 2.70),
    ("NBR", 1.00), ("RUBBER", 1.10), ("고무", 1.10),
    ("FR4", 1.85), ("FR-4", 1.85), ("PCB", 1.85),                # circuit board laminate
    ("PLA", 1.24), ("PETG", 1.27), ("ABS", 1.04), ("TPU", 1.21), ("POM", 1.41), ("PA", 1.14), ("NYLON", 1.14),
    ("PC", 1.20), ("ACRYL", 1.18), ("PMMA", 1.18),
]


def density(material: str | None) -> float | None:
    m = re.sub(r"\s+", "", str(material or "")).upper()
    if not m:
        return None
    best = None
    for key, rho in DENSITY:
        k = key.upper()
        if m.startswith(k) and (best is None or len(k) > len(best[0])):
            best = (k, rho)
    return best[1] if best else None


def _volume_mm3(solid) -> float | None:
    try:
        return float(sum(abs(s.volume) for s in solid.solids())) or float(abs(solid.volume))
    except Exception:
        try:
            return float(abs(solid.volume))
        except Exception:
            return None


def build(parts, reference_mark: str = "(참조)") -> dict:
    """parts: objects with no, name, spec, qty, material, solid (PartInfo or the mate assembly's parts).

    Returns {"top": [...], "flat": [...], "total_mass_g": float, "unknown_material": [names]}.
    Parts whose name contains reference_mark (a workpiece shown for context) are listed but not counted in mass.
    A part whose material has no typical density is left out of total_mass_g and named in unknown_material, so the
    total is then the sum of the known parts only (mass_complete is False)."""
    top, unknown = [], []
    total = 0.0
    for p in parts:
        name = str(getattr(p, "name", ""))
        qty = int(getattr(p, "qty", 1) or 1)
        mat = str(getattr(p, "material", "") or "")
        vol = _volume_mm3(getattr(p, "solid", None))
        per_vol = (vol / qty) if (vol is not None and qty) else None
        rho = density(mat)
        ref = reference_mark in name
        exact = per_vol / 1000.0 * rho if (per_vol is not None and rho) else None   # rounded only for display
        mass = round(exact, 1) if exact is not None else None
        if exact is None and not ref:
            unknown.append(name)
        if exact is not None and not ref:
            total += exact * qty
        top.append({"no": getattr(p, "no", len(top) + 1), "item": name, "spec": str(getattr(p, "spec", "") or ""),
                     "qty": qty, "material": mat, "volume_cm3": round(per_vol / 1000.0, 2) if per_vol is not None else None,
                     "mass_g": mass, "mass_total_g": round(exact * qty, 1) if exact is not None else None,
                     "reference": ref})
    groups: dict[tuple, dict] = {}
    for r in top:
        k = (r["item"], r["spec"], r["material"])
        g = groups.setdefault(k, {"item": r["item"], "spec": r["spec"], "material": r["material"], "qty": 0,
                                  "nos": [], "mass_g": r["mass_g"], "mass_total_g": 0.0, "reference": r["reference"]})
        g["qty"] += r["qty"]
        g["nos"].append(r["no"])
        if r["mass_total_g"] is not None and g["mass_total_g"] is not None:
            g["mass_total_g"] = round(g["mass_total_g"] + r["mass_total_g"], 1)
        else:
            g["mass_total_g"] = None
    flat = []
    for i, g in enumerate(groups.values(), 1):
        flat.append({"no": i, **g})
    return {"top": top, "flat": flat, "total_mass_g": round(total, 1), "unknown_material": unknown,
            "mass_complete": not unknown}


def write_csv(bom: dict, path, which: str = "flat") -> Path:
    """CSV of the flat (one row per kind of part) or top (one row per placed part) list, with a total line."""
    path = Path(path)
    rows = bom.get(which) or []
    keys = ["no", "item", "spec", "qty", "material", "mass_g", "mass_total_g"] + (["nos"] if which == "flat" else ["volume_cm3"])
    with path.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            rr = {k: (("'" + v) if isinstance(v, str) and v[:1] in "=+-@\t\r" else v) for k, v in r.items()}  # no spreadsheet formulas
            if "nos" in rr:
                rr["nos"] = " ".join(str(x) for x in rr["nos"])
            if rr.get("reference"):
                rr["item"] = rr["item"] + " *"
            w.writerow(rr)
        unk = bom.get("unknown_material") or []
        w.writerow({"no": "", "item": "합계 / total (추정 질량, 대표 밀도)" + (f", 재질 모름 {len(unk)}개 제외: {', '.join(unk)}" if unk else ""),
                    "mass_total_g": bom.get("total_mass_g")})

    return path
