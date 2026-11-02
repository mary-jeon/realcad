"""Motion frames for the viewer: one input value drives the moving parts, numbers measured on the same solids."""
import numpy as np
import pytest

from realcad.contract.schema import DesignContract as D
from realcad.pipeline import build_and_verify
from realcad.mech.animate import motion_frames


def _asm(preset):
    part, *_ = build_and_verify(D.from_dict({"kind": "assembly", "assembly": {"preset": preset}}))
    return part._rc_asm


def test_eccentric_slider_runs_a_full_turn_and_its_stroke_is_2e():
    asm = _asm("eccentric_slider")
    m = motion_frames(asm)
    assert m["unit"] == "deg" and m["values"][0] == 0 and m["values"][-1] == 360
    assert {"슬라이더", "링크(크랭크)", "편심축"} <= set(m["parts"])
    pos = [r["슬라이더"]["pos_mm"] for r in m["readout"]]
    assert abs((max(pos) - min(pos)) - asm.layout["stroke"]) < 0.05          # the numbers come from the solids
    turn = [r["편심축"]["turn_deg"] for r in m["readout"]]
    assert abs(turn[9] - 90) < 0.5 and abs(turn[27] - 270) < 0.5               # a full turn reads 0 to 360
    for name, frames in m["parts"].items():                                   # each frame is a 3x4 rigid move
        R = np.array(frames[9]).reshape(3, 4)[:, :3]
        assert np.allclose(R @ R.T, np.eye(3), atol=1e-6), name


def test_vise_slides_by_its_opening():
    m = motion_frames(_asm("vise"))
    assert m["unit"] == "mm"
    last = m["readout"][-1]["이동조"]
    assert abs(last["move_mm"] - m["values"][-1]) < 1e-6 and last["turn_deg"] == 0


def test_a_part_with_no_motion_gives_none():
    from types import SimpleNamespace as NS
    assert motion_frames(NS(motion=None)) is None
