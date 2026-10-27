"""외부 3D 모델 라이브러리 검색(리트리벌).

RealCAD 커널은 파라메트릭 기본형(plate/container/gear/...)만 생성한다.
마우스·신발·피규어 같은 유기적 자유곡면은 못 만들므로, 플래너가 kind="retrieve"로
넘기면 여기서 외부 3D 모델 라이브러리(Thingiverse 등)를 검색해 후보 모델을 돌려준다.

설계 원칙:
- 네트워크 실패/토큰 없음은 **예외를 던지지 않고** 구조화된 에러 dict로 돌려준다
  (웹 엔드포인트가 500 대신 안내를 내보낼 수 있게).
- 표준 라이브러리 + requests(설치돼 있으면)만 쓴다. 없으면 urllib로 폴백.
- 모든 네트워크 호출은 타임아웃 10초.

반환(성공): [{"name","source","url","thumbnail","download_url","license"}, ...]
반환(실패/안내): [{"error": "...", "how": "..."}]  (리스트 안에 단일 에러 dict)

TODO(후속 범위): 선택한 후보의 download_url에서 STL/3MF 내려받기 → trimesh로 watertight
검증(is_watertight, 구멍 메우기) → 빌드볼륨 초과 시 printing.mesh_split로 분할·정렬핀 연결.
이번 범위는 "검색 후보 반환"까지.
"""
from __future__ import annotations
import json
import os
import urllib.parse
import urllib.request
import urllib.error

TIMEOUT = 10  # seconds

try:                       # requests가 있으면 쓰고, 없으면 urllib 폴백
    import requests        # type: ignore
    _HAS_REQUESTS = True
except ImportError:        # pragma: no cover
    requests = None        # type: ignore
    _HAS_REQUESTS = False


def _http_get_json(url: str, headers: dict) -> dict:
    """GET → JSON. requests 있으면 requests, 없으면 urllib. 타임아웃 10초."""
    if _HAS_REQUESTS:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def _err(error: str, how: str) -> list[dict]:
    """구조화된 에러를 리스트 단일 항목으로 — 호출부가 항상 list를 받도록."""
    return [{"error": error, "how": how}]


# ───────────────────────── Thingiverse ─────────────────────────

def _search_thingiverse(query: str, limit: int) -> list[dict]:
    token = os.environ.get("THINGIVERSE_TOKEN", "").strip()
    if not token:
        return _err(
            "THINGIVERSE_TOKEN not set",
            "https://www.thingiverse.com/apps/create 에서 무료 앱 토큰(App Token) 발급 후 "
            "환경변수 THINGIVERSE_TOKEN 에 설정하세요.",
        )
    # GET https://api.thingiverse.com/search/{query}?type=things  (Bearer 토큰)
    url = (f"https://api.thingiverse.com/search/{urllib.parse.quote(query)}"
           f"?type=things&per_page={int(limit)}")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        data = _http_get_json(url, headers)
    except urllib.error.HTTPError as e:            # 401/429 등
        body = ""
        try:
            body = e.read().decode()[:200]
        except Exception:
            pass
        return _err(f"Thingiverse API {e.code}", f"응답: {body or '(없음)'}")
    except Exception as e:                          # 타임아웃·네트워크 등
        return _err(f"Thingiverse request failed: {type(e).__name__}", str(e)[:200])

    # 응답 형태: {"hits": N, "total": M, ...} 또는 바로 리스트일 수 있어 둘 다 수용
    hits = data.get("hits", data) if isinstance(data, dict) else data
    if not isinstance(hits, list):
        return _err("Thingiverse unexpected response", f"키: {list(data)[:8] if isinstance(data, dict) else type(data)}")

    out: list[dict] = []
    for t in hits[:limit]:
        if not isinstance(t, dict):
            continue
        out.append({
            "name": t.get("name", ""),
            "source": "thingiverse",
            "url": t.get("public_url") or t.get("url", ""),
            "thumbnail": t.get("thumbnail") or t.get("preview_image", ""),
            # Thing 단위 다운로드(STL 직링크는 파일 단위 조회가 더 필요 → TODO).
            "download_url": (f"https://www.thingiverse.com/thing:{t.get('id')}/zip"
                             if t.get("id") else ""),
            "license": t.get("license", ""),
        })
    return out


# ───────────────────────── Printables (스텁) ─────────────────────────

def _search_printables(query: str, limit: int) -> list[dict]:
    """Printables GraphQL(api.printables.com/graphql) 클라이언트 — 스텁.

    Printables는 공개 토큰 발급/스키마가 불안정하고(비공식 GraphQL), 인증·쿼리 스키마가
    확정되지 않아 실제 호출을 붙이지 않았다. 스키마가 확정되면 아래 쿼리를 채운다:

        POST https://api.printables.com/graphql
        {"query": "query($q:String!){ prints(query:$q){ items{ id name ... } } }",
         "variables": {"q": query}}

    지금은 NotImplemented 수준의 구조화된 안내를 돌려준다(예외 금지).
    """
    return _err(
        "printables source not implemented",
        "Printables GraphQL(api.printables.com/graphql)은 공식 토큰/스키마가 불확실해 "
        "스텁 상태입니다. source='thingiverse'를 쓰거나 스키마 확정 후 구현하세요.",
    )


# ───────────────────────── 텍스트→3D 생성 (Meshy) ─────────────────────────
# 검색(retrieval)이 "기존 모델 찾기"라면, 생성(generative)은 "자유곡면을 새로 만들기"다.
# 마우스·신발·피규어처럼 파라메트릭으로 불가한 형상을 텍스트→3D 생성 AI로 메시를 만든다.
# Meshy(api.meshy.ai) text-to-3d v2 사용. 무료 API 키(MESHY_API_KEY) 필요.
# 생성은 수십 초~수 분 걸리므로 submit→task_id 반환, 상태는 generation_status로 폴링.

_MESHY_BASE = "https://api.meshy.ai/openapi/v2/text-to-3d"


def _http_post_json(url: str, headers: dict, body: dict) -> dict:
    if _HAS_REQUESTS:
        resp = requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def generate_3d(prompt: str, art_style: str = "realistic") -> dict:
    """텍스트→3D 생성 작업을 제출한다(Meshy). 바로 메시가 나오지 않고 task_id를 돌려준다.

    Returns:
        제출 성공: {"task_id","status":"submitted","source":"meshy","how":"generation_status(task_id)로 폴링"}
        키 없음/실패: {"error","how"}  (예외 던지지 않음)
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return {"error": "empty prompt", "how": "생성할 형상 설명을 넘기세요(영문 권장)."}
    key = os.environ.get("MESHY_API_KEY", "").strip()
    if not key:
        return {"error": "MESHY_API_KEY not set",
                "how": "https://www.meshy.ai 에서 무료 API 키 발급 후 환경변수 MESHY_API_KEY 에 설정하세요."}
    headers = {"Authorization": f"Bearer {key}"}
    body = {"mode": "preview", "prompt": prompt, "art_style": art_style, "should_remesh": True}
    try:
        data = _http_post_json(_MESHY_BASE, headers, body)
    except urllib.error.HTTPError as e:
        body_txt = ""
        try:
            body_txt = e.read().decode()[:200]
        except Exception:
            pass
        return {"error": f"Meshy API {e.code}", "how": f"응답: {body_txt or '(없음)'}"}
    except Exception as e:
        return {"error": f"Meshy request failed: {type(e).__name__}", "how": str(e)[:200]}
    task_id = data.get("result") or data.get("id") or ""
    return {"task_id": task_id, "status": "submitted", "source": "meshy",
            "how": "generation_status(task_id)로 완료를 확인하세요(수십 초~수 분)."}


def generation_status(task_id: str) -> dict:
    """Meshy 생성 작업 상태·결과(메시 URL)를 조회한다."""
    task_id = (task_id or "").strip()
    if not task_id:
        return {"error": "empty task_id", "how": "generate_3d가 돌려준 task_id를 넘기세요."}
    key = os.environ.get("MESHY_API_KEY", "").strip()
    if not key:
        return {"error": "MESHY_API_KEY not set",
                "how": "https://www.meshy.ai 에서 무료 API 키 발급 후 MESHY_API_KEY 설정."}
    url = f"{_MESHY_BASE}/{urllib.parse.quote(task_id)}"
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    try:
        data = _http_get_json(url, headers)
    except urllib.error.HTTPError as e:
        return {"error": f"Meshy API {e.code}", "how": str(e)[:200]}
    except Exception as e:
        return {"error": f"Meshy request failed: {type(e).__name__}", "how": str(e)[:200]}
    return {
        "task_id": task_id, "status": data.get("status", ""),
        "progress": data.get("progress"),
        "model_urls": data.get("model_urls", {}),   # {glb, obj, fbx, usdz}
        "thumbnail": data.get("thumbnail_url", ""),
        # TODO: SUCCEEDED면 obj/glb 내려받기 → trimesh watertight 검증·구멍메우기 → 빌드볼륨 초과 시 분할.
    }


# ───────────────────────── 공개 진입점 ─────────────────────────

_SOURCES = {
    "thingiverse": _search_thingiverse,
    "printables": _search_printables,
}


def search_models(query: str, source: str = "thingiverse", limit: int = 5) -> list[dict]:
    """외부 3D 모델 라이브러리에서 query로 모델을 검색한다.

    Args:
        query: 검색어(영문 권장).
        source: "thingiverse"(기본) | "printables"(스텁).
        limit: 최대 결과 수.

    Returns:
        성공 시 [{name, source, url, thumbnail, download_url, license}, ...].
        토큰 없음/네트워크 실패/미구현이면 [{error, how}] (예외 던지지 않음).
    """
    query = (query or "").strip()
    if not query:
        return _err("empty query", "검색어(query)를 비우지 말고 영문 검색어를 넘기세요.")
    fn = _SOURCES.get(source)
    if fn is None:
        return _err(f"unknown source '{source}'", f"지원 source: {', '.join(_SOURCES)}")
    return fn(query, max(1, int(limit)))
