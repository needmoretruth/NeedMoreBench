"""An answer cut off by the token limit keeps the fields it finished (a speech, an answer under 심문), and the
retry reason for an impossible choice reads as Korean with the right particle."""
from __future__ import annotations

from nmb.engine.parse import clean_speech, first_json_object
from nmb.engine.turn import TurnRequest
from nmb.harness import problem_with


def test_a_long_line_is_cut_at_a_sentence_or_a_word_never_mid_word():
    en = "DeepSeek waited until Night 2 to find MiniMax. " * 8 + "I need to cast doubt on DeepSeek now"
    out = clean_speech(en, 400)
    assert len(out) <= 400 and out.endswith("MiniMax.…")
    words = "word " * 120
    assert clean_speech(words, 400).endswith("word…") and len(clean_speech(words, 400)) <= 400
    ko = "딥시크가 둘째 밤까지 기다렸다. " * 30
    assert clean_speech(ko, 400).endswith("기다렸다.…")
    assert clean_speech("짧은 말", 400) == "짧은 말"


def test_a_cut_answer_keeps_its_finished_fields() -> None:
    cut = '{"thought": "의심된다", "say": "어젯밤 {경찰}이 누구였는지 말해 보세요.", "ledger": [{"name": "가", "susp'
    assert first_json_object(cut) == {"thought": "의심된다", "say": "어젯밤 {경찰}이 누구였는지 말해 보세요."}
    assert first_json_object('```json\n{"answer": "저는 시민입니다."') == {"answer": "저는 시민입니다."}
    assert first_json_object('{"answer": "저는 시민입니') is None  # a field cut in the middle is not kept
    assert first_json_object('{"say": "a", "vote": ') == {"say": "a"}
    assert first_json_object("생각 중입니다") is None
    assert first_json_object('{"say": "다 쓴 답"}') == {"say": "다 쓴 답"}


def test_the_retry_reason_uses_the_particle_formatter() -> None:
    req = TurnRequest("vote", "투표", field="vote", options=["가람", "나래"])
    assert str(problem_with({"vote": "다솜"}, req).render("ko")) == "vote 값 「다솜」은 고를 수 있는 것이 아니다"
    assert str(problem_with({"vote": "하루"}, req).render("ko")) == "vote 값 「하루」는 고를 수 있는 것이 아니다"
    assert str(problem_with({"vote": "Kim"}, req).render("en")) == "\"Kim\" is not a choice for vote"
