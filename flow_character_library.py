"""Saved Character Creator dataset browser for ComfyUI."""

from __future__ import annotations

import json
import os
from typing import Any

from .flow_agent_client import FlowAgentError
from .image_utils import image_bytes_to_tensor


def _characters_root() -> str:
    try:
        import folder_paths

        output_root = folder_paths.get_output_directory()
    except (ImportError, AttributeError):
        output_root = os.path.abspath(os.path.join(os.getcwd(), "output"))
    root = os.path.abspath(os.path.join(output_root, "flow_agent", "characters"))
    os.makedirs(root, exist_ok=True)
    return root


def _safe_local_path(value: Any) -> str | None:
    path = os.path.abspath(str(value or "").strip())
    root = _characters_root()
    try:
        if os.path.commonpath((root, path)) != root:
            return None
    except ValueError:
        return None
    return path if os.path.isfile(path) else None


def _shot_spec(manifest: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": 1,
        "dataset_id": manifest.get("dataset_id", ""),
        "subject_description": manifest.get("subject_description", ""),
        "model": manifest.get("model", "gem_pix_2"),
        "aspect_ratio": manifest.get("aspect_ratio", "square (1:1)"),
        "references": manifest.get("references", []),
        "shot_number": record.get("shot_number"),
        "shot_id": record.get("shot_id", ""),
        "group": record.get("group", ""),
        "prompt_fragment": record.get("prompt_fragment", ""),
        "full_prompt": record.get("full_prompt", ""),
        "media_id": record.get("media_id", ""),
        "saved_path": record.get("saved_path", ""),
        "preview": record.get("preview"),
    }


def scan_character_datasets() -> list[dict[str, Any]]:
    """Return newest-first persisted datasets containing usable local shots."""
    datasets: list[dict[str, Any]] = []
    root = _characters_root()
    for folder_name in os.listdir(root):
        manifest_path = os.path.join(root, folder_name, "manifest.json")
        if not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path, "r", encoding="utf-8") as manifest_file:
                manifest = json.load(manifest_file)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, dict):
            continue
        shots = []
        for record in manifest.get("shots", []) or []:
            if not isinstance(record, dict) or record.get("status") != "succeeded":
                continue
            saved_path = _safe_local_path(record.get("saved_path"))
            preview = record.get("preview")
            if not saved_path or not isinstance(preview, dict) or not preview.get("filename"):
                continue
            shots.append(
                {
                    "shot_number": int(record.get("shot_number") or 0),
                    "shot_id": str(record.get("shot_id") or ""),
                    "media_id": str(record.get("media_id") or ""),
                    "full_prompt": str(record.get("full_prompt") or ""),
                    "preview": {
                        "filename": str(preview.get("filename") or ""),
                        "subfolder": str(preview.get("subfolder") or ""),
                        "type": str(preview.get("type") or "output"),
                    },
                }
            )
        if not shots:
            continue
        datasets.append(
            {
                "dataset_id": str(manifest.get("dataset_id") or folder_name),
                "subject_description": str(manifest.get("subject_description") or "Character"),
                "shot_preset": str(manifest.get("shot_preset") or "custom"),
                "created_at": int(os.path.getmtime(manifest_path)),
                "shot_count": len(shots),
                "shots": shots,
            }
        )
    datasets.sort(key=lambda item: item["created_at"], reverse=True)
    return datasets


def _find_selection(dataset_id: str, shot_number: int) -> tuple[dict[str, Any], dict[str, Any]]:
    root = _characters_root()
    for folder_name in os.listdir(root):
        manifest_path = os.path.join(root, folder_name, "manifest.json")
        if not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path, "r", encoding="utf-8") as manifest_file:
                manifest = json.load(manifest_file)
        except (OSError, json.JSONDecodeError):
            continue
        if str(manifest.get("dataset_id") or folder_name) != dataset_id:
            continue
        for record in manifest.get("shots", []) or []:
            if (
                isinstance(record, dict)
                and record.get("status") == "succeeded"
                and int(record.get("shot_number") or 0) == shot_number
            ):
                return manifest, record
    raise FlowAgentError(
        "The selected saved character shot is unavailable. Click Refresh datasets and choose again."
    )


def _register_routes() -> None:
    try:
        from aiohttp import web
        from server import PromptServer
    except (ImportError, AttributeError):
        return
    prompt_server = getattr(PromptServer, "instance", None)
    if prompt_server is None:
        return

    @prompt_server.routes.get("/flow-agent/character-library")
    async def flow_character_library_route(_request):
        try:
            return web.json_response({"datasets": scan_character_datasets()})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)


_register_routes()


class FlowCharacterShotSelector:
    """Browse and select one persisted Character Creator shot without generation."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "selection_json": ("STRING", {"default": "", "multiline": False}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "shot_spec_json", "shot_id", "media_id", "full_prompt")
    FUNCTION = "select_saved_shot"
    CATEGORY = "Flow Agent / Character"
    OUTPUT_NODE = True
    DESCRIPTION = (
        "Browse saved Character Creator datasets and select one existing shot. "
        "This node never sends a request to Google Flow."
    )

    def select_saved_shot(self, selection_json):
        try:
            selection = json.loads(str(selection_json or ""))
        except (TypeError, json.JSONDecodeError) as exc:
            raise FlowAgentError("Click Refresh datasets and choose a saved shot first.") from exc
        if not isinstance(selection, dict):
            raise FlowAgentError("Choose a saved character shot first.")
        dataset_id = str(selection.get("dataset_id") or "").strip()
        shot_number = int(selection.get("shot_number") or 0)
        if not dataset_id or shot_number < 1:
            raise FlowAgentError("Choose a saved character shot first.")

        manifest, record = _find_selection(dataset_id, shot_number)
        saved_path = _safe_local_path(record.get("saved_path"))
        if not saved_path:
            raise FlowAgentError("The selected character image file no longer exists.")
        with open(saved_path, "rb") as image_file:
            selected = image_bytes_to_tensor(image_file.read())
        spec = _shot_spec(manifest, record)
        preview = record.get("preview")
        return {
            "ui": {
                "images": [preview],
                "character_shot": [json.dumps(spec, ensure_ascii=False)],
            },
            "result": (
                selected,
                json.dumps(spec, ensure_ascii=False),
                str(record.get("shot_id") or ""),
                str(record.get("media_id") or ""),
                str(record.get("full_prompt") or ""),
            ),
        }
