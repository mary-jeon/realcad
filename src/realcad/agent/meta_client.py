"""Meta Model API client: /chat/completions style endpoint.

Base URL https://api.meta.ai/v1, model muse-spark-1.3, Bearer auth.
The key is read from META_API_KEY in realcad/.env (never commit it).
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


# Log token usage per call (the API does not expose the credit balance, so we count it ourselves).
# Price in USD per 1M tokens: (input, output, cached input).
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


def chat(messages: list[dict], model: str = MODEL,
         temperature: float = 0.0, max_tokens: int = 6000,
         json_mode: bool = False) -> tuple[str, dict]:
    """Messages -> (response text, usage). This is a reasoning model, so if content is None
    (finish_reason=length), retry once with double the token budget."""
    content, finish, usage = _call(messages, model, temperature, max_tokens, json_mode)
    if content is None and finish == "length":
        content, finish, usage = _call(messages, model, temperature, max_tokens * 2, json_mode)
    if content is None:
        raise RuntimeError(f"Meta 응답이 비었습니다(finish={finish}). 더 구체적으로 요청해 주세요.")
    return content, usage


IMAGE_MODEL = "muse-image-1.0"
IMAGE_USD = 0.01   # list price per generated image


def image(prompt: str, size: str = "1024x1024", model: str = IMAGE_MODEL) -> bytes:
    """Text -> one generated image (PNG bytes) from Meta Muse Image."""
    import base64
    import time
    body = {"model": model, "prompt": prompt, "n": 1, "size": size}
    req = urllib.request.Request(
        f"{BASE_URL}/images/generations",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {_load_key()}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Meta API {e.code}: {e.read().decode()[:400]}") from e
    try:
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with USAGE_LOG.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": model, "images": 1, "usd": IMAGE_USD}) + "\n")
    except Exception:
        pass
    return base64.b64decode(resp["data"][0]["b64_json"])


VOICE_MODEL = "muse-voice-transcribe-1.0"
# Words people say to a CAD tool. They bias recognition; they do not force a spelling.
VOICE_KEYWORDS = {
    "ko": ["쿼터 트웬티", "볼트", "너트", "밀리", "구멍", "지름", "두께", "간격", "M3", "M4", "M5", "M6", "M8"],
    "en": ["quarter-twenty", "bolt", "nut", "millimeters", "diameter", "thickness", "spacing", "M3", "M4", "M5", "M6", "M8"],
}


def transcribe(wav: bytes, lang: str = "ko") -> str:
    """Mono 16-bit PCM WAV (16 or 24 kHz) -> text, with Meta Muse Voice Transcribe."""
    import time
    import uuid
    lg = "en" if str(lang).lower().startswith("en") else "ko"
    settings = {"mode": "PUSH_TO_TALK", "model": VOICE_MODEL, "audioEncoding": "WAV",
                "languageBias": ["English" if lg == "en" else "Korean"], "keywords": VOICE_KEYWORDS[lg]}
    bnd = uuid.uuid4().hex
    body = (f'--{bnd}\r\nContent-Disposition: form-data; name="request"\r\nContent-Type: application/json\r\n\r\n'
            f'{json.dumps(settings, ensure_ascii=False)}\r\n'
            f'--{bnd}\r\nContent-Disposition: form-data; name="audio"; filename="a.wav"\r\nContent-Type: audio/wav\r\n\r\n'
            ).encode("utf-8") + wav + f"\r\n--{bnd}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/asr/transcribe?sessionId={uuid.uuid4().hex}", data=body, method="POST",
        headers={"Authorization": f"Bearer {_load_key()}", "Content-Type": f"multipart/form-data; boundary={bnd}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Meta API {e.code}: {e.read().decode()[:400]}") from e
    try:
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with USAGE_LOG.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": VOICE_MODEL,
                                 "audio_ms": resp.get("audioDurationMs")}) + "\n")
    except Exception:
        pass
    return str(resp.get("transcript") or "").strip()
