"""기어 맞물림·엔클로저 실측 검증 회귀."""
import pytest
from realcad.contract.schema import DesignContract as D
from realcad.pipeline import build_and_verify
from realcad.geometry import builder as g


def _run(d):
    part, f, dia, findings, summ = build_and_verify(D.from_dict(d))
    return summ, {x.code: x for x in findings}


@pytest.mark.parametrize("z,m", [(8, 2), (17, 2), (20, 2), (24, 1.5), (60, 1)])
def test_involute_gear_meshes_at_theoretical_center_distance(z, m):
    summ, fd = _run({"kind": "gear", "gear": {"teeth": z, "module": m, "thickness": 6, "bore": 5}})
    assert summ["passed"], summ["hard_fail"]
    assert fd["G1"].ok and fd["G1"].actual < 0.05 * m * 6


def test_gear_extreme_values_are_clamped_not_crashing():
    summ, fd = _run({"kind": "gear", "gear": {"teeth": 0, "module": -3, "thickness": 6, "bore": 500}})
    assert "M2" in fd and "G1" in fd            # 실행은 되고 판정이 나온다


@pytest.mark.parametrize("board", ["raspberry_pi_4", "raspberry_pi_5", "raspberry_pi_zero", "arduino_uno"])
def test_enclosure_standoffs_match_real_board_holes_and_floor_kept(board):
    summ, fd = _run({"kind": "enclosure", "enclosure": {"board": board}})
    assert summ["passed"], summ["hard_fail"]
    assert fd["E1"].ok and fd["E2"].actual >= 1.0


def test_pi4_holes_are_asymmetric_like_the_real_board():
    xs = sorted({h[0] for h in g.BOARDS["raspberry_pi_4"]["holes"]})
    assert xs[1] - xs[0] == pytest.approx(58.0) and xs[0] != pytest.approx(-xs[1])   # 3.5mm 오프셋 패턴


def test_unknown_board_is_an_error_not_silent_pi():
    with pytest.raises(g.UnknownBoard):
        g.board_spec("esp32_devkit")
