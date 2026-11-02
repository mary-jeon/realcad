"""Assembly audit, the checks a CAD program's assembly audit runs before a BOM goes out.

B1 part properties : every real part has a material and a spec (reference parts are skipped)
B2 BOM quantity    : the quantity each BOM row declares equals the number of separate solids actually modelled
                     (RealCAD models each part, bought ones too, as one fused solid, so the count is meaningful here;
                     an imported vendor model made of several bodies would need its own rule)
B3 BOM rows        : every placed part appears in the BOM once, and no BOM row points at a part that does not exist
"""
from __future__ import annotations

from .checks import Finding

REF = "(참조)"


def _bodies(solid) -> int:
    try:
        return len(solid.solids())
    except Exception:
        return 1


def b1_properties(parts) -> Finding:
    miss_mat, miss_spec = [], []
    for p in parts:
        if REF in p.name:
            continue
        if not str(getattr(p, "material", "") or "").strip():
            miss_mat.append(f"{p.no}.{p.name}")
        if not str(getattr(p, "spec", "") or "").strip():
            miss_spec.append(f"{p.no}.{p.name}")
    ok = not miss_mat and not miss_spec
    bits = []
    if miss_mat:
        bits.append(f"재질 없음 {len(miss_mat)}개: " + ", ".join(miss_mat[:5]))
    if miss_spec:
        bits.append(f"사양 없음 {len(miss_spec)}개: " + ", ".join(miss_spec[:5]))
    return Finding("B1", "SOFT", ok,
                   (f"부품 속성 / properties: {sum(REF not in p.name for p in parts)}개 부품 모두 재질, 사양 있음" if ok
                    else "부품 속성 빠짐 / missing properties: " + "; ".join(bits)),
                   actual=float(len(miss_mat) + len(miss_spec)), required=0.0,
                   standard="BOM 에 나가는 부품은 재질과 사양이 있어야 함 (참조 부품 제외)",
                   suggestion={} if ok else {"option_a": "빠진 부품에 재질(예: SM45C, PLA)과 사양을 적기"})


def b2_quantity(parts) -> Finding:
    bad = []
    for p in parts:
        n = _bodies(p.solid)
        q = int(getattr(p, "qty", 1) or 1)
        if n != q:
            bad.append(f"{p.no}.{p.name} 수량 {q} / 실제 입체 {n}")
    ok = not bad
    return Finding("B2", "HARD", ok,
                   (f"BOM 수량 / quantity: {len(parts)}행 모두 적힌 수량 = 실제 입체 개수" if ok
                    else f"BOM 수량 불일치 {len(bad)}건: " + "; ".join(bad[:4])),
                   actual=float(len(bad)), required=0.0, standard="BOM 수량 = 모델 안의 실제 개수 (세어서 비교). RealCAD 모델 규칙: 부품 하나는 입체 하나로 합쳐 둠",
                   suggestion={} if ok else {"option_a": "수량을 실제 개수로 고치거나, 빠진 개수만큼 부품을 더 배치"})


def b3_rows(parts, bom_rows) -> Finding | None:
    if bom_rows is None:
        return None
    from collections import Counter
    pc = Counter(getattr(p, "no", None) for p in parts)
    rc = Counter(r.get("no") for r in bom_rows)
    part_nos, row_nos = set(pc), set(rc)
    missing = sorted(n for n in part_nos - row_nos if n is not None)
    orphan = sorted(n for n in row_nos - part_nos if n is not None)
    dup = sorted({n for n, k in list(pc.items()) + list(rc.items()) if n is not None and k > 1})
    ok = not missing and not orphan and not dup
    bits = ([f"BOM 에 없는 부품 번호 {missing}"] if missing else []) + ([f"모델에 없는 BOM 번호 {orphan}"] if orphan else []) + \
           ([f"두 번 나온 번호 {dup}"] if dup else [])
    msg = (f"BOM 행 / rows: 부품 {len(parts)}개와 BOM {len(bom_rows)}행이 하나씩 맞음" if ok else
           "BOM 행 불일치: " + " ".join(bits))
    return Finding("B3", "HARD", ok, msg, actual=float(len(missing) + len(orphan) + len(dup)), required=0.0,
                   standard="모델의 부품과 BOM 행이 1:1", suggestion={} if ok else {"option_a": "BOM 을 모델에서 다시 뽑기"})


def audit(parts, bom_rows=None) -> list[Finding]:
    out = [b1_properties(parts), b2_quantity(parts)]
    b3 = b3_rows(parts, bom_rows)
    if b3 is not None:
        out.append(b3)
    return out
