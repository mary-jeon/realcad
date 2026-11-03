"""Regression for measured gear meshing and enclosure checks."""
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
    assert "M2" in fd and "G1" in fd            # it runs and produces a verdict


@pytest.mark.parametrize("board", ["raspberry_pi_4", "raspberry_pi_5", "raspberry_pi_zero", "arduino_uno"])
def test_enclosure_standoffs_match_real_board_holes_and_floor_kept(board):
    summ, fd = _run({"kind": "enclosure", "enclosure": {"board": board}})
    assert summ["passed"], summ["hard_fail"]
    assert fd["E1"].ok and fd["E2"].actual >= 1.0


def test_pi4_holes_are_asymmetric_like_the_real_board():
    xs = sorted({h[0] for h in g.BOARDS["raspberry_pi_4"]["holes"]})
    assert xs[1] - xs[0] == pytest.approx(58.0) and xs[0] != pytest.approx(-xs[1])   # 3.5mm offset pattern


def test_unknown_board_is_an_error_not_silent_pi():
    with pytest.raises(g.UnknownBoard):
        g.board_spec("esp32_devkit")


BOARDS_WITH_PORTS = ["raspberry_pi_3b", "raspberry_pi_4", "raspberry_pi_5", "raspberry_pi_zero", "arduino_uno"]


@pytest.mark.parametrize("board", BOARDS_WITH_PORTS)
def test_every_connector_clears_the_wall(board):
    summ, fd = _run({"kind": "enclosure", "enclosure": {"board": board}})
    assert summ["passed"], summ["hard_fail"]
    assert fd["E3"].ok and fd["E3"].actual == 0


def test_arduino_short_wall_has_slots_and_long_walls_stay_closed():
    from build123d import Box, Pos
    from realcad.contract.schema import Enclosure
    from realcad.verify.checks import _intersection_volume
    part = g.build_enclosure(Enclosure(board="arduino_uno"))
    b = g.BOARDS["arduino_uno"]
    outer_l, outer_w = b["l"] + 8, b["w"] + 8
    usb_y = 38.1 - b["w"] / 2
    assert _intersection_volume(part, Pos(-(outer_l - 2) / 2, usb_y, 14) * Box(2, 12, 11)) < 1e-3     # the USB slot
    long_wall = Pos(0, (outer_w - 2) / 2, 14) * Box(40, 2, 11)
    assert _intersection_volume(part, long_wall) == pytest.approx(40 * 2 * 11, rel=0.01)              # still solid


def test_closed_case_reports_no_connector_check():
    summ, fd = _run({"kind": "enclosure", "enclosure": {"board": "arduino_uno", "open_ports": False}})
    assert "E3" not in fd


def test_custom_board_says_its_connectors_are_unknown():
    summ, fd = _run({"kind": "enclosure", "enclosure": {"board": "custom", "board_l": 50, "board_w": 30,
                                                        "board_holes": [[3, 3], [47, 3], [3, 27], [47, 27]]}})
    assert fd["E3"].severity == "SOFT" and not fd["E3"].ok and summ["passed"]
