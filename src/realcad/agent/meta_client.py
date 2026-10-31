"""Meta Model API 클라이언트 (Muse Spark). OpenAI 호환 /chat/completions.

Base URL https://api.meta.ai/v1, 모델 muse-spark-1.3, Bearer 인증.
키는 realcad/.env 의 META_API_KEY 에서 읽는다(절대 커밋 안 함).
"""
from __future__ import annotations
import json
import os
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = "https://api.meta.ai/v1"
MODEL = "muse-spark-1.3"

_ROOT = Path(__file__).resolve().parents[3]  # realcad/


def _load_key() -> str:
    k = os.environ.get("META_API_KEY")
    if k:
        return k.strip()
    envf = _ROOT / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            if line.startswith("META_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("META_API_KEY 없음 (.env 또는 환경변수)")


def _call(messages, model, temperature, max_tokens, json_mode):
    body = {"model": model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {_load_key()}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Meta API {e.code}: {e.read().decode()[:400]}") from e
    ch = resp["choices"][0]
    _log_usage(model, resp.get("usage", {}))
    return ch["message"].get("content"), ch.get("finish_reason"), resp.get("usage", {})


# 호출마다 토큰 사용량을 로그에 적는다(크레딧 잔액은 API 로 못 보니 우리가 센다).
# 단가: dev.meta.ai/docs/pricing-rate-limits (2026-10-31) muse-spark-1.3 입력 $1.25 / 출력 $4.25 / 캐시 입력 $0.15 per 1M
_PRICE = {"muse-spark-1.3": (1.25, 4.25, 0.15), "muse-spark-1.3-contributor": (0.10, 0.20, 0.002)}
USAGE_LOG = Path(os.environ.get("REALCAD_USAGE_LOG", Path.home() / "Library" / "Logs" / "realcad.meta_usage.jsonl"))


def _log_usage(model: str, usage: dict) -> None:
    try:
        import time
        pi, po, pc = _PRICE.get(model, _PRICE["muse-spark-1.3"])
        it = int(usage.get("prompt_tokens", 0) or 0); ot = int(usage.get("completion_tokens", 0) or 0)
        ct = int(((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)) or 0)
        cost = ((it - ct) * pi + ct * pc + ot * po) / 1e6
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with USAGE_LOG.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": model, "in": it, "out": ot, "cached": ct, "usd": round(cost, 5)}) + "\n")
    except Exception:
        pass


def usage_summary() -> dict:
    """누적 호출 수, 토큰, 추정 비용(USD). 로그가 시작된 시점부터만."""
    n = ti = to = 0; usd = 0.0
    try:
        for line in USAGE_LOG.read_text(encoding="utf-8").splitlines():
            d = json.loads(line); n += 1; ti += d.get("in", 0); to += d.get("out", 0); usd += d.get("usd", 0.0)
    except Exception:
        pass
    return {"calls": n, "in": ti, "out": to, "usd": round(usd, 3)}


def chat(messages: list[dict], model: str = MODEL,
         temperature: float = 0.0, max_tokens: int = 6000,
         json_mode: bool = False) -> tuple[str, dict]:
    """메시지 → (응답 텍스트, usage). Muse Spark는 reasoning 모델이라
    content=None(finish_reason=length)이면 토큰을 2배로 한 번 더 시도한다."""
    content, finish, usage = _call(messages, model, temperature, max_tokens, json_mode)
    if content is None and finish == "length":
        content, finish, usage = _call(messages, model, temperature, max_tokens * 2, json_mode)
    if content is None:
        raise RuntimeError(f"Meta 응답이 비었습니다(finish={finish}). 더 구체적으로 요청해 주세요.")
    return content, usage
