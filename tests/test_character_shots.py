from __future__ import annotations

import pytest

from comfyui_flow_agent_under_test.character_shots import (
    ALL_CHARACTER_SHOTS,
    build_character_prompt,
    resolve_character_shots,
)
from comfyui_flow_agent_under_test.flow_agent_client import FlowAgentError


def test_persona_preset_contains_the_verified_22_stable_shots():
    shots = resolve_character_shots("all 22", "", 22)

    assert len(ALL_CHARACTER_SHOTS) == 22
    assert len(shots) == 22
    assert len({shot.shot_id for shot in shots}) == 22
    assert shots[0].shot_id == "face_front"
    assert shots[-1].shot_id == "body_dancing"


def test_custom_shots_are_limited_and_receive_stable_ids():
    shots = resolve_character_shots(
        "custom",
        "# comment\nleft profile\nright profile\nfull body",
        2,
    )

    assert [shot.shot_id for shot in shots] == [
        "custom_001_left_profile",
        "custom_002_right_profile",
    ]


def test_character_prompt_contains_subject_and_consistency_rules():
    prompt = build_character_prompt("front portrait", "A blue-haired singer")

    assert prompt.startswith("front portrait. A blue-haired singer.")
    assert "one character only" in prompt
    assert "face consistency" in prompt

    with pytest.raises(FlowAgentError, match="Subject description"):
        build_character_prompt("front portrait", "  ")
