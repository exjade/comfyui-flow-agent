import os

from comfyui_flow_agent_under_test import video_utils
from comfyui_flow_agent_under_test.video_utils import video_input_path


class FileVideo:
    def __init__(self, path):
        self.path = str(path)

    def get_stream_source(self):
        return self.path

    def get_active_trim_window(self):
        return 0.0, 0.0


class ExportedVideo:
    def get_stream_source(self):
        return object()

    def save_to(self, path):
        with open(path, "wb") as handle:
            handle.write(b"video")


def test_video_input_path_reuses_untrimmed_file(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")

    with video_input_path(FileVideo(source)) as path:
        assert path == str(source)

    assert source.exists()


def test_video_input_path_cleans_temporary_export():
    with video_input_path(ExportedVideo()) as path:
        assert os.path.isfile(path)
        temporary_path = path

    assert not os.path.exists(temporary_path)


def test_video_without_audio_uses_temporary_copy_and_cleans_it(monkeypatch, tmp_path):
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"source")

    def fake_run(command, **_kwargs):
        assert "-an" in command
        assert command[command.index("-i") + 1] == str(source_path)
        output_path = command[-1]
        with open(output_path, "wb") as handle:
            handle.write(b"silent")
        return type("Result", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr(video_utils, "_find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(video_utils.subprocess, "run", fake_run)

    with video_utils.video_without_audio(source_path) as silent_path:
        assert silent_path != str(source_path)
        assert os.path.exists(silent_path)
        with open(silent_path, "rb") as handle:
            assert handle.read() == b"silent"
    assert source_path.read_bytes() == b"source"
    assert not os.path.exists(silent_path)
