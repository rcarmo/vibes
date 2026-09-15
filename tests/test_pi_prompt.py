from vibes.pi_prompt import PI_PROMPT_PREFIX


def test_pi_prompt_advertises_safe_inline_svg_contract():
    assert "fenced ```svg code block" in PI_PROMPT_PREFIX
    assert "sanitizes it and displays it as an inert image" in PI_PROMPT_PREFIX
    assert "SVG files remain safe download attachments" in PI_PROMPT_PREFIX
