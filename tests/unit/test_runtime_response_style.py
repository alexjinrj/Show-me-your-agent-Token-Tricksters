from agent_runtime.service import SYSTEM_RULES


def test_runtime_requests_clear_adaptive_final_answers() -> None:
    assert "Lead with the direct conclusion" in SYSTEM_RULES
    assert "Match the depth and length to the" in SYSTEM_RULES
    assert "do not force a fixed" in SYSTEM_RULES
    assert "Synthesize tool results instead of dumping payloads" in SYSTEM_RULES
    assert "leaving full tool evidence in the UI disclosure" in SYSTEM_RULES
    assert "no more than four short bullets" not in SYSTEM_RULES
    assert "roughly 120 words" not in SYSTEM_RULES
