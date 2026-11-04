"""Voice input goes to Meta Muse Voice Transcribe, and no other speech model is left in the project."""
import json
from pathlib import Path

from realcad.agent import meta_client as M

ROOT = Path(__file__).resolve().parents[1]


class _Resp:
    def __init__(self, d): self.d = d
    def read(self, *a): return json.dumps(self.d).encode()
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_transcribe_request(monkeypatch, tmp_path):
    seen = {}
    def fake(req, timeout=0):
        seen["url"], seen["body"], seen["auth"] = req.full_url, req.data, req.get_header("Authorization")
        return _Resp({"transcript": " 볼트 두 개 ", "audioDurationMs": 1000})
    monkeypatch.setenv("META_API_KEY", "test-key")
    monkeypatch.setattr(M, "USAGE_LOG", tmp_path / "u.jsonl")
    monkeypatch.setattr(M.urllib.request, "urlopen", fake)
    assert M.transcribe(b"RIFFdata", "ko-KR") == "볼트 두 개"
    assert "/asr/transcribe" in seen["url"] and seen["auth"] == "Bearer test-key"
    body = seen["body"].decode("utf-8", "ignore")
    assert 'name="request"' in body and 'name="audio"' in body and "muse-voice-transcribe-1.0" in body
    assert "Korean" in body and "RIFFdata" in body
    assert "English" in _body_for(monkeypatch, "en-US")


def _body_for(monkeypatch, lang):
    seen = {}
    def fake(req, timeout=0):
        seen["b"] = req.data
        return _Resp({"transcript": "ok"})
    monkeypatch.setattr(M.urllib.request, "urlopen", fake)
    M.transcribe(b"x", lang)
    return seen["b"].decode("utf-8", "ignore")


def test_no_other_speech_model_in_runtime():
    for f in list((ROOT / "src").rglob("*.py")) + [ROOT / "web" / "acad.html", ROOT / "pyproject.toml"]:
        assert "whisper" not in f.read_text(encoding="utf-8").lower(), f

