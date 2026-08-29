"""ComfyUI registration for Flow Agent image generation."""

from .nodes import FlowNanoBanana


NODE_CLASS_MAPPINGS = {
    "FlowNanoBanana": FlowNanoBanana,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FlowNanoBanana": "Flow / Nano Banana",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
