from __future__ import annotations

import json
import io
import sys
import types
from contextlib import nullcontext

import pytest
from PIL import Image

torch = pytest.importorskip("torch")

from comfyui_flow_agent_under_test import flow_character_library, nodes


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
    assert FakeClient.generation_args["exclude_media_ids"] == ["ref-1"]
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


def test_video_mode_rejects_reference_images_before_paid_request(monkeypatch):
    class UnexpectedClient:
        @classmethod
        def from_env(cls):
            raise AssertionError("Client must not be created for an invalid mode/input combination")

    monkeypatch.setattr(nodes, "FlowAgentClient", UnexpectedClient)

    with pytest.raises(nodes.FlowAgentError, match="would ignore them"):
        nodes.FlowOmniFlashVideo().generate(
            prompt="Slow camera move",
            mode="text to video",
            aspect_ratio="landscape",
            duration=8,
            count=1,
            resolution="720p",
            seed=43,
            video_model_override="",
            timeout_seconds=1200,
            reference_images=torch.zeros((1, 4, 4, 3)),
        )


def test_video_mode_rejects_start_image_before_paid_request(monkeypatch):
    class UnexpectedClient:
        @classmethod
        def from_env(cls):
            raise AssertionError("Client must not be created for an invalid mode/input combination")

    monkeypatch.setattr(nodes, "FlowAgentClient", UnexpectedClient)

    with pytest.raises(nodes.FlowAgentError, match="would ignore it"):
        nodes.FlowOmniFlashVideo().generate(
            prompt="Slow camera move",
            mode="text to video",
            aspect_ratio="landscape",
            duration=8,
            count=1,
            resolution="720p",
            seed=43,
            video_model_override="",
            timeout_seconds=1200,
            start_image=torch.zeros((1, 4, 4, 3)),
        )


def test_video_mode_rejects_hidden_source_video_before_paid_request(monkeypatch):
    class UnexpectedClient:
        @classmethod
        def from_env(cls):
            raise AssertionError("Client must not be created for an invalid mode/input combination")

    monkeypatch.setattr(nodes, "FlowAgentClient", UnexpectedClient)

    with pytest.raises(nodes.FlowAgentError, match="would ignore it"):
        nodes.FlowOmniFlashVideo().generate(
            prompt="Slow camera move",
            mode="text to video",
            aspect_ratio="landscape",
            duration=8,
            count=1,
            resolution="720p",
            seed=43,
            video_model_override="",
            timeout_seconds=1200,
            source_video_media_id="hidden-old-source",
        )


def test_edit_source_video_rejects_additional_references_before_paid_request(monkeypatch):
    class UnexpectedClient:
        @classmethod
        def from_env(cls):
            raise AssertionError("Client must not be created when edit mode has references")

    monkeypatch.setattr(nodes, "FlowAgentClient", UnexpectedClient)

    with pytest.raises(nodes.FlowAgentError, match="Reference images are connected"):
        nodes.FlowOmniFlashVideo().generate(
            prompt="Remove the logo",
            mode="edit source video",
            aspect_ratio="landscape",
            duration=8,
            count=1,
            resolution="720p",
            seed=43,
            video_model_override="",
            timeout_seconds=1200,
            source_video_media_id="source-video",
            reference_media_ids='["extra-image"]',
        )


def test_video_to_video_rejects_additional_video_references_before_paid_request(monkeypatch):
    class UnexpectedClient:
        @classmethod
        def from_env(cls):
            raise AssertionError("Client must not be created for a hidden video reference")

    monkeypatch.setattr(nodes, "FlowAgentClient", UnexpectedClient)

    with pytest.raises(nodes.FlowAgentError, match="Reference videos are connected"):
        nodes.FlowOmniFlashVideo().generate(
            prompt="Use this visual style",
            mode="video to video",
            aspect_ratio="landscape",
            duration=8,
            count=1,
            resolution="720p",
            seed=43,
            video_model_override="",
            timeout_seconds=1200,
            source_video_media_id="source-video",
            reference_video_media_ids='["extra-video"]',
        )


def test_video_reuses_existing_flow_media_id_without_upload(monkeypatch):
    class ReuseVideoClient:
        generation_args = None

        @classmethod
        def from_env(cls):
            return cls()

        def assert_ready(self, timeout_seconds):
            return {"status": "healthy"}

        def upload_image(self, *_args, **_kwargs):
            raise AssertionError("An existing Flow media ID must not be uploaded again")

        def generate_videos(self, **kwargs):
            type(self).generation_args = kwargs
            return {"status": "succeeded", "data": []}

    monkeypatch.setattr(nodes, "FlowAgentClient", ReuseVideoClient)
    monkeypatch.setattr(nodes, "_download_video_result", lambda *_args, **_kwargs: "ok")

    result = nodes.FlowOmniFlashVideo().generate(
        prompt="Slow deliberate camera move",
        mode="ingredients / reference images",
        aspect_ratio="landscape",
        duration=8,
        count=1,
        resolution="720p",
        seed=43,
        video_model_override="",
        timeout_seconds=1200,
        reference_media_ids='["original-flow-contact-sheet"]',
    )

    assert result == "ok"
    assert ReuseVideoClient.generation_args["ref_media_ids"] == [
        "original-flow-contact-sheet"
    ]


def test_video_ingredients_accept_existing_and_local_video_references(monkeypatch):
    class VideoReferenceClient:
        generation_args = None
        uploaded_paths = []

        @classmethod
        def from_env(cls):
            return cls()

        def assert_ready(self, timeout_seconds):
            return {"status": "healthy"}

        def upload_file(self, path, timeout_seconds):
            type(self).uploaded_paths.append(path)
            return {"media_id": f"uploaded-video-{len(type(self).uploaded_paths)}"}

        def generate_videos(self, **kwargs):
            type(self).generation_args = kwargs
            return {"status": "succeeded", "data": []}

    VideoReferenceClient.uploaded_paths = []
    monkeypatch.setattr(nodes, "FlowAgentClient", VideoReferenceClient)
    monkeypatch.setattr(nodes, "_download_video_result", lambda *_args, **_kwargs: "ok")

    result = nodes.FlowOmniFlashVideo().generate(
        prompt="Use the motion and lighting from the reference clips",
        mode="ingredients / reference images",
        aspect_ratio="landscape",
        duration=8,
        count=1,
        resolution="720p",
        seed=43,
        video_model_override="",
        timeout_seconds=1200,
        reference_media_ids='["image-reference"]',
        reference_video_media_ids='["existing-video-reference"]',
        reference_video_paths="D:\\clips\\motion.mp4",
    )

    assert result == "ok"
    assert VideoReferenceClient.uploaded_paths == ["D:\\clips\\motion.mp4"]
    assert VideoReferenceClient.generation_args["ref_media_ids"] == [
        "image-reference",
        "existing-video-reference",
        "uploaded-video-1",
    ]


def test_video_to_video_alias_uses_one_source_video(monkeypatch):
    class VideoToVideoClient:
        generation_args = None

        @classmethod
        def from_env(cls):
            return cls()

        def assert_ready(self, timeout_seconds):
            return {"status": "healthy"}

        def generate_videos(self, **kwargs):
            type(self).generation_args = kwargs
            return {"status": "succeeded", "data": []}

    monkeypatch.setattr(nodes, "FlowAgentClient", VideoToVideoClient)
    monkeypatch.setattr(nodes, "_download_video_result", lambda *_args, **_kwargs: "ok")

    result = nodes.FlowOmniFlashVideo().generate(
        prompt="Restyle this clip as hand-drawn animation",
        mode="video to video",
        aspect_ratio="landscape",
        duration=8,
        count=1,
        resolution="720p",
        seed=43,
        video_model_override="",
        timeout_seconds=1200,
        source_video_media_id="source-video-id",
        reference_media_ids='["image-reference"]',
    )

    assert result == "ok"
    assert VideoToVideoClient.generation_args["start_media_id"] == "source-video-id"
    assert VideoToVideoClient.generation_args["is_video"] is True
    assert VideoToVideoClient.generation_args["ref_media_ids"] == ["image-reference"]


def test_video_to_video_accepts_native_comfy_video(monkeypatch, tmp_path):
    source_path = tmp_path / "loaded.mp4"
    source_path.write_bytes(b"video")

    class NativeVideo:
        def get_stream_source(self):
            return str(source_path)

        def get_active_trim_window(self):
            return 0.0, 0.0

    class NativeVideoClient:
        generation_args = None

        @classmethod
        def from_env(cls):
            return cls()

        def assert_ready(self, timeout_seconds):
            return {"status": "healthy"}

        def upload_file(self, path, timeout_seconds):
            assert path == str(source_path)
            return {"media_id": "uploaded-native-video"}

        def generate_videos(self, **kwargs):
            type(self).generation_args = kwargs
            return {"status": "succeeded", "data": []}

    monkeypatch.setattr(nodes, "FlowAgentClient", NativeVideoClient)
    monkeypatch.setattr(nodes, "video_without_audio", lambda path: nullcontext(path))
    monkeypatch.setattr(nodes, "_download_video_result", lambda *_args, **_kwargs: "ok")

    result = nodes.FlowOmniFlashVideo().generate(
        prompt="Restyle this clip",
        mode="video to video",
        aspect_ratio="landscape",
        duration=8,
        count=1,
        resolution="720p",
        seed=43,
        video_model_override="",
        timeout_seconds=1200,
        source_video=NativeVideo(),
    )

    assert result == "ok"
    assert NativeVideoClient.generation_args["start_media_id"] == "uploaded-native-video"


def test_upload_media_blocks_wrong_selected_socket_before_client(monkeypatch):
    class UnexpectedClient:
        @classmethod
        def from_env(cls):
            raise AssertionError("Client must not be created for an invalid media selection")

    monkeypatch.setattr(nodes, "FlowAgentClient", UnexpectedClient)

    with pytest.raises(nodes.FlowAgentError, match="media_type is image"):
        nodes.FlowUploadMedia().upload(
            media_type="image",
            timeout_seconds=600,
            video=object(),
        )


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
        return f"reference-{len(type(self).uploaded)}"

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
        "reference-1"
    ]
    assert "exclude_media_ids" not in FakeCharacterClient.generation_calls[0]
    assert (
        FakeCharacterClient.generation_calls[0]["idempotency_key"]
        != FakeCharacterClient.generation_calls[1]["idempotency_key"]
    )


def test_character_creator_labels_outfit_references_and_respects_aspect(monkeypatch, tmp_path):
    FakeCharacterClient.uploaded = []
    FakeCharacterClient.generation_calls = []
    monkeypatch.setattr(nodes, "FlowAgentClient", FakeCharacterClient)
    monkeypatch.setattr(nodes, "_comfy_output_directory", lambda: str(tmp_path))

    response = nodes.FlowCharacterCreator().generate_dataset(
        reference_image=torch.zeros((1, 4, 4, 3)),
        subject_description="A fashion model",
        shot_preset="body shots 8",
        shot_count=1,
        model="gem_pix_2",
        seed=43,
        retry_count=0,
        continue_on_error=False,
        timeout_per_image=600,
        preview_columns=1,
        dataset_name="Wardrobe Test",
        aspect_ratio="landscape (16:9)",
        top_reference=torch.zeros((2, 4, 4, 3)),
        bottom_reference=torch.zeros((1, 4, 4, 3)),
        accessories_reference=torch.zeros((1, 4, 4, 3)),
        shoes_reference=torch.zeros((1, 4, 4, 3)),
    )

    manifest = json.loads(response["result"][2])
    call = FakeCharacterClient.generation_calls[0]
    assert call["size"] == "1792x1024"
    assert call["ref_media_ids"] == [f"reference-{index}" for index in range(1, 7)]
    assert [item["role"] for item in manifest["references"]] == [
        "character",
        "top",
        "top",
        "bottom",
        "accessories",
        "shoes",
    ]
    assert "reference image 2 defines the exact top garment" in call["prompt"]
    assert "reference image 6 defines the exact shoes" in call["prompt"]
    assert manifest["requested_size"] == "1792x1024"


def test_character_selector_and_regenerator_use_stable_shot_identity(monkeypatch, tmp_path):
    FakeCharacterClient.uploaded = []
    FakeCharacterClient.generation_calls = []
    monkeypatch.setattr(nodes, "FlowAgentClient", FakeCharacterClient)
    monkeypatch.setattr(nodes, "_comfy_output_directory", lambda: str(tmp_path))
    monkeypatch.setattr(
        flow_character_library,
        "_characters_root",
        lambda: str(tmp_path / "characters"),
    )

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
    _, _, manifest_json, dataset_id, _, _ = created["result"]
    manifest = json.loads(manifest_json)
    assert manifest["manifest_path"].endswith("manifest.json")
    selected = flow_character_library.FlowCharacterShotSelector().select_saved_shot(
        selection_json=json.dumps(
            {"dataset_id": dataset_id, "shot_number": 2}
        ),
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
