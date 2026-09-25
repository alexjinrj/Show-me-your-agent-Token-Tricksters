from agent_runtime.service import SYSTEM_RULES


def test_runtime_requests_concise_final_answers() -> None:
    assert "Lead with the direct conclusion" in SYSTEM_RULES
    assert "no more than four short bullets" in SYSTEM_RULES
    assert "roughly 120 words" in SYSTEM_RULES
    assert "UI exposes full tool evidence separately" in SYSTEM_RULES
