"""Sandbox regression: attacks are blocked and normal build123d code runs. (No Meta API)"""
import tempfile, pytest
from realcad.agent import sandbox

ATTACKS = [
    'from build123d import *\npart=Box(5,5,5)\nos.system("true")\n',
    'from build123d import *\npart=Box(5,5,5)\nexport_stl(part, "/tmp/x.stl")\n',
    'from build123d import *\npart=Box(5,5,5)\npart.export_stl("/tmp/x.stl")\n',
    'from build123d import os as o\npart=Box(5,5,5)\n',
    'import build123d as b\npart=b.Box(5,5,5)\nb.os.system("true")\n',
    'from build123d import *\npart=Box(5,5,5)\ns="{0.__class__}".format(part)\n',
    'from build123d import *\npart=Box(5,5,5)\nf=(lambda: 0)\nc=f.__code__\n',
    'from build123d import *\npart=Box(5,5,5)\nBRepTools.Write_s(part.wrapped, "/tmp/x.brep")\n',
    'from build123d import *\npart=Box(5,5,5)\ng=getattr(part,"ex"+"port_stl")\n',
    'from build123d.topology import Shape\npart=Box(5,5,5)\n',
    'import math as os\nfrom build123d import *\npart=Box(5,5,5)\n',
    'from build123d import *\npart=Box(5,5,5)\nrequests.get("http://127.0.0.1:1")\n',
]
LEGIT = [
    'from build123d import *\nouter=Cylinder(radius=40,height=95)\ninner=Pos(0,0,4)*Cylinder(radius=37,height=95)\npart=outer-inner\n',
    'import build123d as b\nimport math\npart=b.Box(10,10,10)-b.Cylinder(radius=2,height=30)\n',
    'from build123d import Box, fillet, Axis\nb=Box(20,20,10)\npart=fillet(b.edges().filter_by(Axis.Z), radius=2)\n',
    'from build123d import *\nwith BuildPart() as bp:\n    Box(20,20,10)\npart=bp.part\n',
]


@pytest.mark.parametrize("code", ATTACKS)
def test_attack_blocked(code):
    td = tempfile.mkdtemp()
    with pytest.raises(sandbox.SandboxError):
        sandbox.validate(code)
        sandbox.execute_to_files(code, td + "/a.stl", td + "/a.step")


@pytest.mark.parametrize("code", LEGIT)
def test_legit_runs(code):
    td = tempfile.mkdtemp()
    r = sandbox.execute_to_files(code, td + "/a.stl", td + "/a.step")
    assert r["ok"] and r["nsolids"] == 1 and r["watertight"] is True


def test_unfused_overlap_is_rejected_with_fix_hint():
    code = 'from build123d import *\na=Box(20,20,20)\nb=Pos(10,0,0)*Box(20,20,20)\npart=Compound(children=[a,b])\n'
    td = tempfile.mkdtemp()
    with pytest.raises(sandbox.SandboxError, match="융합"):
        sandbox.execute_to_files(code, td + "/a.stl", td + "/a.step")


def test_separate_pieces_allowed():
    code = 'from build123d import *\na=Box(20,20,20)\nb=Pos(40,0,0)*Box(20,20,20)\npart=Compound(children=[a,b])\n'
    td = tempfile.mkdtemp()
    r = sandbox.execute_to_files(code, td + "/a.stl", td + "/a.step")
    assert r["ok"] and r["nsolids"] == 2


def test_cpu_limit_kills_infinite_loop():
    code = 'from build123d import *\npart=Box(5,5,5)\nwhile True:\n    pass\n'
    td = tempfile.mkdtemp()
    with pytest.raises(sandbox.SandboxError):
        sandbox.execute_to_files(code, td + "/a.stl", td + "/a.step", timeout=20)


def test_floating_piece_rejected_but_touching_assembly_allowed():
    floating = 'from build123d import *\nbase=Box(40,20,4)\nhook=Pos(0,0,15)*Cylinder(radius=2,height=6)\npart=Compound(children=[base,hook])\n'
    td = tempfile.mkdtemp()
    with pytest.raises(sandbox.SandboxError, match="공중"):
        sandbox.execute_to_files(floating, td + "/a.stl", td + "/a.step")
    on_bed = 'from build123d import *\nbody=Pos(0,0,15)*Box(60,40,30)\nlid=Pos(80,0,1.5)*Box(62,42,3)\npart=Compound(children=[body,lid])\n'
    r = sandbox.execute_to_files(on_bed, td + "/b.stl", td + "/b.step")
    assert r["ok"] and r["nsolids"] == 2
