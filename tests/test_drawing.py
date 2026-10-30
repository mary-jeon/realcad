import tempfile, os
from realcad.contract.schema import DesignContract as D
from realcad.geometry.builder import build_from_contract
from realcad.export.drawing import write_drawing


def test_plate_drawing_has_dimensions_and_mm_units():
    c = D.from_dict({"kind": "plate", "plate": {"length": 80, "width": 40, "thickness": 5}, "fastener": "M4",
                     "holes": [{"x": -25, "y": 0}, {"x": 25, "y": 0}]})
    part, f, dia = build_from_contract(c)
    p = write_drawing(part, os.path.join(tempfile.mkdtemp(), "a.dxf"), z=-2.5, contract=c, fastener=f)
    t = open(p).read()
    assert t.count("\nDIMENSION") >= 4 and "$INSUNITS" in t and "HOLE" in t and "M4" in t
