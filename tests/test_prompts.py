import pytest

from app.prompts import SUPPORTED_MODES, build_user_prompt


@pytest.mark.parametrize("mode", SUPPORTED_MODES)
def test_build_user_prompt_contains_selected_text(mode):
    prompt = build_user_prompt("Language models predict tokens.", mode)

    assert "Language models predict tokens." in prompt
    assert "Selected text:" in prompt
