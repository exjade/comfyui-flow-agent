import json
from pathlib import Path

import pytest
from PIL import Image

pytest.importorskip("torch")

from comfyui_flow_agent_under_test import flow_character_library as library


def _write_png(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (3, 2), (20, 40, 60)).save(path, format="PNG")


def test_saved_character_library_scans_and_selects_without_flow(monkeypatch, tmp_path):
    root = tmp_path / "characters"
    dataset = root / "character_one"
    image_path = dataset / "001_face_front.png"
    _write_png(image_path)
    manifest = {
        "version": 1,
        "dataset_id": "character_one",
        "subject_description": "Saved character",
        "model": "gem_pix_2",
        "aspect_ratio": "square (1:1)",
        "references": [{"media_id": "reference-1", "role": "identity"}],
        "shots": [
            {
                "status": "succeeded",
                "shot_number": 1,
                "shot_id": "face_front",
                "media_id": "generated-1",
                "full_prompt": "front portrait",
                "saved_path": str(image_path),
                "preview": {
                    "filename": image_path.name,
                    "subfolder": "flow_agent/characters/character_one",
                    "type": "output",
                },
            }
        ],
    }
    dataset.mkdir(parents=True, exist_ok=True)
    (dataset / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(library, "_characters_root", lambda: str(root))

    datasets = library.scan_character_datasets()
    assert datasets[0]["dataset_id"] == "character_one"
    assert datasets[0]["shot_count"] == 1

    selected = library.FlowCharacterShotSelector().select_saved_shot(
        json.dumps({"dataset_id": "character_one", "shot_number": 1})
    )
    image, spec_json, shot_id, media_id, prompt = selected["result"]
    spec = json.loads(spec_json)
    assert tuple(image.shape) == (1, 2, 3, 3)
    assert shot_id == "face_front"
    assert media_id == "generated-1"
    assert prompt == "front portrait"
    assert spec["references"][0]["media_id"] == "reference-1"


def test_character_library_frontend_has_visual_dataset_and_shot_pickers():
    source = (
        Path(__file__).resolve().parents[1] / "web" / "flow_character_library.js"
    ).read_text(encoding="utf-8")
    assert "Refresh datasets" in source
    assert "/flow-agent/character-library" in source
    assert "datasetPicker" in source
    assert "shotPicker" in source
