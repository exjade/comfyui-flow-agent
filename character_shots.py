"""Stable character-dataset shot definitions shared by the ComfyUI nodes."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .flow_agent_client import FlowAgentError


CHARACTER_RULES = (
    "one character only, plain solid background, simple identical studio lighting, "
    "high quality face consistency"
)


@dataclass(frozen=True)
class CharacterShot:
    shot_id: str
    group: str
    prompt_fragment: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


FACE_ANGLES = (
    CharacterShot("face_front", "Face Angles", "close-up portrait, front view, neutral expression, looking at camera"),
    CharacterShot("face_three_quarter_left", "Face Angles", "close-up portrait, 3/4 view facing left, soft smile"),
    CharacterShot("face_three_quarter_right", "Face Angles", "close-up portrait, 3/4 view facing right, soft smile"),
    CharacterShot("face_left_profile", "Face Angles", "close-up portrait, left side profile"),
    CharacterShot("face_right_profile", "Face Angles", "close-up portrait, right side profile"),
    CharacterShot("face_looking_up", "Face Angles", "close-up portrait, looking slightly up, curious expression"),
    CharacterShot("face_looking_down", "Face Angles", "close-up portrait, looking slightly down, gentle smile"),
    CharacterShot("face_head_tilt", "Face Angles", "close-up portrait, head tilted, playful expression"),
)

EXPRESSIONS = (
    CharacterShot("expression_laugh", "Expressions", "close-up, big open-mouth laugh, eyes squinted with joy"),
    CharacterShot("expression_surprised", "Expressions", "close-up, surprised expression, wide eyes, mouth open in 'wow'"),
    CharacterShot("expression_singing", "Expressions", "close-up, singing expression, mouth open mid-song"),
    CharacterShot("expression_thinking", "Expressions", "close-up, thinking expression, finger on chin"),
    CharacterShot("expression_excited", "Expressions", "close-up, excited grin, eyebrows raised"),
    CharacterShot("expression_sleepy", "Expressions", "close-up, sleepy expression, rubbing one eye"),
)

BODY_SHOTS = (
    CharacterShot("body_front", "Body Shots", "full body, standing front view, arms at sides, neutral pose"),
    CharacterShot("body_back", "Body Shots", "full body, standing back view"),
    CharacterShot("body_waving", "Body Shots", "full body, waving hello with right hand, big smile"),
    CharacterShot("body_jumping", "Body Shots", "full body, jumping mid-air, arms up, excited"),
    CharacterShot("body_sitting", "Body Shots", "full body, sitting cross-legged, smiling at camera"),
    CharacterShot("body_walking", "Body Shots", "full body, walking pose, side view"),
    CharacterShot("body_pointing", "Body Shots", "full body, pointing forward with excited expression"),
    CharacterShot("body_dancing", "Body Shots", "full body, dancing pose, arms out, laughing"),
)

ALL_CHARACTER_SHOTS = FACE_ANGLES + EXPRESSIONS + BODY_SHOTS
CHARACTER_PRESETS = {
    "all 22": ALL_CHARACTER_SHOTS,
    "face angles 8": FACE_ANGLES,
    "expressions 6": EXPRESSIONS,
    "body shots 8": BODY_SHOTS,
}
CHARACTER_PRESET_NAMES = tuple(CHARACTER_PRESETS) + ("custom",)


def slugify(value: str, fallback: str = "shot") -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return (slug or fallback)[:64]


def build_character_prompt(prompt_fragment: str, subject_description: str) -> str:
    subject = subject_description.strip()
    if not subject:
        raise FlowAgentError("Subject description cannot be empty.")
    return f"{prompt_fragment.strip()}. {subject}. {CHARACTER_RULES}"


def resolve_character_shots(
    preset: str,
    custom_shots: str,
    shot_count: int,
) -> list[CharacterShot]:
    if shot_count < 1 or shot_count > 102:
        raise FlowAgentError("shot_count must be between 1 and 102.")

    if preset == "custom":
        lines = [line.strip(" \t-\r") for line in custom_shots.splitlines()]
        lines = [line for line in lines if line and not line.startswith("#")]
        if not lines:
            raise FlowAgentError(
                "Custom shot preset requires one prompt fragment per line in custom_shots."
            )
        shots = [
            CharacterShot(
                f"custom_{index:03d}_{slugify(line)}",
                "Custom",
                line,
            )
            for index, line in enumerate(lines, start=1)
        ]
    else:
        try:
            shots = list(CHARACTER_PRESETS[preset])
        except KeyError as exc:
            raise FlowAgentError(f"Unsupported character shot preset {preset!r}.") from exc

    return shots[:shot_count]
