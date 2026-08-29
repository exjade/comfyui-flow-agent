"""Small, defensive HTTP client for the Flow Agent image API."""

from __future__ import annotations

import base64
import binascii
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class FlowAgentError(RuntimeError):
    """Base error shown by ComfyUI for this integration."""


class FlowAgentConfigurationError(FlowAgentError):
    """Raised when the RunPod-side configuration is missing or unsafe."""


class FlowAgentHTTPError(FlowAgentError):
    """Raised for transport failures and non-success HTTP responses."""


@dataclass(frozen=True)
class FlowAgentConfig:
    base_url: str
    api_key: str
    connect_timeout: float = 10.0
    max_download_bytes: int = 64 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "FlowAgentConfig":
        raw_base_url = os.environ.get("FLOW_AGENT_BASE_URL", "").strip()
        if not raw_base_url:
            raise FlowAgentConfigurationError(
                "FLOW_AGENT_BASE_URL is not configured. Set it to the HTTPS ngrok URL "
                "before starting ComfyUI."
            )

        base_url = _normalise_base_url(raw_base_url)
        api_key = os.environ.get("FLOW_AGENT_API_KEY", "").strip()
        hostname = (urlparse(base_url).hostname or "").lower()
        is_local = hostname in {"localhost", "127.0.0.1", "::1"}
        if not api_key and not is_local:
            raise FlowAgentConfigurationError(
                "FLOW_AGENT_API_KEY is required for a non-local Flow Agent URL. "
                "Use the same value as SERVER_API_KEY on the PC running Flow Agent."
            )

        connect_timeout = _positive_float_env(
            "FLOW_AGENT_CONNECT_TIMEOUT_SECONDS", default=10.0
        )
        max_download_mb = _positive_float_env(
            "FLOW_AGENT_MAX_DOWNLOAD_MB", default=64.0
        )
        return cls(
            base_url=base_url,
            api_key=api_key,
            connect_timeout=connect_timeout,
            max_download_bytes=int(max_download_mb * 1024 * 1024),
        )


def _positive_float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise FlowAgentConfigurationError(f"{name} must be a number.") from exc
    if value <= 0:
        raise FlowAgentConfigurationError(f"{name} must be greater than zero.")
    return value


def _normalise_base_url(value: str) -> str:
    candidate = value.rstrip("/")
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise FlowAgentConfigurationError(
            "FLOW_AGENT_BASE_URL must be a complete http:// or https:// URL."
        )
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise FlowAgentConfigurationError(
            "FLOW_AGENT_BASE_URL must contain only the origin, without a path, query, or fragment."
        )
    return candidate


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlparse(url)
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80 if parsed.scheme == "http" else None
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), port


class FlowAgentClient:
    """Client matching Flow Agent revision 206285a's image/media contracts."""

    TRANSIENT_STATUS_CODES = {429, 502, 503, 504}

    def __init__(
        self,
        config: FlowAgentConfig,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        if session is None:
            retry = Retry(
                total=3,
                connect=3,
                read=3,
                status=3,
                backoff_factor=0.5,
                status_forcelist=(429, 502, 503, 504),
                allowed_methods=frozenset({"GET"}),
                respect_retry_after_header=True,
            )
            adapter = HTTPAdapter(max_retries=retry)
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)

    @classmethod
    def from_env(cls) -> "FlowAgentClient":
        return cls(FlowAgentConfig.from_env())

    def _absolute_url(self, path_or_url: str) -> str:
        parsed = urlparse(path_or_url)
        if parsed.scheme:
            if parsed.scheme not in {"http", "https"}:
                raise FlowAgentHTTPError(f"Unsupported media URL scheme: {parsed.scheme}")
            return path_or_url
        return urljoin(f"{self.config.base_url}/", path_or_url.lstrip("/"))

    def _headers(self, url: str, *, json_response: bool = True) -> dict[str, str]:
        headers = {
            "User-Agent": "comfyui-flow-agent/1.0",
            "ngrok-skip-browser-warning": "comfyui-flow-agent",
            "Accept": "application/json" if json_response else "image/*,application/octet-stream",
        }
        # Never leak the Flow Agent bearer token to a fallback Google/R2 URL.
        if self.config.api_key and _origin(url) == _origin(self.config.base_url):
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def health(self, timeout_seconds: float = 15.0) -> dict[str, Any]:
        payload = self._request_json(
            "GET", "/health", timeout_seconds=timeout_seconds
        )
        if not isinstance(payload, dict):
            raise FlowAgentHTTPError("GET /health returned a non-object JSON response.")
        return payload

    def assert_ready(self, timeout_seconds: float = 15.0) -> dict[str, Any]:
        health = self.health(timeout_seconds=timeout_seconds)
        if (
            health.get("status") != "healthy"
            or health.get("extension_connected") is not True
            or health.get("has_flow_key") is not True
        ):
            raise FlowAgentHTTPError(
                "Flow Agent is reachable but not ready: "
                f"status={health.get('status')!r}, "
                f"extension_connected={health.get('extension_connected')!r}, "
                f"has_flow_key={health.get('has_flow_key')!r}, "
                f"transport={health.get('transport')!r}."
            )
        return health

    def list_models(self, timeout_seconds: float = 15.0) -> list[str]:
        payload = self._request_json(
            "GET", "/v1/models", timeout_seconds=timeout_seconds
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise FlowAgentHTTPError("GET /v1/models did not return a data array.")
        return [item["id"] for item in data if isinstance(item, dict) and item.get("id")]

    def upload_image(self, png_data_uri: str, timeout_seconds: float) -> str:
        # /v1/upload has no idempotency contract, so it is deliberately not retried.
        payload = self._request_json(
            "POST",
            "/v1/upload",
            json_body={"image_base64": png_data_uri},
            timeout_seconds=timeout_seconds,
        )
        media_id = payload.get("media_id") if isinstance(payload, dict) else None
        if not isinstance(media_id, str) or not media_id.strip():
            raise FlowAgentHTTPError("POST /v1/upload did not return a non-empty media_id.")
        return media_id

    def generate_images(
        self,
        *,
        prompt: str,
        model: str,
        size: str,
        count: int,
        seed: int,
        ref_media_ids: Iterable[str] = (),
        timeout_seconds: float,
        idempotency_key: str | None = None,
    ) -> list[dict[str, Any]]:
        refs = [value for value in ref_media_ids if value]
        body: dict[str, Any] = {
            "prompt": prompt,
            "model": model,
            "n": count,
            "size": size,
            "response_format": "url",
            "seed": seed,
        }
        if refs:
            body["ref_media_ids"] = refs

        key = idempotency_key or f"comfyui-{uuid.uuid4()}"
        payload = self._post_generation_with_replay(
            body=body,
            idempotency_key=key,
            timeout_seconds=timeout_seconds,
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list) or not data:
            raise FlowAgentHTTPError(
                "POST /v1/images/generations returned no generated images."
            )
        for index, item in enumerate(data):
            if not isinstance(item, dict) or not (item.get("url") or item.get("b64_json")):
                raise FlowAgentHTTPError(
                    f"Generated image item {index} has neither url nor b64_json."
                )
        return data

    def _post_generation_with_replay(
        self,
        *,
        body: dict[str, Any],
        idempotency_key: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        attempt = 0
        last_error: Exception | None = None

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FlowAgentHTTPError(
                    "Flow image generation exceeded the total timeout. The same request was "
                    f"protected with Idempotency-Key {idempotency_key!r}; increase timeout_seconds "
                    "and retry if needed."
                ) from last_error

            attempt += 1
            per_attempt_timeout = min(180.0, remaining)
            try:
                return self._request_json(
                    "POST",
                    "/v1/images/generations",
                    json_body=body,
                    timeout_seconds=per_attempt_timeout,
                    extra_headers={"Idempotency-Key": idempotency_key},
                )
            except FlowAgentHTTPError as exc:
                last_error = exc
                status = getattr(exc, "status_code", None)
                processing = status == 409 and "already processing" in str(exc).lower()
                if status not in self.TRANSIENT_STATUS_CODES and not processing:
                    raise
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                continue
            time.sleep(min(10.0, max(1.0, 2 ** min(attempt - 1, 3)), remaining))

    def download_generated_image(
        self, item: dict[str, Any], timeout_seconds: float = 120.0
    ) -> bytes:
        inline = item.get("b64_json")
        if inline:
            try:
                return base64.b64decode(inline, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise FlowAgentHTTPError("Generated b64_json is invalid base64.") from exc

        raw_url = item.get("url")
        if not isinstance(raw_url, str) or not raw_url:
            raise FlowAgentHTTPError("Generated image response is missing its URL.")
        url = self._absolute_url(raw_url)
        try:
            response = self.session.get(
                url,
                headers=self._headers(url, json_response=False),
                timeout=(self.config.connect_timeout, timeout_seconds),
                stream=True,
            )
        except requests.RequestException as exc:
            raise FlowAgentHTTPError(f"Image download failed: {exc}") from exc
        if not response.ok:
            raise self._http_error(response, "GET", url)

        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > self.config.max_download_bytes:
                    raise FlowAgentHTTPError(
                        "Generated image exceeds FLOW_AGENT_MAX_DOWNLOAD_MB."
                    )
            except ValueError:
                pass

        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > self.config.max_download_bytes:
                raise FlowAgentHTTPError(
                    "Generated image exceeds FLOW_AGENT_MAX_DOWNLOAD_MB."
                )
            chunks.append(chunk)
        if total == 0:
            raise FlowAgentHTTPError("Generated image download returned an empty body.")
        return b"".join(chunks)

    def _request_json(
        self,
        method: str,
        path_or_url: str,
        *,
        json_body: dict[str, Any] | None = None,
        timeout_seconds: float,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        url = self._absolute_url(path_or_url)
        headers = self._headers(url)
        if extra_headers:
            headers.update(extra_headers)
        try:
            response = self.session.request(
                method,
                url,
                headers=headers,
                json=json_body,
                timeout=(self.config.connect_timeout, timeout_seconds),
            )
        except (requests.Timeout, requests.ConnectionError):
            # Generation retries need the concrete requests exception type.
            raise
        except requests.RequestException as exc:
            raise FlowAgentHTTPError(f"{method} {url} failed: {exc}") from exc
        if not response.ok:
            raise self._http_error(response, method, url)
        try:
            return response.json()
        except ValueError as exc:
            preview = response.text[:300].replace("\n", " ")
            raise FlowAgentHTTPError(
                f"{method} {url} returned non-JSON content: {preview!r}. "
                "If this is an ngrok warning page, verify the tunnel URL."
            ) from exc

    @staticmethod
    def _http_error(response: requests.Response, method: str, url: str) -> FlowAgentHTTPError:
        detail: Any = None
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = payload.get("detail")
                if detail is None and isinstance(payload.get("error"), dict):
                    detail = payload["error"].get("message")
        except ValueError:
            detail = None
        if detail is None:
            detail = response.text[:500].replace("\n", " ") or response.reason
        error = FlowAgentHTTPError(
            f"{method} {url} returned HTTP {response.status_code}: {detail}"
        )
        error.status_code = response.status_code  # type: ignore[attr-defined]
        return error
