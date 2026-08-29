"""ComfyUI node implementation for Flow Agent / Nano Banana."""

from __future__ import annotations

import json
import time

from .flow_agent_client import FlowAgentClient, FlowAgentError
from .image_utils import (
    image_bytes_to_tensor,
    stack_image_tensors,
    tensor_batch_to_png_data_uris,
)


MODEL_IDS = ("gem_pix_2", "narwhal", "harbor_seal")

# Flow Agent's image endpoint receives `size`, then map_size_to_aspect() maps
# the numeric ratio to one of these five internal keys.
ASPECT_TO_SIZE = {
    "square (1:1)": "1024x1024",
    "landscape (16:9)": "1792x1024",
    "portrait (9:16)": "1024x1792",
    "landscape (4:3)": "1365x1024",
    "portrait (3:4)": "1024x1365",
}


class FlowNanoBanana:
    """Generate a ComfyUI IMAGE batch through a remote Flow Agent tunnel."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "dynamicPrompts": True,
                    },
                ),
                "model": (MODEL_IDS, {"default": "gem_pix_2"}),
                "aspect_ratio": (
                    tuple(ASPECT_TO_SIZE),
                    {"default": "square (1:1)"},
                ),
                "count": (
                    "INT",
                    {"default": 1, "min": 1, "max": 20, "step": 1},
                ),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 4294967295,
                        "step": 1,
                    },
                ),
                "timeout_seconds": (
                    "INT",
                    {"default": 600, "min": 30, "max": 3600, "step": 30},
                ),
            },
            "optional": {
                "reference_image": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("images", "media_ids_json", "source_urls_json")
    OUTPUT_TOOLTIPS = (
        "Generated images as one ComfyUI batch.",
        "JSON array of reusable Flow media IDs.",
        "JSON array of the source URLs returned by Flow Agent.",
    )
    FUNCTION = "generate"
    CATEGORY = "Flow Agent"
    DESCRIPTION = (
        "Generates Nano Banana images through Flow Agent running on your PC and "
        "exposed to this ComfyUI instance through ngrok."
    )

    @classmethod
    def IS_CHANGED(cls, **_kwargs):
        # A generation node is intentionally not cached between queue runs.
        return float("nan")

    def generate(
        self,
        prompt: str,
        model: str,
        aspect_ratio: str,
        count: int,
        seed: int,
        timeout_seconds: int,
        reference_image=None,
    ):
        cleaned_prompt = prompt.strip()
        if not cleaned_prompt:
            raise FlowAgentError("Prompt cannot be empty.")
        if model not in MODEL_IDS:
            raise FlowAgentError(f"Unsupported model {model!r}.")
        if aspect_ratio not in ASPECT_TO_SIZE:
            raise FlowAgentError(f"Unsupported aspect ratio {aspect_ratio!r}.")

        client = FlowAgentClient.from_env()
        started = time.monotonic()
        client.assert_ready(timeout_seconds=min(15.0, float(timeout_seconds)))

        media_ids: list[str] = []
        if reference_image is not None:
            data_uris = tensor_batch_to_png_data_uris(reference_image, max_images=10)
            for index, data_uri in enumerate(data_uris, start=1):
                remaining = timeout_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    raise FlowAgentError(
                        f"Timeout expired while uploading reference image {index}."
                    )
                media_ids.append(
                    client.upload_image(data_uri, timeout_seconds=remaining)
                )

        remaining = timeout_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise FlowAgentError("Timeout expired before image generation started.")
        items = client.generate_images(
            prompt=cleaned_prompt,
            model=model,
            size=ASPECT_TO_SIZE[aspect_ratio],
            count=count,
            seed=seed,
            ref_media_ids=media_ids,
            timeout_seconds=remaining,
        )

        tensors = []
        generated_media_ids: list[str | None] = []
        source_urls: list[str | None] = []
        for item in items:
            remaining = timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                raise FlowAgentError("Timeout expired while downloading generated images.")
            image_bytes = client.download_generated_image(
                item, timeout_seconds=min(120.0, remaining)
            )
            tensors.append(image_bytes_to_tensor(image_bytes))
            generated_media_ids.append(item.get("media_id"))
            source_urls.append(item.get("url"))

        return (
            stack_image_tensors(tensors),
            json.dumps(generated_media_ids, ensure_ascii=False),
            json.dumps(source_urls, ensure_ascii=False),
        )
