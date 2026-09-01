import os

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
