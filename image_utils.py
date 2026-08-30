"""Conversions between ComfyUI IMAGE tensors and PNG bytes."""

from __future__ import annotations

import base64
import io
import math
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


def make_contact_sheet(
    image_batch,
    columns: int = 4,
    padding: int = 8,
    max_tile_size: int = 256,
) -> torch.Tensor:
    """Arrange a ComfyUI IMAGE batch into one preview-friendly contact sheet."""
    if hasattr(image_batch, "detach"):
        batch = image_batch.detach().cpu()
    else:
        batch = torch.as_tensor(image_batch)
    if batch.ndim == 3:
        batch = batch.unsqueeze(0)
    if batch.ndim != 4 or batch.shape[0] < 1:
        raise FlowAgentError(
            f"Contact sheet requires a non-empty [B,H,W,C] IMAGE batch; received {tuple(batch.shape)}."
        )
    _, height, width, _ = batch.shape
    longest_side = max(int(height), int(width))
    if longest_side > max_tile_size:
        scale = max_tile_size / longest_side
        target_height = max(1, round(int(height) * scale))
        target_width = max(1, round(int(width) * scale))
        batch = torch.nn.functional.interpolate(
            batch.permute(0, 3, 1, 2),
            size=(target_height, target_width),
            mode="bilinear",
            align_corners=False,
        ).permute(0, 2, 3, 1)
    columns = max(1, min(int(columns), int(batch.shape[0])))
    rows = math.ceil(int(batch.shape[0]) / columns)
    _, height, width, channels = batch.shape
    sheet_height = rows * height + (rows + 1) * padding
    sheet_width = columns * width + (columns + 1) * padding
    sheet = torch.full(
        (1, sheet_height, sheet_width, channels),
        0.08,
        dtype=batch.dtype,
    )
    for index, image in enumerate(batch):
        row, column = divmod(index, columns)
        top = padding + row * (height + padding)
        left = padding + column * (width + padding)
        sheet[0, top : top + height, left : left + width, :] = image
    return sheet
