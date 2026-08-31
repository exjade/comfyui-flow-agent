from __future__ import annotations

import base64
import json

import pytest
import requests

from comfyui_flow_agent_under_test.flow_agent_client import (
    FlowAgentClient,
    FlowAgentConfig,
    FlowAgentConfigurationError,
    FlowAgentHTTPError,
)


class FakeResponse:
    def __init__(self, status=200, payload=None, content=b"", headers=None):
        self.status_code = status
        self._payload = payload
        self._content = content
        self.headers = headers or {}
        self.reason = "fake"
        self.ok = 200 <= status < 300
        self.text = json.dumps(payload) if payload is not None else content.decode("utf-8", "replace")

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload

    def iter_content(self, chunk_size):
        yield self._content


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def config():
    return FlowAgentConfig(
        base_url="https://unit-test.ngrok-free.app",
        api_key="top-secret",
    )


def test_remote_env_requires_api_key(monkeypatch):
    monkeypatch.setenv("FLOW_AGENT_BASE_URL", "https://example.ngrok-free.app")
    monkeypatch.delenv("FLOW_AGENT_API_KEY", raising=False)
    with pytest.raises(FlowAgentConfigurationError, match="required"):
        FlowAgentConfig.from_env()


def test_local_installer_configuration_is_discovered_without_process_env(
    monkeypatch, tmp_path
):
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / ".env").write_text("SERVER_API_KEY=local-secret\n", encoding="utf-8")
    data_dir = tmp_path / "ComfyUIFlowAgent"
    data_dir.mkdir()
    (data_dir / "flow-local.config.json").write_text(
        '{"flow_agent_dir": "' + str(agent_dir).replace("\\", "\\\\") + '", "port": 8001}',
        encoding="utf-8",
    )
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("FLOW_AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("FLOW_AGENT_API_KEY", raising=False)

    discovered = FlowAgentConfig.from_env()

    assert discovered.base_url == "http://127.0.0.1:8001"
    assert discovered.api_key == "local-secret"


def test_unresolved_runpod_secret_reference_is_rejected(monkeypatch):
    monkeypatch.setenv("FLOW_AGENT_BASE_URL", "https://example.ngrok-free.app")
    monkeypatch.setenv(
        "FLOW_AGENT_API_KEY", "{{ RUNPOD_SECRET_flow_agent_api_key }}"
    )
    with pytest.raises(
        FlowAgentConfigurationError, match="unresolved RunPod secret reference"
    ):
        FlowAgentConfig.from_env()


def test_health_contract_and_bearer_header():
    session = FakeSession(
        [FakeResponse(payload={"status": "healthy", "extension_connected": True, "has_flow_key": True, "transport": "http"})]
    )
    client = FlowAgentClient(config(), session=session)
    health = client.assert_ready()
    assert health["transport"] == "http"
    headers = session.calls[0][2]["headers"]
    assert headers["Authorization"] == "Bearer top-secret"
    assert headers["ngrok-skip-browser-warning"] == "comfyui-flow-agent"


def test_upload_uses_real_json_field_and_reads_media_id():
    session = FakeSession([FakeResponse(payload={"media_id": "uploaded-123", "url": "https://x/download/a.png"})])
    client = FlowAgentClient(config(), session=session)
    result = client.upload_image("data:image/png;base64,AAAA", timeout_seconds=30)
    assert result == "uploaded-123"
    assert session.calls[0][2]["json"] == {"image_base64": "data:image/png;base64,AAAA"}


def test_generation_payload_matches_repo_contract():
    session = FakeSession([FakeResponse(payload={"created": 1, "data": [{"url": "/download/a.png", "media_id": "m1"}]})])
    client = FlowAgentClient(config(), session=session)
    items = client.generate_images(
        prompt="hello",
        model="narwhal",
        size="1792x1024",
        count=2,
        seed=7,
        ref_media_ids=["ref-1"],
        timeout_seconds=30,
        idempotency_key="stable-key",
    )
    assert items[0]["media_id"] == "m1"
    call = session.calls[0]
    assert call[2]["json"] == {
        "prompt": "hello",
        "model": "narwhal",
        "n": 2,
        "size": "1792x1024",
        "response_format": "url",
        "seed": 7,
        "ref_media_ids": ["ref-1"],
    }
    assert call[2]["headers"]["Idempotency-Key"] == "stable-key"


def test_image_count_strictly_caps_extra_gem_pix_candidates():
    session = FakeSession(
        [
            FakeResponse(
                payload={
                    "data": [
                        {"url": "/download/1.png"},
                        {"url": "/download/2.png"},
                        {"url": "/download/3.png"},
                    ]
                }
            )
        ]
    )
    client = FlowAgentClient(config(), session=session)
    items = client.generate_images(
        prompt="one image",
        model="gem_pix_2",
        size="1024x1024",
        count=1,
        seed=1,
        timeout_seconds=30,
    )
    assert len(items) == 1


def test_video_payload_and_processing_job_poll(monkeypatch):
    session = FakeSession(
        [
            FakeResponse(
                status=202,
                payload={"job_id": "video-1", "status": "processing", "data": []},
            ),
            FakeResponse(
                payload={
                    "job_id": "video-1",
                    "status": "succeeded",
                    "data": [
                        {
                            "url": "/download/video.mp4",
                            "media_id": "video-media-1",
                            "resolution": "720p",
                        }
                    ],
                }
            ),
        ]
    )
    monkeypatch.setattr(
        "comfyui_flow_agent_under_test.flow_agent_client.time.sleep",
        lambda _seconds: None,
    )
    client = FlowAgentClient(config(), session=session)
    result = client.generate_videos(
        prompt="moving camera",
        aspect="landscape",
        count=1,
        duration=8,
        seed=42,
        resolution="720p",
        start_media_id="start-1",
        ref_media_ids=["ingredient-1"],
        video_model=None,
        timeout_seconds=30,
        idempotency_key="video-key",
    )
    assert result["status"] == "succeeded"
    assert session.calls[0][2]["json"] == {
        "prompt": "moving camera",
        "aspect": "landscape",
        "n": 1,
        "duration": 8,
        "seed": 42,
        "resolution": "720p",
        "ref_media_ids": ["ingredient-1"],
        "start_media_id": "start-1",
    }
    assert session.calls[1][1].endswith("/v1/videos/generations/video-1")


def test_generation_retry_reuses_the_same_idempotency_key(monkeypatch):
    session = FakeSession(
        [
            requests.Timeout("tunnel stalled"),
            FakeResponse(payload={"created": 1, "data": [{"url": "/download/a.png"}]}),
        ]
    )
    monkeypatch.setattr("comfyui_flow_agent_under_test.flow_agent_client.time.sleep", lambda _seconds: None)
    client = FlowAgentClient(config(), session=session)
    client.generate_images(
        prompt="safe retry",
        model="narwhal",
        size="1024x1024",
        count=1,
        seed=9,
        timeout_seconds=30,
        idempotency_key="one-key",
    )
    assert len(session.calls) == 2
    assert {
        call[2]["headers"]["Idempotency-Key"] for call in session.calls
    } == {"one-key"}


def test_external_media_download_never_receives_bearer_token():
    session = FakeSession([FakeResponse(content=b"png bytes")])
    client = FlowAgentClient(config(), session=session)
    assert client.download_generated_image({"url": "https://googleusercontent.example/signed"}) == b"png bytes"
    headers = session.calls[0][2]["headers"]
    assert "Authorization" not in headers


def test_inline_b64_json_is_supported_defensively():
    client = FlowAgentClient(config(), session=FakeSession([]))
    raw = b"image bytes"
    assert client.download_generated_image({"b64_json": base64.b64encode(raw).decode()}) == raw


def test_fastapi_detail_is_exposed_without_secret():
    session = FakeSession([FakeResponse(status=401, payload={"detail": "Invalid or missing API key"})])
    client = FlowAgentClient(config(), session=session)
    with pytest.raises(FlowAgentHTTPError) as raised:
        client.list_models()
    assert "HTTP 401" in str(raised.value)
    assert "top-secret" not in str(raised.value)
