"""상용 제품 규격 조회(agent/product_spec): 표 조회, 확신도 상태, 모델 답 병합, codegen 블록, 질문 생성. 네트워크 없음."""
import re
import pytest
from realcad.agent import product_spec as ps


def test_table_lookup_mac_mini_official():
    c = ps.lookup("맥미니 M4를 노트북 거치대 팔에 거는 브래킷", use_meta=False)
    assert len(c.products) == 1
    p = c.products[0]
    assert (p.w, p.d, p.h, p.weight_g) == (127.0, 127.0, 50.0, 670)
    assert p.status == "확실(공식 규격)" and p.source.startswith("https://support.apple.com")
    assert any("바닥" in k for k in p.keep_clear)          # 환기면을 피하라는 메모가 있어야 한다


def test_table_lookup_english_and_multiple():
    c = ps.lookup("a holder for a raspberry pi 5 and two 18650 cells", use_meta=False)
    names = [p.name for p in c.products]
    assert any("Raspberry Pi 5" in n for n in names) and any("18650" in n for n in names)


def test_no_product_gives_empty_card():
    c = ps.lookup("연필꽂이 80 x 100", use_meta=False)
    assert c.products == [] and c.to_prompt() == "" and c.questions == []


def test_prompt_block_has_clearance_and_keep_clear():
    c = ps.lookup("맥미니 케이스", use_meta=False)
    t = c.to_prompt()
    assert t.startswith("SPEC") and "127 x 127 x 50" in t
    assert "CLEARANCE" in t and "KEEP CLEAR" in t


@pytest.mark.parametrize("conf,status", [(0.98, "확실(모델 기억)"), (0.9, "확실(모델 기억)"),
                                         (0.75, "추정"), (0.6, "추정"), (0.3, "모름")])
def test_confidence_thresholds(conf, status):
    data = {"products": [{"name": "Some Gadget X1", "w_mm": 100, "d_mm": 50, "h_mm": 20,
                          "weight_g": 200, "confidence": conf}], "questions": []}
    c = ps.merge([], data)
    assert c.products[0].status == status
    if status == "모름":
        assert c.products[0].w is None                      # 모르는 치수는 지우고
        assert c.questions and "Some Gadget X1" in c.questions[0]["question"]   # 질문으로 돌린다


def test_merge_prefers_table_over_model(monkeypatch):
    """표에 있는 제품은 모델이 다른 숫자를 말해도 표 값이 남고, 상대편 질문은 최대 3개."""
    fake = {"products": [{"name": "Apple Mac mini M4 2024", "w_mm": 130, "d_mm": 130, "h_mm": 55,
                          "weight_g": 700, "confidence": 0.95}],
            "counterpart": "노트북 거치대 팔",
            "questions": [{"key": "arm_width", "question": "팔 너비?", "suggestion": "50mm"},
                          {"key": "arm_thickness", "question": "팔 두께?", "suggestion": "8mm"},
                          {"key": "dir", "question": "포트 방향?", "suggestion": "위"},
                          {"key": "extra", "question": "색?", "suggestion": ""}]}
    monkeypatch.setattr(ps, "extract_with_meta", lambda prompt: (fake, {"prompt_tokens": 1}))
    c = ps.lookup("맥미니 M4 거치대 팔 브래킷")
    assert len(c.products) == 1 and c.products[0].w == 127.0 and c.products[0].status == "확실(공식 규격)"
    assert c.counterpart == "노트북 거치대 팔"
    assert [q["key"] for q in c.questions] == ["arm_width", "arm_thickness", "dir"]


def test_meta_failure_falls_back_to_table(monkeypatch):
    def boom(prompt):
        raise RuntimeError("Meta API 500")
    monkeypatch.setattr(ps, "extract_with_meta", boom)
    c = ps.lookup("맥미니 브래킷")
    assert c.products and c.products[0].w == 127.0 and "error" in c.usage


def test_answers_text_block():
    assert ps.answers_text(None) == "" and ps.answers_text({"a": " "}) == ""
    t = ps.answers_text({"arm_width": "60 mm"})
    assert t.startswith("MEASURED") and "arm_width: 60 mm" in t


def test_no_middle_dot_or_dash_in_korean_strings():
    import inspect
    src = inspect.getsource(ps)
    bad = [ln for ln in src.splitlines() if re.search(r"[·–]", ln) or ("—" in ln and "SPEC —" not in ln)]
    assert bad == [], bad


def test_model_duplicate_of_table_is_dropped():
    """모델이 표 제품을 다른 이름(한글)으로 또 말해도 한 줄만 남는다(이름 regex 또는 치수 2% 일치)."""
    data = {"products": [{"name": "신용카드 (ISO/IEC 7810 ID-1)", "w_mm": 85.6, "d_mm": 53.98, "h_mm": 0.76,
                          "weight_g": 5, "confidence": 1.0},
                         {"name": "Mac mini 2024", "w_mm": 127, "d_mm": 127, "h_mm": 50, "confidence": 0.9}]}
    hits = ps.lookup_table("신용카드 지갑과 맥미니 받침")
    c = ps.merge(hits, data)
    assert [p.status for p in c.products] == ["확실(공식 규격)", "확실(공식 규격)"] and len(c.products) == 2
