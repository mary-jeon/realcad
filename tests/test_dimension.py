from realcad.agent.codegen import declared_overall_mm, dimension_check

def test_declared_parse():
    assert declared_overall_mm("# Watering can 1.5 L: overall ~ 250 x 150 x 300 mm\n# spout Ø12\nx=1") == 300
    assert declared_overall_mm("# A4 = 210x297, keyboard case 283 x 111 x 11\nfrom build123d import *") == 297
    assert declared_overall_mm("# mug: Ø80 x 95 tall, wall 3\n") == 95
    assert declared_overall_mm("from build123d import *\npart=Box(1,1,1)") is None

def test_dimension_check_flags_collapse_and_passes_match():
    code = "# overall 250 x 150 x 300 mm\n"
    assert dimension_check(code, {"bbox": [12, 24, 103]}) is not None
    assert dimension_check(code, {"bbox": [240, 160, 290]}) is None
    assert dimension_check("x=1", {"bbox": [3, 3, 3]}) is not None     # under 8mm is suspicious even without a declaration


def test_separate_pieces_laid_side_by_side_are_not_too_big():
    code = "# overall 90 x 60 x 25 mm\n"
    assert dimension_check(code, {"bbox": [190.4, 61.4, 28.0], "nsolids": 2}) is None
    assert dimension_check(code, {"bbox": [190.4, 61.4, 28.0], "nsolids": 1}) is not None
    assert dimension_check(code, {"bbox": [20, 15, 8], "nsolids": 2}) is not None
