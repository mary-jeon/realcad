"""Sandbox that runs generated build123d code safely.

LLM-written Python is untrusted. Two layers of defense:
  1) AST static validation: blocks imports (other than math/build123d), file/network access,
     dunder access, and dangerous names like exec/eval/open/__import__ up front.
  2) Separate process: runs under `python -I` with CPU and time limits so a runaway
     loft/boolean cannot hog the server. Even if the code does something, it cannot
     reach the parent (web server) process.

Not a complete security sandbox (no real OS sandbox/seccomp). Trust boundary:
**local development tool**. Do not expose it on a public tunnel for strangers to generate code.

Success: {"ok":True,"nsolids":int,"is_valid":bool,"volume":float,"bbox":[dx,dy,dz]}
Failure: SandboxError (human-readable message); this message is the input to the auto-repair loop.
"""
from __future__ import annotations
import ast
import json
import subprocess
import sys
import tempfile
from pathlib import Path


class SandboxError(Exception):
    """Code validation or execution failure. The message goes verbatim into the LLM retry prompt."""


# ───────────────────────── 1) AST static validation ─────────────────────────

_ALLOWED_IMPORTS = {"math", "build123d"}
_BANNED_NAMES = {
    # standard modules re-exported by build123d: never placed in harness globals, but the names are blocked too
    "os", "sys", "ctypes", "io", "tempfile", "pathlib", "Path", "copy", "subprocess",
    "shutil", "socket", "importlib", "builtins",
    "eval", "exec", "compile", "open", "__import__", "input",
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
    "exit", "quit", "help", "breakpoint", "memoryview", "classmethod",
    "staticmethod", "super", "object", "type",
}


import re as _re
# file, network and serialization: export_*/import_*/Mesher/... exposed by build123d/OCP, and Shape.export_* methods
_BANNED_PATTERN = _re.compile(
    r"^(export|import|Export|Import|save|load|write|read|to_file|from_file|download|upload|fetch|open)"
    r"|^(Mesher|mesher|exporters|importers|persistence|StlAPI|RWStl|RWGltf|STEP|IGES|BRepTools|Lib3MF|ezdxf|"
    r"svgpathtools|requests|webbrowser|format|format_map|__)"
)


def _banned(name: str) -> bool:
    return name in _BANNED_NAMES or bool(_BANNED_PATTERN.match(name))


def validate(code: str) -> None:
    """Raise SandboxError on dangerous constructs; return None if clean."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        raise SandboxError(f"문법 오류 / SyntaxError (line {e.lineno}): {e.msg}") from e
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name not in _ALLOWED_IMPORTS or (a.asname and _banned(a.asname)):
                    raise SandboxError(f"허용되지 않은 import: '{a.name}' "
                                       f"(math, build123d 만 가능)")
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if mod not in _ALLOWED_IMPORTS or (node.module or "") not in _ALLOWED_IMPORTS:
                raise SandboxError(f"허용되지 않은 import: '{node.module}' "
                                   f"(math, build123d 만 가능, 하위모듈 불가)")
            for a in node.names:                       # block `from build123d import os as o`
                if a.name != "*" and (_banned(a.name) or (a.asname and _banned(a.asname))):
                    raise SandboxError(f"허용되지 않은 import 이름: '{a.name}'")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                raise SandboxError(f"금지된 dunder 속성 접근: '{node.attr}'")
            if _banned(node.attr):
                raise SandboxError(f"금지된 속성/메서드: '.{node.attr}' (파일, 네트워크, 직렬화 계열은 사용 불가)")
        elif isinstance(node, ast.Name):
            if _banned(node.id):
                raise SandboxError(f"금지된 이름 사용: '{node.id}'")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # block dunder leaks via string formatting, e.g. "{0.__class__}".format(x)
            if "__" in node.value and "{" in node.value:
                raise SandboxError("문자열 안의 dunder 포맷 접근은 금지")


# ───────────────────── 2) Isolated process harness ─────────────────────
# argv: [harness] <code_file> <stl_out> <step_out>; result JSON on the last stdout line.

_HARNESS = r'''
import sys, json, math, resource, builtins as _bi

# CPU 25 s (raised to 60 s for a mesh-mode rerun) and 3 GB memory; the OS kills the process past them
try:
    resource.setrlimit(resource.RLIMIT_CPU, (25, 60))
except Exception: pass
try:
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
except Exception: pass

code_file, stl_out, step_out = sys.argv[1], sys.argv[2], sys.argv[3]
bases_dir = sys.argv[4] if len(sys.argv) > 4 else ""
code = open(code_file, "r", encoding="utf-8").read()

import build123d as _b
from build123d import Part, Solid, Compound, export_stl, export_step
try:
    from build123d import BuildPart
except Exception:
    BuildPart = ()

# guarded __import__ that only lets the allowed modules through
_ALLOWED = {"math", "build123d"}
_orig_import = _bi.__import__
_PROXY = None   # stand-in build123d module, filled below with the allowed globals (g)
def _guarded_import(name, *a, **k):
    if name == "math":
        return math
    if name == "build123d" and _PROXY is not None:
        return _PROXY          # so neither `from build123d import os` nor `b.os` works
    raise ImportError("import 차단: " + name)

_SAFE_BUILTIN_NAMES = ("range","len","int","float","abs","min","max","round","sum",
  "pow","divmod","enumerate","zip","list","tuple","dict","set","frozenset","bool",
  "str","repr","sorted","reversed","map","filter","print","any","all","isinstance",
  "hasattr","complex","bytes","format","ValueError","TypeError","ZeroDivisionError",
  "ArithmeticError","RuntimeError","Exception","True","False","None")
_sb = {}
for _n in _SAFE_BUILTIN_NAMES:
    if hasattr(_bi, _n): _sb[_n] = getattr(_bi, _n)
_sb["__import__"] = _guarded_import

import types as _types, re as _re
_BLOCK = {"os", "sys", "ctypes", "io", "tempfile", "Path", "PathLike", "copy", "subprocess", "shutil",
          "socket", "importlib", "builtins", "pathlib", "requests", "webbrowser", "json", "logging",
          "inspect", "np", "ET", "PT", "TopoDS", "Lib3MF", "ezdxf", "svgpathtools", "colorsys",
          "export_to_pcbway", "brep_from_stl"}
_BAD = _re.compile(r"^(export|import|Export|Import|Mesher|mesher|exporters|importers|persistence|"
                   r"StlAPI|RWStl|RWGltf|STEP|IGES|BRepTools|BRep_|BRepBuilderAPI|BRepLib|BRepMesh|"
                   r"BRepGProp|BRepBndLib|HLRBRep|GccEnt|save|load|write|read|open|download|upload)")
g = {"__builtins__": _sb, "math": math}
for _n in dir(_b):
    if _n.startswith("_") or _n in _BLOCK or _BAD.match(_n):
        continue
    _v = getattr(_b, _n)
    if isinstance(_v, _types.ModuleType):      # leave out every module build123d imported (os, sys, ctypes, requests)
        continue
    _m = getattr(_v, "__module__", "") or ""
    if not (_m.startswith("build123d") or _m == "math" or _m == "builtins"):
        continue                                # no OCP classes or other libraries' objects
    g[_n] = _v
# Starting shape: if the code has "# RealCAD-BASE: <name>.step", the trusted harness reads it from the server's bases folder as BASE,
# so sketches and extrusions can continue a part that has no code (a template part). Names are alphanumeric, nothing outside the folder.
_mb = _re.search(r"^# RealCAD-BASE: ([A-Za-z0-9_-]{1,64}\.step)\s*$", code, _re.M)
if _mb and bases_dir:
    import os.path as _op
    _bp = _op.realpath(_op.join(bases_dir, _mb.group(1)))
    if _op.dirname(_bp) == _op.realpath(bases_dir) and _op.exists(_bp):
        from build123d import import_step as _imp_step
        g["BASE"] = _imp_step(_bp)
_PROXY = _types.ModuleType("build123d")
for _k, _v in g.items():
    if _k not in ("__builtins__",):
        setattr(_PROXY, _k, _v)
_PROXY.__all__ = [k for k in g if k != "__builtins__"]
_sb["__import__"] = _guarded_import

def done(obj):
    print(json.dumps(obj))
    sys.exit(0)

_g0 = dict(g)   # clean globals, kept for a mesh-mode rerun
_KERNEL_ERR = _re.compile(r"Null TopoDS|StdFail|Standard_|BOPAlgo|not done|IsDone|kernel", _re.I)


def _mesh_rerun(reason):
    """The CAD kernel failed to union or cut. Run the same code again, but do every +, - and & on
    closed triangle meshes (manifold3d), then sew the result back into a STEP solid."""
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    except Exception:
        pass
    import ast as _ast
    import numpy as _np
    import trimesh as _tm
    import manifold3d as _mf
    from build123d.topology import Shape as _Shape
    gm = dict(_g0)
    skipped = []

    def to_mf(x):
        if isinstance(x, _mf.Manifold):
            return x
        v, t = x.tessellate(0.05, 0.3)
        m = _tm.Trimesh(_np.array([[p.X, p.Y, p.Z] for p in v]), _np.array(t), process=True)
        m.merge_vertices(); m.fix_normals()
        r = _mf.Manifold(_mf.Mesh(vert_properties=_np.asarray(m.vertices, dtype=_np.float32),
                                  tri_verts=_np.asarray(m.faces, dtype=_np.uint32)))
        if r.status() != _mf.Error.NoError:
            raise ValueError("not a closed solid")
        return r

    geo = lambda x: isinstance(x, (_Shape, _mf.Manifold))
    OPS = {_ast.Add: "add", _ast.Sub: "sub", _ast.BitAnd: "and"}

    def ev(node):
        if isinstance(node, _ast.BinOp) and type(node.op) in OPS:
            a, b = ev(node.left), ev(node.right)
            op = OPS[type(node.op)]
            if geo(a) and geo(b):
                A, B = to_mf(a), to_mf(b)
                return A + B if op == "add" else (A - B if op == "sub" else A ^ B)
            return a + b if op == "add" else (a - b if op == "sub" else a & b)
        if isinstance(node, _ast.BinOp) and isinstance(node.op, _ast.Mult):
            a, b = ev(node.left), ev(node.right)
            if isinstance(b, _mf.Manifold) and isinstance(a, _b.Location):
                t = a.wrapped.Transformation()
                return b.transform(_np.array([[t.Value(i, j) for j in range(1, 5)] for i in range(1, 4)]))
            return a * b
        return eval(compile(_ast.Expression(node), "<generated>", "eval"), gm)

    def run(stmts):
        for st in stmts:
            try:
                if isinstance(st, _ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], _ast.Name):
                    gm[st.targets[0].id] = ev(st.value)
                elif isinstance(st, _ast.AugAssign) and isinstance(st.target, _ast.Name) and type(st.op) in OPS:
                    gm[st.target.id] = ev(_ast.BinOp(left=_ast.Name(st.target.id, _ast.Load()), op=st.op, right=st.value))
                elif isinstance(st, _ast.For) and isinstance(st.target, _ast.Name) and not st.orelse:
                    for item in ev(st.iter):
                        gm[st.target.id] = item
                        run(st.body)
                elif isinstance(st, _ast.If):
                    run(st.body if ev(st.test) else st.orelse)
                elif isinstance(st, _ast.Try):
                    run(st.body)
                else:
                    exec(compile(_ast.Module([st], []), "<generated>", "exec"), gm)
            except Exception as e:
                skipped.append("line %s: %s" % (getattr(st, "lineno", "?"), (type(e).__name__ + ": " + str(e))[:80]))

    run(_ast.parse(code).body)
    part = gm.get("part")
    if part is None:
        done({"ok": False, "error": "코드가 최종 솔리드를 `part` 변수에 넣지 않았습니다."})
    try:
        M = to_mf(part).to_mesh()
        m = _tm.Trimesh(_np.asarray(M.vert_properties)[:, :3], _np.asarray(M.tri_verts), process=True)
    except Exception as e:
        done({"ok": False, "error": "합치기 실패 (CAD 엔진, 메시 둘 다): " + str(e)[:200] + " / 처음 오류: " + reason[:200]})
    bodies = len(m.split(only_watertight=False))
    if bodies > 1:
        done({"ok": False, "error": "공중에 뜬 분리 조각이 %d개 있습니다. 붙어야 할 부품은 이웃 부품에 2mm 이상 파묻어 + 로 융합하세요." % (bodies - 1)})
    m.export(stl_out)
    try:
        from OCP.StlAPI import StlAPI_Reader
        from OCP.TopoDS import TopoDS_Shape, TopoDS
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
        from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
        raw = TopoDS_Shape(); StlAPI_Reader().Read(raw, stl_out)
        sew = BRepBuilderAPI_Sewing(1e-4); sew.Add(raw); sew.Perform()
        solid = BRepBuilderAPI_MakeSolid(TopoDS.Shell(sew.SewedShape())).Solid()
        uni = ShapeUpgrade_UnifySameDomain(solid, True, True, True); uni.Build()
        export_step(Solid(uni.Shape()), step_out)
    except Exception as e:
        done({"ok": False, "error": "메시를 STEP 으로 바꾸지 못했습니다: " + type(e).__name__ + ": " + str(e)[:200]})
    ext = [round(float(x), 2) for x in m.extents]
    done({"ok": True, "nsolids": 1, "is_valid": True, "watertight": bool(m.is_watertight), "bodies": bodies,
          "volume": float(m.volume), "bbox": ext, "mesh": True, "mesh_reason": reason[:160], "skipped": skipped[:6]})


try:
    exec(compile(code, "<generated>", "exec"), g)
except Exception as e:
    _msg = type(e).__name__ + ": " + str(e)[:400]
    if _KERNEL_ERR.search(_msg):
        _mesh_rerun(_msg)
    done({"ok": False, "error": _msg})

part = g.get("part")
if part is None:
    done({"ok": False, "error": "코드가 최종 솔리드를 `part` 변수에 넣지 않았습니다."})

# unwrap builder objects such as BuildPart via .part
if BuildPart and isinstance(part, BuildPart):
    part = part.part
elif hasattr(part, "part") and not hasattr(part, "solids"):
    part = part.part

# normalise to a Part
try:
    if not isinstance(part, (Part, Solid, Compound)):
        # a Sketch or Wire is not a 3D solid
        done({"ok": False, "error": "`part`가 3D 솔리드가 아닙니다 (" + type(part).__name__ + "). Box/Cylinder/extrude/revolve 등으로 솔리드를 만드세요."})
    solids = part.solids()
    nsolids = len(solids)
    if nsolids == 0:
        done({"ok": False, "error": "솔리드가 0개입니다 (빈 형상). 치수·불리언을 확인하세요."})
    is_valid = bool(part.is_valid) if hasattr(part, "is_valid") else True
    vol = float(sum(s.volume for s in solids))
    if vol <= 1e-6:
        done({"ok": False, "error": "부피가 0입니다. 형상이 비었거나 불리언이 전부 깎여 나갔습니다."})
    bb = part.bounding_box()
    dx = float(bb.max.X - bb.min.X); dy = float(bb.max.Y - bb.min.Y); dz = float(bb.max.Z - bb.min.Z)
except Exception as e:
    done({"ok": False, "error": "형상 측정 실패: " + type(e).__name__ + ": " + str(e)[:300]})

# solids that overlap without being fused (checked only for 10 or fewer; a 40+ Compound array overlaps on purpose)
overlaps = []
if 2 <= nsolids <= 10:
    for i in range(nsolids):
        for j in range(i + 1, nsolids):
            try:
                inter = solids[i] & solids[j]
                v = float(inter.volume) if inter is not None else 0.0
            except Exception:
                v = 0.0
            if v > 0.5:
                overlaps.append((i, j, round(v, 1)))
floating = []
if 2 <= nsolids <= 10:
    try:
        zmin_all = min(float(s.bounding_box().min.Z) for s in solids)
        for i, s_ in enumerate(solids):
            if float(s_.bounding_box().min.Z) - zmin_all > 0.5:      # above the lowest piece
                # raised but touching another solid (distance 0) counts as assembled
                touching = False
                for j, o in enumerate(solids):
                    if i == j: continue
                    try:
                        if float((s_ & o).volume) > 1e-6 or s_.distance_to(o) < 1e-3:
                            touching = True; break
                    except Exception:
                        pass
                if not touching:
                    floating.append((i, round(float(s_.bounding_box().min.Z) - zmin_all, 1)))
    except Exception:
        floating = []
if nsolids > 10:
    # many solids (an intended Compound array): a raised piece whose box touches no other piece is floating
    try:
        _bbs = [s_.bounding_box() for s_ in solids]
        _z0 = min(float(b_.min.Z) for b_ in _bbs)
        def _near(a_, b_, e=0.01):
            return not (a_.max.X < b_.min.X - e or b_.max.X < a_.min.X - e or a_.max.Y < b_.min.Y - e or
                        b_.max.Y < a_.min.Y - e or a_.max.Z < b_.min.Z - e or b_.max.Z < a_.min.Z - e)
        for i, b_ in enumerate(_bbs):
            if float(b_.min.Z) - _z0 > 0.5 and not any(_near(b_, _bbs[j]) for j in range(nsolids) if j != i):
                floating.append((i, round(float(b_.min.Z) - _z0, 1)))
    except Exception:
        pass
if floating:
    desc = ", ".join("solid%d (바닥 위 %.1fmm)" % o for o in floating[:4])
    done({"ok": False, "error": "공중에 뜬 분리 솔리드가 있습니다 (%s). 붙어야 할 부품(고리, 손잡이, 다리)이면 몸체에 2mm 이상 파묻어 "
          "+ 로 융합하세요. 별도 출력 부품이면 바닥(z=0)에 내려놓으세요." % desc})
if overlaps:
    desc = ", ".join("solid%d∩solid%d=%.0fmm³" % o for o in overlaps[:4])
    done({"ok": False, "error": "솔리드 %d개가 서로 겹치기만 하고 융합되지 않았습니다 (%s). "
          "같은 부품에 속하는 형상은 body = body + feature 로 반드시 + 융합해 ONE solid 로 만드세요(2mm 이상 파묻기). "
          "정말 분리 부품(뚜껑 등)이면 서로 겹치지 않게 떨어뜨리세요." % (nsolids, desc)})

# export
try:
    export_stl(part, stl_out, tolerance=0.01, angular_tolerance=0.1)
    export_step(part, step_out)
except Exception as e:
    done({"ok": False, "error": "내보내기 실패: " + type(e).__name__ + ": " + str(e)[:300]})

# watertight on the mesh (degenerate faces at sphere poles are cleaned first)
watertight, bodies = None, None
try:
    import trimesh
    m = trimesh.load(stl_out)
    mask = m.area_faces > 1e-9
    if not bool(mask.all()):
        m.update_faces(mask); m.remove_unreferenced_vertices(); m.merge_vertices()
        m.export(stl_out)
    watertight = bool(m.is_watertight)
    bodies = len(m.split(only_watertight=False))
except Exception:
    pass
if watertight is False:
    _mesh_rerun("kernel result is not watertight (%s pieces)" % bodies)
    done({"ok": False, "error": "내보낸 메시가 닫혀 있지 않습니다(non-watertight, 조각 %s개). "
          "면이 서로 스치거나(0두께) 붙지 않은 형상이 있습니다. 겹치는 부위를 2mm 이상 파묻어 융합하고, "
          "접하기만 하는(touching) 배치를 피하세요." % bodies})

done({"ok": True, "nsolids": nsolids, "is_valid": is_valid, "watertight": watertight, "bodies": bodies,
      "volume": vol, "bbox": [round(dx,2), round(dy,2), round(dz,2)]})
'''


MAX_RSS_MB = 3072   # macOS ignores RLIMIT_AS/DATA, so the parent watches RSS and kills the child


def _rss_mb(pid: int) -> float:
    """Child process resident memory (MB), read via ps to stay platform independent."""
    try:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=2).stdout
        return int(out.strip() or 0) / 1024.0
    except Exception:
        return 0.0


def _run_watched(cmd: list[str], timeout: float, max_rss_mb: int):
    """subprocess.run replacement that enforces time and memory (RSS) limits from the parent."""
    import time as _time
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    t0 = _time.monotonic(); reason = None
    while True:
        try:
            out, err = proc.communicate(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            pass
        if _time.monotonic() - t0 > timeout:
            reason = f"실행 시간 초과({timeout:.0f}초): 모양이 너무 복잡하거나 계산이 끝나지 않아요. 더 단순하게."
        elif _rss_mb(proc.pid) > max_rss_mb:
            reason = f"메모리 초과({max_rss_mb} MB): 모양이나 반복 배치가 너무 커요. 더 단순하게."
        if reason:
            proc.kill()
            try: proc.communicate(timeout=5)
            except Exception: pass
            raise SandboxError(reason)

    class _R:  # mimics only the shape of subprocess.CompletedProcess
        pass
    r = _R(); r.stdout, r.stderr, r.returncode = out, err, proc.returncode
    return r


BASES_DIR = Path(__file__).resolve().parents[3] / "out" / "bases"   # stores starting-shape STEP files (not shown on the web, not cleaned up)
BASES_DIR.mkdir(parents=True, exist_ok=True)


# ───────────────────── 3) Union diagnosis (which part breaks it) ─────────────────────
# Rewrite the final big union `part = a + b + c + ...` of the generated code, leaving earlier code as-is,
# into code that adds one part at a time and checks validity and piece count each step, run in the **same sandbox**.
# Results come back only as an exception message (RCDIAG:...), with no files or output.

DIAG_TRIGGER = _re.compile(r"Null TopoDS|is_valid|StdFail|BRep|Boolean|BOP|fuse|공중에 뜬|융합되지 않았|닫혀 있지 않습니다|"
                           r"솔리드가 0개|부피가 0|형상 측정 실패", _re.I)


def _flatten_add(node):
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _flatten_add(node.left) + _flatten_add(node.right)
    return [node]


def _diag_label(node, k: int) -> str:
    s = ast.unparse(node) if hasattr(ast, "unparse") else f"part{k}"
    s = _re.sub(r"[^A-Za-z0-9_.,()*+ -]", "", s)[:32]
    return s or f"part{k}"


def diagnose(code: str, timeout: float = 60.0) -> dict | None:
    """Redo a broken union one part at a time to find the offending part.

    Returns: {"kind": SELFINVALID|INVALID|SEPARATE|FAIL|OK, "part": name, "en": explanation for the model, "ko": one line for the UI} or None
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    best = None
    for st in tree.body:
        if (isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name)
                and st.targets[0].id == "part"):
            ops = _flatten_add(st.value)
            if len(ops) >= 3 and (best is None or len(ops) >= len(best[1])):
                best = (st, ops)
    if not best:
        return None
    st, ops = best
    labels = [_diag_label(o, k) for k, o in enumerate(ops)]
    head = "\n".join(code.splitlines()[:st.lineno - 1])
    items = ",\n".join(f"    ({labels[k]!r}, {ast.unparse(o)})" for k, o in enumerate(ops))
    probe = head + "\n_rc_items = [\n" + items + "\n]\n" + r'''
_rc_bad = ""
for _rc_n, _rc_s in _rc_items:
    try:
        if not bool(_rc_s.is_valid):
            _rc_bad = "SELFINVALID|" + _rc_n + "|"
            break
    except Exception as _rc_e:
        _rc_bad = "SELFINVALID|" + _rc_n + "|" + str(_rc_e)[:60]
        break
if not _rc_bad:
    _rc_acc = _rc_items[0][1]
    for _rc_n, _rc_s in _rc_items[1:]:
        try:
            _rc_t = _rc_acc + _rc_s
            _rc_v = bool(_rc_t.is_valid)
        except Exception as _rc_e:
            _rc_bad = "FAIL|" + _rc_n + "|" + str(_rc_e)[:60]
            break
        if not _rc_v:
            _rc_bad = "INVALID|" + _rc_n + "|" + str(len(_rc_t.solids()))
            break
        _rc_acc = _rc_t
# Pieces can stay apart while the union is half done (a left leg before the hip joins it), so
# separation is judged only on the finished union: name the parts that do not touch the biggest piece.
if not _rc_bad and len(_rc_acc.solids()) > 1:
    _rc_main = max(_rc_acc.solids(), key=lambda _s: _s.volume)
    _rc_lone = []
    for _rc_n, _rc_s in _rc_items:
        try:
            if _rc_s.distance_to(_rc_main) > 1e-3:
                _rc_lone.append(_rc_n)
        except Exception:
            pass
    _rc_bad = "SEPARATE|" + ", ".join(_rc_lone[:3]) + "|" + str(len(_rc_acc.solids()))
raise ValueError("RCDIAG:" + (_rc_bad or "OK||"))
'''
    with tempfile.TemporaryDirectory() as td:
        try:
            execute_to_files(probe, Path(td) / "d.stl", Path(td) / "d.step", timeout=timeout)
            return None
        except SandboxError as e:
            msg = str(e)
    m = _re.search(r"RCDIAG:([A-Z]+)\|([^|]*)\|(.*)$", msg)
    if not m:
        return None
    kind, name, extra = m.group(1), m.group(2), m.group(3).strip()
    common = ("Typical causes: a face of it grazes another part tangentially or meets it with zero overlap; "
              "a sphere's pole or seam lies on another cylinder's axis (rotate that sphere with Rot so its axis matches the cylinder); "
              "a sphere stretched with scale() (build an ellipsoid by revolving an Ellipse instead); a torus resting on a curved surface "
              "(use a thin Cylinder disk slightly bigger than the body instead). Overlap attached parts by >= 2 mm.")
    if kind == "OK":
        return {"kind": "OK", "part": "", "en": "Fusing the listed parts one by one worked, so the problem is in a later step after the main fuse.",
                "ko": "부품을 하나씩 합쳐 보면 문제없음: 합친 뒤 단계에서 깨짐"}
    if kind == "SELFINVALID":
        return {"kind": kind, "part": name, "en": f"RealCAD engine diagnosis: the shape `{name}` is itself an invalid solid before any fuse. Rebuild it. {common}",
                "ko": f"`{name}` 부품 자체가 깨진 모양이에요"}
    if kind == "SEPARATE":
        return {"kind": kind, "part": name, "en": f"RealCAD engine diagnosis: after fusing every part, `{name}` is still a separate piece "
                f"({extra} pieces in total): it does not overlap what it should attach to (maybe it only touches face to face or floats). "
                f"Move or enlarge `{name}` so it sinks >= 2 mm into its neighbour.",
                "ko": f"`{name}` 가 몸체에서 떨어져 있음(맞닿기만 하거나 떠 있음)"}
    if kind == "INVALID":
        return {"kind": kind, "part": name, "en": f"RealCAD engine diagnosis: fusing the parts one by one, everything before `{name}` fused into one valid solid, "
                f"but adding `{name}` made the solid INVALID. Fix `{name}`. {common}",
                "ko": f"`{name}` 를 더할 때 모양이 깨짐(유효하지 않은 솔리드)"}
    return {"kind": "FAIL", "part": name, "en": f"RealCAD engine diagnosis: the fuse crashed when adding `{name}` ({extra}). Fix `{name}`. {common}",
            "ko": f"`{name}` 를 더할 때 합치기가 실패함"}


def execute_to_files(code: str, stl_out: str | Path, step_out: str | Path,
                     timeout: float = 75.0) -> dict:
    """Run code isolated and write STL/STEP files. Returns a measurement dict; raises SandboxError on failure."""
    validate(code)   # first static check (the harness blocks imports again too)
    with tempfile.TemporaryDirectory() as td:
        cf = Path(td) / "gen_code.py"
        hf = Path(td) / "harness.py"
        cf.write_text(code, encoding="utf-8")
        hf.write_text(_HARNESS, encoding="utf-8")
        proc = _run_watched([sys.executable, "-I", str(hf), str(cf), str(stl_out), str(step_out), str(BASES_DIR)],
                            timeout=timeout, max_rss_mb=MAX_RSS_MB)
        so = proc.stdout or ""
        if len(so) > 2_000_000:                 # for output over 2MB keep only the tail (result JSON is on the last line)
            so = so[-200_000:]
        out = so.strip().splitlines()
        last = out[-1] if out else ""
        try:
            res = json.loads(last)
        except Exception:
            err = (proc.stderr or "").strip()[-500:] or "(출력 없음)"
            raise SandboxError(f"실행 프로세스 비정상 종료(code {proc.returncode}): {err}")
        if not res.get("ok"):
            raise SandboxError(res.get("error", "알 수 없는 실행 오류"))
        return res
