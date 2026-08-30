"""ComfyUI nodes for Flow Agent image, video, upload, and upsample APIs."""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from typing import Any

from .character_shots import (
    CHARACTER_PRESET_NAMES,
    build_character_prompt,
    resolve_character_shots,
    slugify,
)
from .flow_agent_client import FlowAgentClient, FlowAgentError
from .image_utils import (
    image_bytes_to_tensor,
    make_contact_sheet,
    stack_image_tensors,
    tensor_batch_to_png_data_uris,
)

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


def _new_dataset_id(dataset_name: str) -> str:
    prefix = slugify(dataset_name, fallback="character")
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}_{uuid.uuid4().hex[:6]}"


def _image_extension(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def _save_character_preview(
    data: bytes,
    *,
    dataset_id: str,
    filename_stem: str,
) -> tuple[str, dict[str, str]]:
    safe_dataset_id = slugify(dataset_id, fallback="character")
    safe_stem = slugify(filename_stem, fallback="image")
    extension = _image_extension(data)
    relative_folder = os.path.join("characters", safe_dataset_id)
    output_folder = os.path.join(_comfy_output_directory(), relative_folder)
    os.makedirs(output_folder, exist_ok=True)
    filename = f"{safe_stem}{extension}"
    destination = os.path.join(output_folder, filename)
    with open(destination, "wb") as handle:
        handle.write(data)
    return destination, {
        "filename": filename,
        "subfolder": os.path.join("flow_agent", relative_folder).replace("\\", "/"),
        "type": "output",
    }


def _tensor_png_bytes(image) -> bytes:
    data_uri = tensor_batch_to_png_data_uris(image, max_images=1)[0]
    return base64.b64decode(data_uri.split(",", 1)[1])


def _parse_json_object(value: str, field_name: str) -> dict[str, Any]:
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise FlowAgentError(f"{field_name} must contain a valid JSON object.") from exc
    if not isinstance(payload, dict):
        raise FlowAgentError(f"{field_name} must contain a JSON object.")
    return payload


def _preview_from_record(record: dict[str, Any]) -> dict[str, str] | None:
    preview = record.get("preview")
    if not isinstance(preview, dict) or not preview.get("filename"):
        return None
    return {
        "filename": str(preview["filename"]),
        "subfolder": str(preview.get("subfolder", "")),
        "type": str(preview.get("type", "output")),
    }


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
    try:
        from comfy_api.latest import InputImpl

        native_video = InputImpl.VideoFromFile(paths[0])
    except (ImportError, AttributeError) as exc:
        raise FlowAgentError(
            "This ComfyUI build does not provide the native VIDEO API required by "
            "comfyui-flow-agent. Update ComfyUI and restart it."
        ) from exc

    result = (
        native_video,
        (True, paths),
        json.dumps(paths, ensure_ascii=False),
        json.dumps([item.get("media_id") for item in items], ensure_ascii=False),
        json.dumps([item.get("url") for item in items], ensure_ascii=False),
        json.dumps(payload, ensure_ascii=False),
    )
    # Native ComfyUI PreviewVideo uses the regular saved-image descriptors plus
    # the animated flag. Keep `gifs` too for VideoHelperSuite compatibility.
    saved_results = [
        {
            "filename": preview["filename"],
            "subfolder": preview["subfolder"],
            "type": preview["type"],
        }
        for preview in previews
    ]
    return {
        "ui": {
            "images": saved_results,
            "animated": (True,),
            "gifs": previews,
        },
        "result": result,
    }


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


class FlowCharacterCreator:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "reference_image": ("IMAGE",),
                "subject_description": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "A single character portrait",
                        "dynamicPrompts": True,
                    },
                ),
                "shot_preset": (CHARACTER_PRESET_NAMES, {"default": "all 22"}),
                "shot_count": ("INT", {"default": 22, "min": 1, "max": 102, "step": 1}),
                "model": (MODEL_IDS, {"default": "gem_pix_2"}),
                "seed": ("INT", {"default": 43, "min": 0, "max": 4294967295, "step": 1}),
                "retry_count": ("INT", {"default": 1, "min": 0, "max": 3, "step": 1}),
                "continue_on_error": ("BOOLEAN", {"default": True}),
                "timeout_per_image": (
                    "INT",
                    {"default": 600, "min": 30, "max": 3600, "step": 30},
                ),
                "preview_columns": ("INT", {"default": 4, "min": 1, "max": 8, "step": 1}),
                "dataset_name": ("STRING", {"default": "character"}),
            },
            "optional": {
                "custom_shots": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "placeholder": "One custom shot prompt per line",
                    },
                ),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = (
        "images",
        "contact_sheet",
        "manifest_json",
        "dataset_id",
        "media_ids_json",
        "saved_paths_json",
    )
    FUNCTION = "generate_dataset"
    CATEGORY = "Flow Agent / Character"
    OUTPUT_NODE = True
    DESCRIPTION = (
        "Generate a labeled, previewable character dataset from one reference image. "
        "Includes the 22-shot Character Persona preset and custom shot lists."
    )

    @classmethod
    def IS_CHANGED(cls, **_kwargs):
        return float("nan")

    def generate_dataset(
        self,
        reference_image,
        subject_description,
        shot_preset,
        shot_count,
        model,
        seed,
        retry_count,
        continue_on_error,
        timeout_per_image,
        preview_columns,
        dataset_name,
        custom_shots="",
    ):
        shots = resolve_character_shots(shot_preset, custom_shots, shot_count)
        dataset_id = _new_dataset_id(dataset_name)
        client = FlowAgentClient.from_env()
        client.assert_ready(timeout_seconds=min(15.0, float(timeout_per_image)))
        upload_started = time.monotonic()
        reference_ids = _upload_image_batch(
            client,
            reference_image,
            started=upload_started,
            timeout_seconds=timeout_per_image,
            max_images=1,
        )
        if len(reference_ids) != 1:
            raise FlowAgentError("Character Creator requires exactly one reference image.")
        reference_media_id = reference_ids[0]

        records: list[dict[str, Any]] = []
        tensors, previews, media_ids, source_urls, saved_paths = [], [], [], [], []
        for shot_number, shot in enumerate(shots, start=1):
            full_prompt = build_character_prompt(
                shot.prompt_fragment,
                subject_description,
            )
            record: dict[str, Any] = {
                "shot_number": shot_number,
                **shot.to_dict(),
                "full_prompt": full_prompt,
                "seed": seed,
                "status": "pending",
                "attempts": 0,
                "batch_index": None,
            }
            idempotency_key = f"comfyui-character-{dataset_id}-{shot.shot_id}"
            last_error: Exception | None = None
            for attempt in range(1, int(retry_count) + 2):
                record["attempts"] = attempt
                try:
                    item = client.generate_images(
                        prompt=full_prompt,
                        model=model,
                        size="1024x1024",
                        count=1,
                        seed=seed,
                        ref_media_ids=[reference_media_id],
                        timeout_seconds=float(timeout_per_image),
                        idempotency_key=idempotency_key,
                    )[0]
                    image_bytes = client.download_generated_image(
                        item,
                        timeout_seconds=min(120.0, float(timeout_per_image)),
                    )
                    tensor = image_bytes_to_tensor(image_bytes)
                    media_id = str(item.get("media_id") or "")
                    filename_stem = (
                        f"{shot_number:03d}_{shot.shot_id}_{media_id[:8] or 'generated'}"
                    )
                    saved_path, preview = _save_character_preview(
                        image_bytes,
                        dataset_id=dataset_id,
                        filename_stem=filename_stem,
                    )
                    record.update(
                        {
                            "status": "succeeded",
                            "batch_index": len(tensors),
                            "media_id": media_id,
                            "source_url": item.get("url"),
                            "saved_path": saved_path,
                            "preview": preview,
                        }
                    )
                    tensors.append(tensor)
                    previews.append(preview)
                    media_ids.append(media_id)
                    source_urls.append(item.get("url"))
                    saved_paths.append(saved_path)
                    last_error = None
                    break
                except Exception as exc:  # Keep successful paid generations on partial failure.
                    last_error = exc
            if last_error is not None:
                record.update({"status": "failed", "error": str(last_error)})
                records.append(record)
                if not continue_on_error:
                    raise FlowAgentError(
                        f"Character shot {shot_number} ({shot.shot_id}) failed: {last_error}"
                    ) from last_error
                continue
            records.append(record)

        if not tensors:
            failures = "; ".join(
                f"{record['shot_id']}: {record.get('error', 'unknown error')}"
                for record in records[:3]
            )
            raise FlowAgentError(f"Character Creator generated no images. {failures}")

        image_batch = stack_image_tensors(tensors)
        contact_sheet = make_contact_sheet(image_batch, columns=preview_columns)
        contact_path, contact_preview = _save_character_preview(
            _tensor_png_bytes(contact_sheet),
            dataset_id=dataset_id,
            filename_stem="000_contact_sheet",
        )
        manifest = {
            "version": 1,
            "dataset_id": dataset_id,
            "shot_preset": shot_preset,
            "requested_shots": len(shots),
            "successful_shots": len(tensors),
            "failed_shots": len(shots) - len(tensors),
            "subject_description": subject_description.strip(),
            "model": model,
            "aspect_ratio": "1:1",
            "reference_media_id": reference_media_id,
            "contact_sheet_path": contact_path,
            "source_urls": source_urls,
            "shots": records,
        }
        ui_summary = {
            "dataset_id": dataset_id,
            "requested_shots": len(shots),
            "successful_shots": len(tensors),
            "failed_shots": len(shots) - len(tensors),
            "shots": [
                {
                    "shot_number": record["shot_number"],
                    "shot_id": record["shot_id"],
                    "status": record["status"],
                    "media_id": record.get("media_id", ""),
                    "error": record.get("error", ""),
                }
                for record in records
            ],
        }
        result = (
            image_batch,
            contact_sheet,
            json.dumps(manifest, ensure_ascii=False),
            dataset_id,
            json.dumps(media_ids, ensure_ascii=False),
            json.dumps(saved_paths, ensure_ascii=False),
        )
        return {
            "ui": {
                "images": [contact_preview, *previews],
                "character_dataset": [json.dumps(ui_summary, ensure_ascii=False)],
            },
            "result": result,
        }


class FlowCharacterShotSelector:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "manifest_json": ("STRING", {"multiline": True, "default": ""}),
                "shot_number": ("INT", {"default": 1, "min": 1, "max": 102, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "shot_spec_json", "shot_id", "media_id", "full_prompt")
    FUNCTION = "select"
    CATEGORY = "Flow Agent / Character"
    OUTPUT_NODE = True
    DESCRIPTION = "Select and preview one logical shot from a Character Creator dataset."

    def select(self, images, manifest_json, shot_number):
        manifest = _parse_json_object(manifest_json, "manifest_json")
        records = manifest.get("shots")
        if not isinstance(records, list):
            raise FlowAgentError("manifest_json does not contain a shots list.")
        record = next(
            (
                item
                for item in records
                if isinstance(item, dict) and item.get("shot_number") == shot_number
            ),
            None,
        )
        if record is None:
            raise FlowAgentError(f"Shot number {shot_number} is not present in this manifest.")
        if record.get("status") != "succeeded" or not isinstance(record.get("batch_index"), int):
            raise FlowAgentError(
                f"Shot {shot_number} ({record.get('shot_id', 'unknown')}) did not generate successfully."
            )
        batch_index = record["batch_index"]
        if getattr(images, "ndim", 0) == 3:
            images = images.unsqueeze(0)
        if batch_index < 0 or batch_index >= int(images.shape[0]):
            raise FlowAgentError(
                f"Manifest batch_index {batch_index} is outside the connected IMAGE batch."
            )
        selected = images[batch_index : batch_index + 1]
        shot_spec = {
            "version": 1,
            "dataset_id": manifest.get("dataset_id", ""),
            "subject_description": manifest.get("subject_description", ""),
            "model": manifest.get("model", "gem_pix_2"),
            "shot_number": record["shot_number"],
            "shot_id": record["shot_id"],
            "group": record.get("group", ""),
            "prompt_fragment": record.get("prompt_fragment", ""),
            "full_prompt": record.get("full_prompt", ""),
            "media_id": record.get("media_id", ""),
            "saved_path": record.get("saved_path", ""),
            "preview": record.get("preview"),
        }
        preview = _preview_from_record(record)
        ui = {
            "character_shot": [json.dumps(shot_spec, ensure_ascii=False)],
        }
        if preview:
            ui["images"] = [preview]
        return {
            "ui": ui,
            "result": (
                selected,
                json.dumps(shot_spec, ensure_ascii=False),
                str(record.get("shot_id", "")),
                str(record.get("media_id", "")),
                str(record.get("full_prompt", "")),
            ),
        }


class FlowGenerateCharacterShot:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "reference_image": ("IMAGE",),
                "shot_spec_json": ("STRING", {"multiline": True, "default": ""}),
                "model": (MODEL_IDS, {"default": "gem_pix_2"}),
                "seed": ("INT", {"default": 43, "min": 0, "max": 4294967295, "step": 1}),
                "retry_count": ("INT", {"default": 1, "min": 0, "max": 3, "step": 1}),
                "timeout_seconds": (
                    "INT",
                    {"default": 600, "min": 30, "max": 3600, "step": 30},
                ),
            },
            "optional": {
                "previous_media_id": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "media_id", "shot_id", "result_json", "saved_path")
    FUNCTION = "regenerate"
    CATEGORY = "Flow Agent / Character"
    OUTPUT_NODE = True
    DESCRIPTION = (
        "Regenerate one selected character shot using the original reference image and shot prompt."
    )

    @classmethod
    def IS_CHANGED(cls, **_kwargs):
        return float("nan")

    def regenerate(
        self,
        reference_image,
        shot_spec_json,
        model,
        seed,
        retry_count,
        timeout_seconds,
        previous_media_id="",
    ):
        spec = _parse_json_object(shot_spec_json, "shot_spec_json")
        shot_id = str(spec.get("shot_id") or "").strip()
        full_prompt = str(spec.get("full_prompt") or "").strip()
        if not shot_id or not full_prompt:
            raise FlowAgentError("shot_spec_json must contain non-empty shot_id and full_prompt values.")
        dataset_id = str(spec.get("dataset_id") or _new_dataset_id("character"))
        replaced_media_id = previous_media_id.strip() or str(spec.get("media_id") or "")

        client = FlowAgentClient.from_env()
        client.assert_ready(timeout_seconds=min(15.0, float(timeout_seconds)))
        upload_started = time.monotonic()
        reference_ids = _upload_image_batch(
            client,
            reference_image,
            started=upload_started,
            timeout_seconds=timeout_seconds,
            max_images=1,
        )
        if len(reference_ids) != 1:
            raise FlowAgentError("Generate Character Shot requires exactly one reference image.")

        regeneration_id = uuid.uuid4().hex[:8]
        idempotency_key = f"comfyui-character-regen-{dataset_id}-{shot_id}-{regeneration_id}"
        last_error: Exception | None = None
        item: dict[str, Any] | None = None
        image_bytes: bytes | None = None
        for attempt in range(1, int(retry_count) + 2):
            try:
                item = client.generate_images(
                    prompt=full_prompt,
                    model=model,
                    size="1024x1024",
                    count=1,
                    seed=seed,
                    ref_media_ids=reference_ids,
                    timeout_seconds=float(timeout_seconds),
                    idempotency_key=idempotency_key,
                )[0]
                image_bytes = client.download_generated_image(
                    item,
                    timeout_seconds=min(120.0, float(timeout_seconds)),
                )
                last_error = None
                break
            except Exception as exc:
                last_error = exc
        if last_error is not None or item is None or image_bytes is None:
            raise FlowAgentError(f"Character shot {shot_id} could not be regenerated: {last_error}")

        media_id = str(item.get("media_id") or "")
        shot_number = int(spec.get("shot_number") or 1)
        saved_path, preview = _save_character_preview(
            image_bytes,
            dataset_id=dataset_id,
            filename_stem=f"{shot_number:03d}_{shot_id}_regen_{media_id[:8] or regeneration_id}",
        )
        result_record = {
            **spec,
            "status": "regenerated",
            "model": model,
            "seed": seed,
            "media_id": media_id,
            "source_url": item.get("url"),
            "saved_path": saved_path,
            "preview": preview,
            "replaces_media_id": replaced_media_id,
            "regeneration_id": regeneration_id,
        }
        result_json = json.dumps(result_record, ensure_ascii=False)
        return {
            "ui": {
                "images": [preview],
                "character_shot": [result_json],
            },
            "result": (
                image_bytes_to_tensor(image_bytes),
                media_id,
                shot_id,
                result_json,
                saved_path,
            ),
        }


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

    RETURN_TYPES = ("VIDEO", "VHS_FILENAMES", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "vhs_filenames", "video_paths_json", "media_ids_json", "source_urls_json", "job_json")
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

    RETURN_TYPES = ("VIDEO", "VHS_FILENAMES", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "vhs_filenames", "video_paths_json", "media_ids_json", "source_urls_json", "job_json")
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
