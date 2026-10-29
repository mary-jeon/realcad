"""볼트 표 값·조회 동작 회귀 테스트 (ASME B18.2.8-1999 최소 공차구멍, B18.6.3/B18.2.1 머리)."""
import math
import pytest
from realcad.fasteners import standards as st

IN = 25.4


@pytest.mark.parametrize("key,close,normal,loose", [
    ("#4-40", 0.120, 0.1285, 0.144), ("#6-32", 0.154, 0.170, 0.185),
    ("#8-32", 0.180, 0.196, 0.213), ("#10-24", 0.206, 0.221, 0.238),
    ("1/4-20", 0.266, 0.281, 0.297), ("5/16-18", 0.328, 0.344, 0.359),
    ("3/8-16", 0.391, 0.406, 0.422), ("1/2-13", 0.531, 0.562, 0.609),
])
def test_inch_clearance_b18_2_8(key, close, normal, loose):
    f = st.get(key)
    assert math.isclose(f.clearance("close"), close * IN, abs_tol=0.01)
    assert math.isclose(f.clearance("normal"), normal * IN, abs_tol=0.01)
    assert math.isclose(f.clearance("loose"), loose * IN, abs_tol=0.01)
    assert f.clearance("close") > f.nominal_dia_mm          # 구멍은 항상 나사보다 크다


@pytest.mark.parametrize("key,close,normal,loose", [
    ("M2", 2.2, 2.4, 2.6), ("M2.5", 2.7, 2.9, 3.1), ("M3", 3.2, 3.4, 3.6), ("M4", 4.3, 4.5, 4.8),
    ("M5", 5.3, 5.5, 5.8), ("M6", 6.4, 6.6, 7.0), ("M8", 8.4, 9.0, 10.0), ("M10", 10.5, 11.0, 12.0),
    ("M12", 13.0, 13.5, 14.5),
])
def test_metric_clearance_iso273(key, close, normal, loose):
    f = st.get(key)
    assert (f.clearance("close"), f.clearance("normal"), f.clearance("loose")) == (close, normal, loose)


def test_machine_screw_heads_b18_6_3():
    assert math.isclose(st.get("#8-32").head_across_flats_mm, 0.250 * IN, abs_tol=0.01)   # 너트 폭 11/32 아님
    assert math.isclose(st.get("#4-40").head_across_flats_mm, 0.188 * IN, abs_tol=0.01)
    assert math.isclose(st.get("#10-24").head_height_mm, 0.120 * IN, abs_tol=0.01)


def test_across_corners_uses_standard_min_not_sharp_hex():
    f = st.get("1/4-20")
    sharp = f.head_across_flats_mm / math.cos(math.radians(30))
    assert f.head_across_corners_mm < sharp
    assert math.isclose(f.head_across_corners_mm, 0.488 * IN, abs_tol=0.01)


def test_unf_shares_head_and_hole_with_unc():
    a, b = st.get("1/4-20"), st.get("1/4-28")
    assert b.series == "UNF" and math.isclose(b.pitch_mm, IN / 28)
    assert a.clearance_normal_mm == b.clearance_normal_mm and a.head_across_flats_mm == b.head_across_flats_mm


@pytest.mark.parametrize("spec,key", [
    ("M6x1", "M6"), ("m6", "M6"), ("1/4-20 UNC", "1/4-20"), ("#10-24 unc", "#10-24"),
    ("1/4", "1/4-20"), ("#8", "#8-32"), ("M2.5", "M2.5"), ('1/4"', "1/4-20"),
])
def test_normalize(spec, key):
    assert st.get(spec) is st.ALL[key]


@pytest.mark.parametrize("spec", ["M20", "#12-24", "3/4-10", "garbage", ""])
def test_unknown_raises_instead_of_silent_substitution(spec):
    with pytest.raises(st.UnknownFastener):
        st.get(spec)


def test_resolve_marks_inexact():
    f, exact, note = st.resolve("M20")
    assert not exact and f.name == "M12" and "M12" in note
    f, exact, note = st.resolve("#12-24")
    assert not exact and f.name.startswith("#10")           # 같은 인치 계열에서 제안, M5 아님


def test_std_length():
    assert st.std_length(st.get("M6"), 17.2) == 20
    assert math.isclose(st.std_length(st.get("1/4-20"), 20.0), 0.875 * IN) or st.std_length(st.get("1/4-20"), 20.0) >= 20
