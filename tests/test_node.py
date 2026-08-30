from __future__ import annotations

import json
import io
import sys
import types

import pytest
from PIL import Image

torch = pytest.importorskip("torch")

from comfyui_flow_agent_under_test import nodes


class FakeClient:
    uploaded = []
    generation_args = None

    @classmethod
    def from_env(cls):
        return cls()

    def assert_ready(self, timeout_seconds):
        return {"status": "healthy"}

    def upload_image(self, data_uri, timeout_seconds):
        self.uploaded.append(data_uri)
        return f"ref-{len(self.uploaded)}"

    def generate_images(self, **kwargs):
        type(self).generation_args = kwargs
        return [
            {"url": "https://unit.invalid/1.png", "media_id": "generated-1"},
            {"url": "https://unit.invalid/2.png", "media_id": "generated-2"},
        ]

    def download_generated_image(self, item, timeout_seconds):
        return item["url"].encode()


def test_node_uploads_reference_generates_and_batches(monkeypatch):
    FakeClient.uploaded = []
    monkeypatch.setattr(nodes, "FlowAgentClient", FakeClient)
    monkeypatch.setattr(
        nodes,
        "image_bytes_to_tensor",
        lambda _data: torch.zeros((1, 3, 4, 3)),
    )

    output, media_ids, urls = nodes.FlowNanoBanana().generate(
        prompt="  product photo  ",
        model="gem_pix_2",
        aspect_ratio="portrait (3:4)",
        count=2,
        seed=42,
        timeout_seconds=600,
        reference_image=torch.zeros((1, 2, 2, 3)),
    )

    assert tuple(output.shape) == (2, 3, 4, 3)
    assert len(FakeClient.uploaded) == 1
    assert FakeClient.generation_args["prompt"] == "product photo"
    assert FakeClient.generation_args["size"] == "1024x1365"
    assert FakeClient.generation_args["ref_media_ids"] == ["ref-1"]
    assert json.loads(media_ids) == ["generated-1", "generated-2"]
    assert len(json.loads(urls)) == 2


def test_video_result_exposes_native_video_and_inline_preview(monkeypatch, tmp_path):
    class FakeVideoClient:
        def download_media_to_file(self, _item, destination, timeout_seconds):
            del timeout_seconds
            with open(destination, "wb") as handle:
                handle.write(b"fake mp4")

    latest = types.ModuleType("comfy_api.latest")
    latest.InputImpl = types.SimpleNamespace(
        VideoFromFile=lambda path: {"native_video_path": path}
    )
    comfy_api = types.ModuleType("comfy_api")
    comfy_api.latest = latest
    monkeypatch.setitem(sys.modules, "comfy_api", comfy_api)
    monkeypatch.setitem(sys.modules, "comfy_api.latest", latest)
    monkeypatch.setattr(nodes, "_comfy_output_directory", lambda: str(tmp_path))

    response = nodes._download_video_result(
        FakeVideoClient(),
        {
            "status": "succeeded",
            "data": [
                {
                    "url": "https://unit.invalid/video.mp4",
                    "media_id": "video-1",
                    "resolution": "720p",
                }
            ],
        },
        requested_resolution="720p",
        count=1,
        started=nodes.time.monotonic(),
        timeout_seconds=60,
    )

    assert response["result"][0]["native_video_path"].endswith(".mp4")
    assert response["result"][1][0] is True
    assert response["ui"]["animated"] == (True,)
    assert response["ui"]["images"][0]["subfolder"] == "flow_agent"


def _png_bytes(value):
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (value, value, value)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeCharacterClient:
    uploaded = []
    generation_calls = []

    @classmethod
    def from_env(cls):
        return cls()

    def assert_ready(self, timeout_seconds):
        return {"status": "healthy"}

    def upload_image(self, data_uri, timeout_seconds):
        type(self).uploaded.append(data_uri)
        return "reference-character"

    def generate_images(self, **kwargs):
        type(self).generation_calls.append(kwargs)
        number = len(type(self).generation_calls)
        return [
            {
                "url": f"https://unit.invalid/character-{number}.png",
                "media_id": f"character-{number}",
            }
        ]

    def download_generated_image(self, item, timeout_seconds):
        number = int(item["media_id"].split("-")[-1])
        return _png_bytes(number * 20)


def test_character_creator_previews_every_result_and_builds_manifest(monkeypatch, tmp_path):
    FakeCharacterClient.uploaded = []
    FakeCharacterClient.generation_calls = []
    monkeypatch.setattr(nodes, "FlowAgentClient", FakeCharacterClient)
    monkeypatch.setattr(nodes, "_comfy_output_directory", lambda: str(tmp_path))

    response = nodes.FlowCharacterCreator().generate_dataset(
        reference_image=torch.zeros((1, 4, 4, 3)),
        subject_description="A blue-haired singer",
        shot_preset="all 22",
        shot_count=2,
        model="gem_pix_2",
        seed=43,
        retry_count=1,
        continue_on_error=True,
        timeout_per_image=600,
        preview_columns=2,
        dataset_name="Test Character",
    )

    images, contact_sheet, manifest_json, dataset_id, media_ids_json, paths_json = response["result"]
    manifest = json.loads(manifest_json)

    assert tuple(images.shape) == (2, 4, 4, 3)
    assert tuple(contact_sheet.shape)[0] == 1
    assert dataset_id.startswith("test_character_")
    assert manifest["successful_shots"] == 2
    assert [shot["shot_id"] for shot in manifest["shots"]] == [
        "face_front",
        "face_three_quarter_left",
    ]
    assert json.loads(media_ids_json) == ["character-1", "character-2"]
    assert len(json.loads(paths_json)) == 2
    assert len(response["ui"]["images"]) == 3  # Contact sheet plus every image.
    assert len(FakeCharacterClient.uploaded) == 1
    assert len(FakeCharacterClient.generation_calls) == 2
    assert FakeCharacterClient.generation_calls[0]["ref_media_ids"] == [
        "reference-character"
    ]
    assert (
        FakeCharacterClient.generation_calls[0]["idempotency_key"]
        != FakeCharacterClient.generation_calls[1]["idempotency_key"]
    )


def test_character_selector_and_regenerator_use_stable_shot_identity(monkeypatch, tmp_path):
    FakeCharacterClient.uploaded = []
    FakeCharacterClient.generation_calls = []
    monkeypatch.setattr(nodes, "FlowAgentClient", FakeCharacterClient)
    monkeypatch.setattr(nodes, "_comfy_output_directory", lambda: str(tmp_path))

    created = nodes.FlowCharacterCreator().generate_dataset(
        reference_image=torch.zeros((1, 4, 4, 3)),
        subject_description="A blue-haired singer",
        shot_preset="face angles 8",
        shot_count=2,
        model="gem_pix_2",
        seed=43,
        retry_count=0,
        continue_on_error=True,
        timeout_per_image=600,
        preview_columns=2,
        dataset_name="Selector Test",
    )
    images, _, manifest_json, _, _, _ = created["result"]
    selected = nodes.FlowCharacterShotSelector().select(
        images=images,
        manifest_json=manifest_json,
        shot_number=2,
    )
    selected_image, shot_spec_json, shot_id, previous_media_id, full_prompt = selected[
        "result"
    ]

    assert tuple(selected_image.shape) == (1, 4, 4, 3)
    assert shot_id == "face_three_quarter_left"
    assert previous_media_id == "character-2"
    assert "3/4 view facing left" in full_prompt
    assert selected["ui"]["images"][0]["filename"]

    FakeCharacterClient.generation_calls = []
    regenerated = nodes.FlowGenerateCharacterShot().regenerate(
        reference_image=torch.zeros((1, 4, 4, 3)),
        shot_spec_json=shot_spec_json,
        model="gem_pix_2",
        seed=43,
        retry_count=1,
        timeout_seconds=600,
    )
    _, new_media_id, regenerated_shot_id, result_json, saved_path = regenerated[
        "result"
    ]
    record = json.loads(result_json)

    assert regenerated_shot_id == shot_id
    assert new_media_id == "character-1"
    assert record["replaces_media_id"] == previous_media_id
    assert record["shot_id"] == shot_id
    assert saved_path
    assert regenerated["ui"]["images"][0]["filename"]
