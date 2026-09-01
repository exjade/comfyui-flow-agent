"""Small adapters for ComfyUI's native VIDEO datatype."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager

FLOW_EDIT_DURATIONS = (4, 6, 8, 10)


def flow_edit_duration(video=None, path=None, fallback=10):
    """Map a source clip's real duration to Flow's supported edit window, capped at 10s."""
    seconds = None
    get_duration = getattr(video, "get_duration", None)
    if callable(get_duration):
        try:
            seconds = float(get_duration())
        except (TypeError, ValueError, RuntimeError):
            seconds = None
    if seconds is None and path:
        try:
            import av

            with av.open(os.fspath(path), mode="r") as container:
                if container.duration is not None:
                    seconds = float(container.duration / av.time_base)
        except (ImportError, OSError, ValueError):
            seconds = None
    if seconds is None or seconds <= 0:
        return int(fallback)
    capped = min(seconds, float(FLOW_EDIT_DURATIONS[-1]))
    return next((duration for duration in FLOW_EDIT_DURATIONS if capped <= duration), 10)


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


def _find_ffmpeg():
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg

        executable = imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        executable = None
    if not executable or not os.path.isfile(executable):
        raise RuntimeError(
            "FFmpeg is required to remove source-video audio before sending it to Google Flow."
        )
    return executable


@contextmanager
def video_without_audio(path):
    """Yield a temporary video-only copy, leaving the user's source untouched."""
    descriptor, temporary_path = tempfile.mkstemp(prefix="flow_video_silent_", suffix=".mp4")
    os.close(descriptor)
    try:
        result = subprocess.run(
            [
                _find_ffmpeg(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                os.fspath(path),
                "-map",
                "0:v:0",
                "-c:v",
                "copy",
                "-an",
                temporary_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not os.path.isfile(temporary_path):
            detail = (result.stderr or "FFmpeg did not create the silent video.").strip()
            raise RuntimeError(f"Could not remove source-video audio: {detail}")
        yield temporary_path
    finally:
        try:
            os.remove(temporary_path)
        except FileNotFoundError:
            pass
