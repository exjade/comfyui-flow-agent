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


NODE_CLASS_MAPPINGS = {
    "FlowNanoBanana": FlowNanoBanana,
    "FlowCharacterCreator": FlowCharacterCreator,
    "FlowCharacterShotSelector": FlowCharacterShotSelector,
    "FlowGenerateCharacterShot": FlowGenerateCharacterShot,
    "FlowOmniFlashVideo": FlowOmniFlashVideo,
    "FlowUploadMedia": FlowUploadMedia,
    "FlowVideoUpsample": FlowVideoUpsample,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FlowNanoBanana": "Flow / Nano Banana",
    "FlowCharacterCreator": "Flow / Custom Character Creator",
    "FlowCharacterShotSelector": "Flow / Select Character Shot",
    "FlowGenerateCharacterShot": "Flow / Generate Character Shot",
    "FlowOmniFlashVideo": "Flow / Omni Flash Video",
    "FlowUploadMedia": "Flow / Upload Media",
    "FlowVideoUpsample": "Flow / Upsample Video",
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
