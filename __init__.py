"""ComfyUI registration for Flow Agent image and video generation."""

from .nodes import (
    FlowCharacterCreator,
    FlowGenerateCharacterShot,
    FlowNanoBanana,
    FlowOmniFlashVideo,
    FlowUploadMedia,
)
from .flow_character_library import FlowCharacterShotSelector
from .flow_video_library import FlowVideoLibrary


NODE_CLASS_MAPPINGS = {
    "FlowNanoBanana": FlowNanoBanana,
    "FlowCharacterCreator": FlowCharacterCreator,
    "FlowCharacterShotSelector": FlowCharacterShotSelector,
    "FlowGenerateCharacterShot": FlowGenerateCharacterShot,
    "FlowOmniFlashVideo": FlowOmniFlashVideo,
    "FlowUploadMedia": FlowUploadMedia,
    "FlowVideoLibrary": FlowVideoLibrary,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FlowNanoBanana": "Flow / Nano Banana",
    "FlowCharacterCreator": "Flow / Custom Character Creator",
    "FlowCharacterShotSelector": "Flow / 1. Choose Character Shot",
    "FlowGenerateCharacterShot": "Flow / 2. Regenerate Chosen Shot",
    "FlowOmniFlashVideo": "Flow / Omni Flash Video",
    "FlowUploadMedia": "Flow / Upload Media",
    "FlowVideoLibrary": "Flow / Video Library",
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
