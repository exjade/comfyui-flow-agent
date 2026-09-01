"""ComfyUI registration for Flow Agent image and video generation."""

from .nodes import (
    FlowCharacterCreator,
    FlowCharacterShotSelector,
    FlowGenerateCharacterShot,
    FlowNanoBanana,
    FlowOmniFlashVideo,
    FlowUploadMedia,
    FlowVideoUpsample,
)
from .flow_video_library import FlowVideoLibrary


NODE_CLASS_MAPPINGS = {
    "FlowNanoBanana": FlowNanoBanana,
    "FlowCharacterCreator": FlowCharacterCreator,
    "FlowCharacterShotSelector": FlowCharacterShotSelector,
    "FlowGenerateCharacterShot": FlowGenerateCharacterShot,
    "FlowOmniFlashVideo": FlowOmniFlashVideo,
    "FlowUploadMedia": FlowUploadMedia,
    "FlowVideoUpsample": FlowVideoUpsample,
    "FlowVideoLibrary": FlowVideoLibrary,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FlowNanoBanana": "Flow / Nano Banana",
    "FlowCharacterCreator": "Flow / Custom Character Creator",
    "FlowCharacterShotSelector": "Flow / Select Character Shot",
    "FlowGenerateCharacterShot": "Flow / Generate Character Shot",
    "FlowOmniFlashVideo": "Flow / Omni Flash Video",
    "FlowUploadMedia": "Flow / Upload Media",
    # Keep the internal node key for existing workflows; only clarify its UI name.
    "FlowVideoUpsample": "Flow / Upscale Video",
    "FlowVideoLibrary": "Flow / Video Library",
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
