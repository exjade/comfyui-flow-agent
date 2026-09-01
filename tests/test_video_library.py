from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

from comfyui_flow_agent_under_test import flow_video_library as library


def test_video_history_is_filtered_classified_and_sorted():
    records = library.normalise_video_history(
        {
            "history": [
                {"type": "image", "media_id": "image-1", "url": "/image.jpg"},
                {
                    "type": "video",
                    "media_id": "generated-1",
                    "url": "/generated.mp4",
                    "prompt": "Generated clip",
                    "timestamp": 10,
                    "source": "generated",
                },
                {
                    "type": "video",
                    "media_id": "uploaded-1",
                    "filename": "uploaded.mp4",
                    "timestamp": 20,
                    "source": "upload",
                },
                {
                    "type": "video",
                    "media_id": "upscaled-1",
                    "filename": "upscaled.mp4",
                    "timestamp": 30,
                    "source_media_id": "generated-1",
                },
                {"type": "video", "media_id": "missing-file-and-url"},
            ]
        }
    )

    assert [item["media_id"] for item in records] == [
        "upscaled-1",
        "uploaded-1",
        "generated-1",
    ]
    assert [item["library_kind"] for item in records] == [
        "upsampled",
        "uploaded",
        "generated",
    ]


def test_video_library_selects_downloads_and_returns_plain_media_id(monkeypatch, tmp_path):
    record = {
        "type": "video",
        "media_id": "video-123",
        "filename": "original.mp4",
        "url": "http://127.0.0.1:8001/download/original.mp4",
        "prompt": "Wave at camera",
        "timestamp": 100,
        "source": "generated",
    }

    class FakeClient:
        config = types.SimpleNamespace(base_url="https://flow.example")
        downloaded_item = None

        @classmethod
        def from_env(cls):
            return cls()

        def assert_ready(self, timeout_seconds):
            return {"status": "healthy"}

        def list_media_history(self, timeout_seconds):
            return {"history": [record]}

        def download_media_to_file(self, item, destination, timeout_seconds):
            type(self).downloaded_item = item
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with open(destination, "wb") as handle:
                handle.write(b"video")

    latest = types.ModuleType("comfy_api.latest")
    latest.InputImpl = types.SimpleNamespace(
        VideoFromFile=lambda path: {"native_video_path": path}
    )
    comfy_api = types.ModuleType("comfy_api")
    comfy_api.latest = latest
    monkeypatch.setitem(sys.modules, "comfy_api", comfy_api)
    monkeypatch.setitem(sys.modules, "comfy_api.latest", latest)
    monkeypatch.setattr(library, "FlowAgentClient", FakeClient)
    monkeypatch.setattr(library, "_library_output_directory", lambda: str(tmp_path))

    response = library.FlowVideoLibrary().select_video("video-123", 600)
    video, media_id, prompt, source_url, metadata_json = response["result"]

    assert media_id == "video-123"
    assert prompt == "Wave at camera"
    assert source_url == "https://flow.example/download/original.mp4"
    assert FakeClient.downloaded_item["url"] == source_url
    assert os.path.isfile(video["native_video_path"])
    assert json.loads(metadata_json)["library_kind"] == "generated"
    assert response["ui"]["animated"] == (True,)


def test_existing_generation_nodes_remain_in_their_original_module():
    nodes_source = (Path(__file__).resolve().parents[1] / "nodes.py").read_text(
        encoding="utf-8"
    )
    assert "class FlowVideoLibrary" not in nodes_source
