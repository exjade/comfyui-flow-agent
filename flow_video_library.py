"""Independent Flow video-history browser and selector for ComfyUI."""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any
from urllib.parse import quote, urlparse

from .flow_agent_client import FlowAgentClient, FlowAgentError


def normalise_video_history(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Return newest-first usable video records without changing history."""
    records: list[dict[str, Any]] = []
    for raw in document.get("history", []):
        if not isinstance(raw, dict) or str(raw.get("type") or "").lower() != "video":
            continue
        media_id = str(raw.get("media_id") or "").strip()
        url = str(raw.get("url") or "").strip()
        filename = os.path.basename(str(raw.get("filename") or "").strip())
        if not media_id or (not url and not filename):
            continue
        record = dict(raw)
        record["media_id"] = media_id
        record["url"] = url
        record["filename"] = filename
        record["prompt"] = str(raw.get("prompt") or "Untitled Flow video").strip()
        record["timestamp"] = int(raw.get("timestamp") or 0)
        record["source"] = str(raw.get("source") or "generated").strip().lower()
        record["library_kind"] = (
            "upsampled"
            if raw.get("source_media_id")
            else "uploaded"
            if record["source"] == "upload"
            else "generated"
        )
        records.append(record)
    records.sort(key=lambda item: item["timestamp"], reverse=True)
    return records


def _current_media_url(client: FlowAgentClient, record: dict[str, Any]) -> str:
    filename = os.path.basename(str(record.get("filename") or "").strip())
    if filename:
        return f"{client.config.base_url}/download/{quote(filename)}"
    raw_url = str(record.get("url") or "").strip()
    parsed = urlparse(raw_url)
    if parsed.hostname in {"127.0.0.1", "localhost"}:
        return f"{client.config.base_url}{parsed.path}"
    return raw_url


def _library_output_directory() -> str:
    try:
        import folder_paths

        root = folder_paths.get_output_directory()
    except (ImportError, AttributeError):
        root = os.path.abspath(os.path.join(os.getcwd(), "output"))
    destination = os.path.join(root, "flow_agent", "library")
    os.makedirs(destination, exist_ok=True)
    return destination


def _history_payload(limit: int = 100) -> dict[str, Any]:
    client = FlowAgentClient.from_env()
    client.assert_ready(timeout_seconds=15.0)
    records = normalise_video_history(client.list_media_history(timeout_seconds=15.0))[:limit]
    videos = []
    for record in records:
        item = dict(record)
        item["preview_url"] = _current_media_url(client, record)
        videos.append(item)
    return {"videos": videos, "count": len(videos)}


def _register_routes() -> None:
    try:
        from aiohttp import web
        from server import PromptServer
    except (ImportError, AttributeError):
        return

    prompt_server = getattr(PromptServer, "instance", None)
    if prompt_server is None:
        return

    @prompt_server.routes.get("/flow-agent/video-library")
    async def flow_video_library_route(_request):
        try:
            return web.json_response(_history_payload())
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=502)


_register_routes()


class FlowVideoLibrary:
    """Select one previously tracked Flow video without handling raw JSON."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "selected_media_id": (
                    "STRING",
                    {"default": "", "multiline": False},
                ),
                "timeout_seconds": (
                    "INT",
                    {"default": 600, "min": 30, "max": 3600, "step": 30},
                ),
            }
        }

    RETURN_TYPES = ("VIDEO", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = (
        "video",
        "media_id",
        "original_prompt",
        "source_url",
        "metadata_json",
    )
    FUNCTION = "select_video"
    CATEGORY = "Flow Agent"
    DESCRIPTION = "Browse and select a previously tracked Flow video."

    @classmethod
    def IS_CHANGED(cls, **_kwargs):
        return float("nan")

    def select_video(self, selected_media_id, timeout_seconds):
        media_id = str(selected_media_id or "").strip()
        if not media_id:
            raise FlowAgentError("Click Refresh videos and select a Flow video first.")

        client = FlowAgentClient.from_env()
        client.assert_ready(timeout_seconds=min(15.0, float(timeout_seconds)))
        records = normalise_video_history(
            client.list_media_history(timeout_seconds=min(30.0, float(timeout_seconds)))
        )
        record = next((item for item in records if item["media_id"] == media_id), None)
        if record is None:
            raise FlowAgentError(
                f"Video {media_id!r} is no longer present in Flow Agent history. "
                "Click Refresh videos and choose an available item."
            )

        current_url = _current_media_url(client, record)
        filename = f"flow_library_{int(time.time())}_{uuid.uuid4().hex[:8]}.mp4"
        destination = os.path.join(_library_output_directory(), filename)
        client.download_media_to_file(
            {**record, "url": current_url},
            destination,
            timeout_seconds=min(600.0, float(timeout_seconds)),
        )

        try:
            from comfy_api.latest import InputImpl

            native_video = InputImpl.VideoFromFile(destination)
        except (ImportError, AttributeError) as exc:
            raise FlowAgentError(
                "This ComfyUI build does not provide the native VIDEO API. "
                "Update ComfyUI and restart it."
            ) from exc

        preview = {
            "filename": filename,
            "subfolder": "flow_agent/library",
            "type": "output",
        }
        metadata = {**record, "source_url": current_url, "saved_path": destination}
        return {
            "ui": {
                "images": [preview],
                "animated": (True,),
                "gifs": [{**preview, "format": "video/mp4", "fullpath": destination}],
            },
            "result": (
                native_video,
                media_id,
                record["prompt"],
                current_url,
                json.dumps(metadata, ensure_ascii=False),
            ),
        }
