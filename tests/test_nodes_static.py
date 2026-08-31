import ast
from pathlib import Path


def test_character_creator_does_not_use_removed_single_reference_variable():
    source_path = Path(__file__).resolve().parents[1] / "nodes.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    creator_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "FlowCharacterCreator"
    )
    generate_method = next(
        node
        for node in creator_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "generate_dataset"
    )
    loaded_names = {
        node.id
        for node in ast.walk(generate_method)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }

    assert "reference_media_id" not in loaded_names
    assert "reference_ids" in loaded_names


def test_video_preview_avoids_duplicate_native_preview():
    script_path = Path(__file__).resolve().parents[1] / "web" / "flow_video_preview.js"
    source = script_path.read_text(encoding="utf-8")

    assert "Array.isArray(message?.images)" in source
    assert "const items = message?.gifs;" in source


def test_video_model_override_no_longer_advertises_text_model_for_references():
    source_path = Path(__file__).resolve().parents[1] / "nodes.py"
    source = source_path.read_text(encoding="utf-8")

    assert "automatic model for the selected mode" in source
    assert "Blank = Omni Flash abra_t2v_<duration>s" not in source


def test_video_can_reuse_existing_flow_media_ids_without_uploading_pixels():
    source_path = Path(__file__).resolve().parents[1] / "nodes.py"
    source = source_path.read_text(encoding="utf-8")

    assert '"reference_media_ids": (' in source
    assert "direct_reference_ids = _parse_media_ids(reference_media_ids)" in source
    assert "direct_reference_ids + uploaded_reference_ids" in source


def test_omni_video_seed_is_permanently_fixed_to_43():
    source_path = Path(__file__).resolve().parents[1] / "nodes.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    omni_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "FlowOmniFlashVideo"
    )
    source = ast.get_source_segment(source_path.read_text(encoding="utf-8"), omni_class)

    assert '"seed": ("INT", {"default": 43, "min": 43, "max": 43' in source
    assert "seed=43" in source

    preview_source = (
        Path(__file__).resolve().parents[1] / "web" / "flow_video_preview.js"
    ).read_text(encoding="utf-8")
    assert "seedWidget.value = 43" in preview_source
    assert 'controlWidget.value = "fixed"' in preview_source


def test_omni_video_matches_flow_count_and_resolution_options():
    source_path = Path(__file__).resolve().parents[1] / "nodes.py"
    source_text = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    omni_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "FlowOmniFlashVideo"
    )
    omni_source = ast.get_source_segment(source_text, omni_class)

    assert 'VIDEO_RESOLUTIONS = ("360p", "720p", "1080p")' in source_text
    assert '"count": ("INT", {"default": 1, "min": 1, "max": 4' in omni_source


def test_video_preview_shows_dynamic_credit_estimate():
    script_path = Path(__file__).resolve().parents[1] / "web" / "flow_video_preview.js"
    source = script_path.read_text(encoding="utf-8")

    assert '"360p": { 4: 4, 6: 5, 8: 6, 10: 7 }' in source
    assert '"720p": { 4: 7, 6: 10, 8: 12, 10: 15 }' in source
    assert "Costo estimado de Flow" in source
    assert "upscale 1080p sin costo" in source
