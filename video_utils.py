"""Small adapters for ComfyUI's native VIDEO datatype."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager


@contextmanager
def video_input_path(video):
    """Yield a readable path for a native ComfyUI VIDEO and clean temporary exports."""
    if video is None:
        raise ValueError("A ComfyUI VIDEO input is required.")
    get_source = getattr(video, "get_stream_source", None)
    if not callable(get_source):
        raise TypeError("The connected value is not a native ComfyUI VIDEO object.")

    source = get_source()
    trim_window = getattr(video, "get_active_trim_window", lambda: (0.0, 0.0))()
    if isinstance(source, (str, os.PathLike)) and os.path.isfile(source):
        start_time, duration = trim_window
        if float(start_time or 0) == 0 and float(duration or 0) == 0:
            yield os.fspath(source)
            return

    descriptor, temporary_path = tempfile.mkstemp(prefix="flow_video_", suffix=".mp4")
    os.close(descriptor)
    try:
        save_to = getattr(video, "save_to", None)
        if not callable(save_to):
            raise TypeError("The connected VIDEO cannot be exported by this ComfyUI build.")
        save_to(temporary_path)
        yield temporary_path
    finally:
        try:
            os.remove(temporary_path)
        except FileNotFoundError:
            pass
