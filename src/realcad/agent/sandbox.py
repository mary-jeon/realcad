"""생성된 build123d 코드를 안전하게 실행하는 샌드박스.

LLM이 짠 파이썬 코드는 신뢰할 수 없다. 두 겹으로 막는다:
  1) AST 정적 검증 — import(math/build123d 외) · 파일/네트워크 · dunder 접근 ·
     exec/eval/open/__import__ 같은 위험 이름을 사전 차단.
  2) 별도 프로세스 격리 — `python -I` 로 격리 실행, CPU·시간 제한을 걸어
     돌아버리는 로프트/불리언이 서버를 잡아먹지 못하게 한다. 메모리상 격리라
     설령 코드가 뭔가 해도 부모(웹서버) 프로세스엔 닿지 않는다.

완벽한 보안 샌드박스는 아니다(진짜 OS 샌드박스/seccomp 아님). 신뢰 경계:
**로컬 개발 도구**. 공개 터널에 열어두고 낯선 사람에게 코드를 생성시키지 말 것.

성공: {"ok":True,"nsolids":int,"is_valid":bool,"volume":float,"bbox":[dx,dy,dz]}
실패: SandboxError(사람이 읽을 수 있는 메시지) — 이 메시지가 auto-repair 루프의 입력.
"""
from __future__ import annotations
import ast
import json
import subprocess
import sys
import tempfile
from pathlib import Path


class SandboxError(Exception):
    """코드 검증·실행 실패. 메시지는 LLM 재시도 프롬프트에 그대로 들어간다."""


# ───────────────────────── 1) AST 정적 검증 ─────────────────────────

_ALLOWED_IMPORTS = {"math", "build123d"}
_BANNED_NAMES = {
    # build123d 가 re-export 하는 표준 모듈들 — 하네스 전역에 절대 넣지 않지만 이름 자체도 막는다
    "os", "sys", "ctypes", "io", "tempfile", "pathlib", "Path", "copy", "subprocess",
    "shutil", "socket", "importlib", "builtins",
    "eval", "exec", "compile", "open", "__import__", "input",
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
    "exit", "quit", "help", "breakpoint", "memoryview", "classmethod",
    "staticmethod", "super", "object", "type",
}


import re as _re
# 파일·네트워크·직렬화 계열: build123d/OCP 가 노출하는 export_*/import_*/Mesher/… 와 Shape.export_* 메서드
_BANNED_PATTERN = _re.compile(
    r"^(export|import|Export|Import|save|load|write|read|to_file|from_file|download|upload|fetch|open)"
    r"|^(Mesher|mesher|exporters|importers|persistence|StlAPI|RWStl|RWGltf|STEP|IGES|BRepTools|Lib3MF|ezdxf|"
    r"svgpathtools|requests|webbrowser|format|format_map|__)"
)


def _banned(name: str) -> bool:
    return name in _BANNED_NAMES or bool(_BANNED_PATTERN.match(name))


def validate(code: str) -> None:
    """위험 구문이 있으면 SandboxError. 통과하면 None."""
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
            for a in node.names:                       # from build123d import os as o  차단
                if a.name != "*" and (_banned(a.name) or (a.asname and _banned(a.asname))):
                    raise SandboxError(f"허용되지 않은 import 이름: '{a.name}'")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                raise SandboxError(f"금지된 dunder 속성 접근: '{node.attr}'")
            if _banned(node.attr):
                raise SandboxError(f"금지된 속성/메서드: '.{node.attr}' (파일·네트워크·직렬화 계열은 사용 불가)")
        elif isinstance(node, ast.Name):
            if _banned(node.id):
                raise SandboxError(f"금지된 이름 사용: '{node.id}'")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # "{0.__class__}".format(x) 류 — 문자열 포맷으로 dunder 를 우회하는 정보 누출 차단
            if "__" in node.value and "{" in node.value:
                raise SandboxError("문자열 안의 dunder 포맷 접근은 금지")


# ───────────────────── 2) 격리 프로세스 하네스 ─────────────────────
# argv: [harness] <code_file> <stl_out> <step_out> ; 결과 JSON을 stdout 마지막 줄에.

_HARNESS = r'''
import sys, json, math, resource, builtins as _bi

# CPU 25초, 메모리 3GB 제한(초과 시 커널이 프로세스 종료)
try:
    resource.setrlimit(resource.RLIMIT_CPU, (25, 25))
except Exception: pass
try:
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
except Exception: pass

code_file, stl_out, step_out = sys.argv[1], sys.argv[2], sys.argv[3]
code = open(code_file, "r", encoding="utf-8").read()

import build123d as _b
from build123d import Part, Solid, Compound, export_stl, export_step
try:
    from build123d import BuildPart
except Exception:
    BuildPart = ()

# 허용 import 만 통과시키는 guarded __import__
_ALLOWED = {"math", "build123d"}
_orig_import = _bi.__import__
_PROXY = None   # 아래에서 허용 전역(g)으로 채운 가짜 build123d 모듈
def _guarded_import(name, *a, **k):
    if name == "math":
        return math
    if name == "build123d" and _PROXY is not None:
        return _PROXY          # from build123d import os / import build123d as b; b.os  모두 불가
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
    if isinstance(_v, _types.ModuleType):      # build123d 가 끌어온 모듈(os/sys/ctypes/requests…)은 전부 제외
        continue
    _m = getattr(_v, "__module__", "") or ""
    if not (_m.startswith("build123d") or _m == "math" or _m == "builtins"):
        continue                                # OCP 클래스·외부 라이브러리 객체는 주입하지 않음
    g[_n] = _v
_PROXY = _types.ModuleType("build123d")
for _k, _v in g.items():
    if _k not in ("__builtins__",):
        setattr(_PROXY, _k, _v)
_PROXY.__all__ = [k for k in g if k != "__builtins__"]
_sb["__import__"] = _guarded_import

def done(obj):
    print(json.dumps(obj))
    sys.exit(0)

try:
    exec(compile(code, "<generated>", "exec"), g)
except Exception as e:
    done({"ok": False, "error": type(e).__name__ + ": " + str(e)[:400]})

part = g.get("part")
if part is None:
    done({"ok": False, "error": "코드가 최종 솔리드를 `part` 변수에 넣지 않았습니다."})

# BuildPart 등 빌더 객체면 .part 로 언랩
if BuildPart and isinstance(part, BuildPart):
    part = part.part
elif hasattr(part, "part") and not hasattr(part, "solids"):
    part = part.part

# Part 로 정규화
try:
    if not isinstance(part, (Part, Solid, Compound)):
        # Sketch·Wire 등은 3D 솔리드가 아님
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

# 겹치기만 하고 융합되지 않은 솔리드(≤10개일 때만 검사; 40+ 배열 Compound 는 의도된 겹침)
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
            if float(s_.bounding_box().min.Z) - zmin_all > 0.5:      # 바닥(가장 낮은 조각)보다 떠 있음
                # 떠 있어도 다른 솔리드와 닿아 있으면(거리 0) 조립된 것으로 봄
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
if floating:
    desc = ", ".join("solid%d (바닥 위 %.1fmm)" % o for o in floating[:4])
    done({"ok": False, "error": "공중에 뜬 분리 솔리드가 있습니다 (%s). 붙어야 할 부품(고리·손잡이·다리)이면 몸체에 1.5mm 이상 파묻어 "
          "+ 로 융합하세요. 별도 출력 부품이면 바닥(z=0)에 내려놓으세요." % desc})
if overlaps:
    desc = ", ".join("solid%d∩solid%d=%.0fmm³" % o for o in overlaps[:4])
    done({"ok": False, "error": "솔리드 %d개가 서로 겹치기만 하고 융합되지 않았습니다 (%s). "
          "같은 부품에 속하는 형상은 body = body + feature 로 반드시 + 융합해 ONE solid 로 만드세요(1.5mm 이상 파묻기). "
          "정말 분리 부품(뚜껑 등)이면 서로 겹치지 않게 떨어뜨리세요." % (nsolids, desc)})

# 내보내기
try:
    export_stl(part, stl_out, tolerance=0.01, angular_tolerance=0.1)
    export_step(part, step_out)
except Exception as e:
    done({"ok": False, "error": "내보내기 실패: " + type(e).__name__ + ": " + str(e)[:300]})

# 메시 기준 watertight(구 극점 퇴화면은 정리 후 판정)
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
    done({"ok": False, "error": "내보낸 메시가 닫혀 있지 않습니다(non-watertight, 조각 %s개). "
          "면이 서로 스치거나(0두께) 붙지 않은 형상이 있습니다. 겹치는 부위를 1.5mm 이상 파묻어 융합하고, "
          "접하기만 하는(touching) 배치를 피하세요." % bodies})

done({"ok": True, "nsolids": nsolids, "is_valid": is_valid, "watertight": watertight, "bodies": bodies,
      "volume": vol, "bbox": [round(dx,2), round(dy,2), round(dz,2)]})
'''


MAX_RSS_MB = 3072   # macOS 는 RLIMIT_AS/DATA 가 안 먹혀 부모가 RSS 를 감시해 죽인다


def _rss_mb(pid: int) -> float:
    """자식 프로세스 상주 메모리(MB). ps 로 읽어 플랫폼 의존 없이."""
    try:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=2).stdout
        return int(out.strip() or 0) / 1024.0
    except Exception:
        return 0.0


def _run_watched(cmd: list[str], timeout: float, max_rss_mb: int):
    """subprocess.run 대용 — 시간 제한 + 메모리(RSS) 제한을 부모 쪽에서 강제한다."""
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
            reason = f"실행 시간 초과({timeout:.0f}초) — 형상이 너무 복잡하거나 무한 연산입니다. 더 단순하게."
        elif _rss_mb(proc.pid) > max_rss_mb:
            reason = f"메모리 초과({max_rss_mb} MB) — 형상/배열이 너무 큽니다. 더 단순하게."
        if reason:
            proc.kill()
            try: proc.communicate(timeout=5)
            except Exception: pass
            raise SandboxError(reason)

    class _R:  # subprocess.CompletedProcess 와 같은 모양만
        pass
    r = _R(); r.stdout, r.stderr, r.returncode = out, err, proc.returncode
    return r


def execute_to_files(code: str, stl_out: str | Path, step_out: str | Path,
                     timeout: float = 45.0) -> dict:
    """코드를 격리 실행해 STL/STEP 파일을 쓴다. 측정 정보 dict 반환, 실패면 SandboxError."""
    validate(code)   # 1차 정적 검증(하네스에서도 import는 다시 막힘)
    with tempfile.TemporaryDirectory() as td:
        cf = Path(td) / "gen_code.py"
        hf = Path(td) / "harness.py"
        cf.write_text(code, encoding="utf-8")
        hf.write_text(_HARNESS, encoding="utf-8")
        proc = _run_watched([sys.executable, "-I", str(hf), str(cf), str(stl_out), str(step_out)],
                            timeout=timeout, max_rss_mb=MAX_RSS_MB)
        so = proc.stdout or ""
        if len(so) > 2_000_000:                 # 2MB 넘는 출력은 꼬리만 본다(결과 JSON 은 마지막 줄)
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
