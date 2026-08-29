from __future__ import annotations

import json

import torch

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
