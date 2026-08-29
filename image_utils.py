"""Conversions between ComfyUI IMAGE tensors and PNG bytes."""

from __future__ import annotations

import base64
import io
from typing import Iterable

import numpy as np
import torch
from PIL import Image, ImageOps, UnidentifiedImageError

from .flow_agent_client import FlowAgentError


def tensor_batch_to_png_data_uris(image, max_images: int = 10) -> list[str]:
    """Encode a ComfyUI [B,H,W,C] float tensor as PNG data URIs."""
    if hasattr(image, "detach"):
        array = image.detach().cpu().numpy()
    else:
        array = np.asarray(image)

    if array.ndim == 3:
        array = array[np.newaxis, ...]
    if array.ndim != 4:
        raise FlowAgentError(
            f"Reference IMAGE must have shape [B,H,W,C]; received {array.shape}."
        )
    if array.shape[0] > max_images:
        raise FlowAgentError(
            f"Flow Agent accepts at most {max_images} reference images; received {array.shape[0]}."
        )
    if array.shape[-1] not in {1, 3, 4}:
        raise FlowAgentError(
            f"Reference IMAGE must have 1, 3, or 4 channels; received {array.shape[-1]}."
        )

    data_uris: list[str] = []
    for frame in array:
        pixels = np.clip(np.rint(frame * 255.0), 0, 255).astype(np.uint8)
        if pixels.shape[-1] == 1:
            pixels = np.repeat(pixels, 3, axis=-1)
        mode = "RGBA" if pixels.shape[-1] == 4 else "RGB"
        buffer = io.BytesIO()
        Image.fromarray(pixels, mode=mode).save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        data_uris.append(f"data:image/png;base64,{encoded}")
    return data_uris


def image_bytes_to_tensor(data: bytes) -> torch.Tensor:
    """Decode one downloaded image to a ComfyUI [1,H,W,3] float tensor."""
    try:
        with Image.open(io.BytesIO(data)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            array = np.array(image, dtype=np.float32, copy=True) / 255.0
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise FlowAgentError(
            "Flow Agent returned bytes that Pillow could not decode as an image."
        ) from exc
    return torch.from_numpy(array).unsqueeze(0)


def stack_image_tensors(images: Iterable[torch.Tensor]) -> torch.Tensor:
    tensors = list(images)
    if not tensors:
        raise FlowAgentError("Flow Agent returned no decodable images.")
    shapes = {tuple(tensor.shape[1:]) for tensor in tensors}
    if len(shapes) != 1:
        raise FlowAgentError(
            "Generated images have different dimensions and cannot form one ComfyUI IMAGE batch: "
            f"{sorted(shapes)}. Generate them in separate executions."
        )
    return torch.cat(tensors, dim=0)
