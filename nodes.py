"""ComfyUI nodes for Flow Agent image, video, upload, and upsample APIs."""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from .flow_agent_client import FlowAgentClient, FlowAgentError
from .image_utils import image_bytes_to_tensor, stack_image_tensors, tensor_batch_to_png_data_uris

MODEL_IDS = ("gem_pix_2", "narwhal", "harbor_seal")
ASPECT_TO_SIZE = {
    "square (1:1)": "1024x1024",
    "landscape (16:9)": "1792x1024",
    "portrait (9:16)": "1024x1792",
    "landscape (4:3)": "1365x1024",
    "portrait (3:4)": "1024x1365",
}
VIDEO_MODES = (
    "text to video",
    "start image to video",
    "first + last frame",
    "ingredients / reference images",
    "edit source video",
)
VIDEO_ASPECTS = ("landscape", "portrait")
VIDEO_DURATIONS = (4, 6, 8, 10)
VIDEO_RESOLUTIONS = ("720p", "1080p", "4k")
MAX_REFERENCE_IMAGES = 10


def _remaining(started: float, timeout_seconds: float, action: str) -> float:
    remaining = timeout_seconds - (time.monotonic() - started)
    if remaining <= 0:
        raise FlowAgentError(f"Timeout expired while {action}.")
    return remaining


def _upload_image_batch(client, image, *, started, timeout_seconds, max_images=10):
    if image is None:
        return []
    media_ids = []
    for index, data_uri in enumerate(
        tensor_batch_to_png_data_uris(image, max_images=max_images), start=1
    ):
        media_ids.append(
            client.upload_image(
                data_uri,
                timeout_seconds=_remaining(
                    started, timeout_seconds, f"uploading reference image {index}"
                ),
            )
        )
    return media_ids


def _upload_image_sources(client, sources, *, started, timeout_seconds, max_images=10):
    media_ids = []
    for source in sources:
        if source is None:
            continue
        remaining_slots = max_images - len(media_ids)
        if remaining_slots <= 0:
            raise FlowAgentError(f"Flow Agent accepts at most {max_images} reference images.")
        media_ids.extend(
            _upload_image_batch(
                client,
                source,
                started=started,
                timeout_seconds=timeout_seconds,
                max_images=remaining_slots,
            )
        )
    return media_ids


def _comfy_output_directory() -> str:
    try:
        import folder_paths

        root = folder_paths.get_output_directory()
    except (ImportError, AttributeError):
        root = os.path.abspath(os.path.join(os.getcwd(), "output"))
    path = os.path.join(root, "flow_agent")
    os.makedirs(path, exist_ok=True)
    return path


def _select_video_items(payload: dict[str, Any], *, resolution: str, count: int):
    data = [
        item
        for item in payload.get("data", [])
        if isinstance(item, dict) and item.get("url")
    ]
    exact = [item for item in data if item.get("resolution") == resolution]
    if resolution == "720p":
        exact.extend(
            item
            for item in data
            if item.get("resolution") in {None, ""} and item not in exact
        )
    selected = exact or data
    if not selected:
        raise FlowAgentError(
            "Flow Agent completed the video job but returned no downloadable video."
        )
    return selected[:count]


def _download_video_result(
    client,
    payload,
    *,
    requested_resolution,
    count,
    started,
    timeout_seconds,
):
    items = _select_video_items(payload, resolution=requested_resolution, count=count)
    output_dir = _comfy_output_directory()
    paths, previews = [], []
    for index, item in enumerate(items, start=1):
        filename = f"flow_{int(time.time())}_{uuid.uuid4().hex[:8]}_{index}.mp4"
        destination = os.path.join(output_dir, filename)
        client.download_media_to_file(
            item,
            destination,
            timeout_seconds=min(
                600.0,
                _remaining(started, timeout_seconds, f"downloading video {index}"),
            ),
        )
        paths.append(destination)
        previews.append(
            {
                "filename": filename,
                "subfolder": "flow_agent",
                "type": "output",
                "format": "video/mp4",
                "fullpath": destination,
            }
        )
    result = (
        (True, paths),
        json.dumps(paths, ensure_ascii=False),
        json.dumps([item.get("media_id") for item in items], ensure_ascii=False),
        json.dumps([item.get("url") for item in items], ensure_ascii=False),
        json.dumps(payload, ensure_ascii=False),
    )
    return {"ui": {"gifs": previews}, "result": result}


class FlowNanoBanana:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": "", "dynamicPrompts": True}),
                "model": (MODEL_IDS, {"default": "gem_pix_2"}),
                "aspect_ratio": (tuple(ASPECT_TO_SIZE), {"default": "square (1:1)"}),
                "count": ("INT", {"default": 1, "min": 1, "max": 20, "step": 1}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 4294967295, "step": 1}),
                "timeout_seconds": ("INT", {"default": 600, "min": 30, "max": 3600, "step": 30}),
            },
            "optional": {
                "reference_image": ("IMAGE",),
                **{f"reference_image_{index}": ("IMAGE",) for index in range(2, 11)},
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("images", "media_ids_json", "source_urls_json")
    FUNCTION = "generate"
    CATEGORY = "Flow Agent"
    DESCRIPTION = "Nano Banana image generation with up to 10 ingredient/reference images."

    @classmethod
    def IS_CHANGED(cls, **_kwargs):
        return float("nan")

    def generate(
        self,
        prompt,
        model,
        aspect_ratio,
        count,
        seed,
        timeout_seconds,
        reference_image=None,
        **kwargs,
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
        reference_ids = _upload_image_sources(
            client,
            [reference_image]
            + [kwargs.get(f"reference_image_{index}") for index in range(2, 11)],
            started=started,
            timeout_seconds=timeout_seconds,
        )
        items = client.generate_images(
            prompt=cleaned_prompt,
            model=model,
            size=ASPECT_TO_SIZE[aspect_ratio],
            count=count,
            seed=seed,
            ref_media_ids=reference_ids,
            timeout_seconds=_remaining(started, timeout_seconds, "starting image generation"),
        )
        tensors, generated_media_ids, source_urls = [], [], []
        for item in items:
            image_bytes = client.download_generated_image(
                item,
                timeout_seconds=min(
                    120.0,
                    _remaining(started, timeout_seconds, "downloading generated images"),
                ),
            )
            tensors.append(image_bytes_to_tensor(image_bytes))
            generated_media_ids.append(item.get("media_id"))
            source_urls.append(item.get("url"))
        return (
            stack_image_tensors(tensors),
            json.dumps(generated_media_ids, ensure_ascii=False),
            json.dumps(source_urls, ensure_ascii=False),
        )


class FlowOmniFlashVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": "", "dynamicPrompts": True}),
                "mode": (VIDEO_MODES, {"default": "text to video"}),
                "aspect_ratio": (VIDEO_ASPECTS, {"default": "landscape"}),
                "duration": (VIDEO_DURATIONS, {"default": 8}),
                "count": ("INT", {"default": 1, "min": 1, "max": 20, "step": 1}),
                "resolution": (VIDEO_RESOLUTIONS, {"default": "720p"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 4294967295, "step": 1}),
                "video_model_override": (
                    "STRING",
                    {"default": "", "placeholder": "Blank = Omni Flash abra_t2v_<duration>s"},
                ),
                "timeout_seconds": ("INT", {"default": 1200, "min": 60, "max": 7200, "step": 60}),
            },
            "optional": {
                "start_image": ("IMAGE",),
                "end_image": ("IMAGE",),
                "reference_images": ("IMAGE",),
                **{f"reference_image_{index}": ("IMAGE",) for index in range(2, 11)},
                "source_video_media_id": ("STRING", {"default": ""}),
                "source_video_path": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("VHS_FILENAMES", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("vhs_filenames", "video_paths_json", "media_ids_json", "source_urls_json", "job_json")
    FUNCTION = "generate"
    CATEGORY = "Flow Agent"
    OUTPUT_NODE = True
    DESCRIPTION = "Omni Flash text/video, start image, first+last frame, ingredients, and video editing."

    @classmethod
    def IS_CHANGED(cls, **_kwargs):
        return float("nan")

    def generate(
        self,
        prompt,
        mode,
        aspect_ratio,
        duration,
        count,
        resolution,
        seed,
        video_model_override,
        timeout_seconds,
        start_image=None,
        end_image=None,
        reference_images=None,
        source_video_media_id="",
        source_video_path="",
        **kwargs,
    ):
        cleaned_prompt = prompt.strip()
        if not cleaned_prompt:
            raise FlowAgentError("Prompt cannot be empty.")
        if mode not in VIDEO_MODES:
            raise FlowAgentError(f"Unsupported video mode {mode!r}.")
        if duration not in VIDEO_DURATIONS:
            raise FlowAgentError("Duration must be 4, 6, 8, or 10 seconds.")
        if mode == "edit source video" and count != 1:
            raise FlowAgentError("Flow Agent video editing accepts one output per request; set count to 1.")

        client = FlowAgentClient.from_env()
        started = time.monotonic()
        client.assert_ready(timeout_seconds=min(15.0, float(timeout_seconds)))
        start_id, end_id, reference_ids, is_video = None, None, [], False

        if mode in {"start image to video", "first + last frame"}:
            ids = _upload_image_batch(
                client, start_image, started=started, timeout_seconds=timeout_seconds, max_images=1
            )
            if not ids:
                raise FlowAgentError(f"Mode {mode!r} requires start_image.")
            start_id = ids[0]
        if mode == "first + last frame":
            ids = _upload_image_batch(
                client, end_image, started=started, timeout_seconds=timeout_seconds, max_images=1
            )
            if not ids:
                raise FlowAgentError("First + last frame mode requires end_image.")
            end_id = ids[0]
        if mode in {"ingredients / reference images", "edit source video"}:
            reference_ids = _upload_image_sources(
                client,
                [reference_images]
                + [kwargs.get(f"reference_image_{index}") for index in range(2, 11)],
                started=started,
                timeout_seconds=timeout_seconds,
            )
            if mode == "ingredients / reference images" and not reference_ids:
                raise FlowAgentError("Ingredients mode requires reference_images (up to 10).")
        if mode == "edit source video":
            source_id, source_path = source_video_media_id.strip(), source_video_path.strip()
            if source_id and source_path:
                raise FlowAgentError("Provide source_video_media_id or source_video_path, not both.")
            if source_path:
                uploaded = client.upload_file(
                    source_path,
                    timeout_seconds=_remaining(started, timeout_seconds, "uploading source video"),
                )
                source_id = uploaded["media_id"]
            if not source_id:
                raise FlowAgentError(
                    "Edit mode requires one source video media ID or a video path on the RunPod filesystem."
                )
            start_id, is_video = source_id, True

        payload = client.generate_videos(
            prompt=cleaned_prompt,
            aspect=aspect_ratio,
            count=count,
            duration=duration,
            seed=seed,
            resolution=resolution,
            start_media_id=start_id,
            end_media_id=end_id,
            ref_media_ids=reference_ids,
            is_video=is_video,
            video_model=video_model_override.strip() or None,
            timeout_seconds=_remaining(started, timeout_seconds, "starting video generation"),
        )
        return _download_video_result(
            client,
            payload,
            requested_resolution=resolution,
            count=count,
            started=started,
            timeout_seconds=timeout_seconds,
        )


class FlowVideoUpsample:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "media_id": ("STRING", {"default": ""}),
                "resolution": (("1080p", "4k"), {"default": "1080p"}),
                "aspect_ratio": (VIDEO_ASPECTS, {"default": "landscape"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 4294967295, "step": 1}),
                "timeout_seconds": ("INT", {"default": 1200, "min": 60, "max": 7200, "step": 60}),
            }
        }

    RETURN_TYPES = ("VHS_FILENAMES", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("vhs_filenames", "video_paths_json", "media_ids_json", "source_urls_json", "job_json")
    FUNCTION = "upsample"
    CATEGORY = "Flow Agent"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **_kwargs):
        return float("nan")

    def upsample(self, media_id, resolution, aspect_ratio, seed, timeout_seconds):
        clean_media_id = media_id.strip()
        if not clean_media_id:
            raise FlowAgentError("media_id cannot be empty.")
        client = FlowAgentClient.from_env()
        started = time.monotonic()
        client.assert_ready(timeout_seconds=min(15.0, float(timeout_seconds)))
        payload = client.upsample_video(
            media_id=clean_media_id,
            resolution=resolution,
            aspect=aspect_ratio,
            seed=seed,
            timeout_seconds=_remaining(started, timeout_seconds, "starting video upsample"),
        )
        return _download_video_result(
            client,
            payload,
            requested_resolution=resolution,
            count=1,
            started=started,
            timeout_seconds=timeout_seconds,
        )


class FlowUploadMedia:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "media_path": ("STRING", {"default": ""}),
                "timeout_seconds": ("INT", {"default": 600, "min": 30, "max": 3600, "step": 30}),
            },
            "optional": {"image": ("IMAGE",)},
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("media_id", "source_url")
    FUNCTION = "upload"
    CATEGORY = "Flow Agent"

    def upload(self, media_path, timeout_seconds, image=None):
        path = media_path.strip()
        if bool(path) == (image is not None):
            raise FlowAgentError("Provide exactly one source: media_path or image.")
        client = FlowAgentClient.from_env()
        client.assert_ready(timeout_seconds=min(15.0, float(timeout_seconds)))
        if image is not None:
            payload = client.upload_media(
                tensor_batch_to_png_data_uris(image, max_images=1)[0],
                timeout_seconds=timeout_seconds,
            )
        else:
            payload = client.upload_file(path, timeout_seconds=timeout_seconds)
        return payload["media_id"], payload.get("url", "")
