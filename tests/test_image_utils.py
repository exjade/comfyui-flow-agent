from __future__ import annotations

import base64

import pytest
import torch
from PIL import Image

from comfyui_flow_agent_under_test.flow_agent_client import FlowAgentError
from comfyui_flow_agent_under_test.image_utils import (
    image_bytes_to_tensor,
    stack_image_tensors,
    tensor_batch_to_png_data_uris,
)


def test_tensor_png_round_trip_preserves_shape_and_range():
    source = torch.zeros((2, 4, 5, 3), dtype=torch.float32)
    source[0, :, :, 0] = 1.0
    source[1, :, :, 1] = 0.5

    uris = tensor_batch_to_png_data_uris(source)
    decoded = []
    for uri in uris:
        prefix, encoded = uri.split(",", 1)
        assert prefix == "data:image/png;base64"
        raw = base64.b64decode(encoded)
        assert Image.open(__import__("io").BytesIO(raw)).format == "PNG"
        decoded.append(image_bytes_to_tensor(raw))

    result = stack_image_tensors(decoded)
    assert tuple(result.shape) == (2, 4, 5, 3)
    assert float(result.min()) >= 0.0
    assert float(result.max()) <= 1.0
    assert torch.allclose(result[0, :, :, 0], torch.ones((4, 5)))


def test_reference_batch_limit_is_enforced():
    with pytest.raises(FlowAgentError, match="at most 10"):
        tensor_batch_to_png_data_uris(torch.zeros((11, 1, 1, 3)))


def test_mismatched_generated_sizes_fail_clearly():
    with pytest.raises(FlowAgentError, match="different dimensions"):
        stack_image_tensors(
            [torch.zeros((1, 4, 4, 3)), torch.zeros((1, 5, 4, 3))]
        )
