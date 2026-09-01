import ast
from pathlib import Path


def test_standalone_upscale_node_is_not_registered_or_implemented():
    root = Path(__file__).resolve().parents[1]
    registration = (root / "__init__.py").read_text(encoding="utf-8")
    nodes = (root / "nodes.py").read_text(encoding="utf-8")

    assert "FlowVideoUpsample" not in registration
    assert "class FlowVideoUpsample" not in nodes
    assert '"FlowVideoLibrary": "Flow / Video Library"' in registration


def test_character_single_shot_workflow_has_numbered_end_user_names():
    root = Path(__file__).resolve().parents[1]
    registration = (root / "__init__.py").read_text(encoding="utf-8")
    nodes = (root / "nodes.py").read_text(encoding="utf-8")
    library = (root / "flow_character_library.py").read_text(encoding="utf-8")

    assert '"FlowCharacterShotSelector": "Flow / 1. Choose Character Shot"' in registration
    assert '"FlowGenerateCharacterShot": "Flow / 2. Regenerate Chosen Shot"' in registration
    assert "This node never sends a request to Google Flow" in library
    assert "does not edit the old image pixels or media_id" in nodes


def test_character_library_is_independent_from_creator_outputs():
    root = Path(__file__).resolve().parents[1]
    library = (root / "flow_character_library.py").read_text(encoding="utf-8")

    assert '"selection_json": ("STRING"' in library
    assert '"images": ("IMAGE",)' not in library
    assert '"manifest_json": ("STRING"' not in library
    assert "/flow-agent/character-library" in library


def test_character_creator_is_cached_and_uses_a_stable_seed():
    root = Path(__file__).resolve().parents[1]
    source_path = root / "nodes.py"
    source_text = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    creator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "FlowCharacterCreator"
    )
    creator_source = ast.get_source_segment(source_text, creator)

    assert "def IS_CHANGED" not in creator_source
    assert '"seed": ("INT", {"default": 43, "min": 43, "max": 43' in creator_source
    assert "seed=43" in creator_source


def test_nano_banana_seed_is_permanently_fixed_to_43():
    root = Path(__file__).resolve().parents[1]
    source_path = root / "nodes.py"
    source_text = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    nano = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "FlowNanoBanana"
    )
    nano_source = ast.get_source_segment(source_text, nano)

    assert '"seed": ("INT", {"default": 43, "min": 43, "max": 43' in nano_source
    assert "seed=43" in nano_source

    fixed_seed_source = (root / "web" / "flow_fixed_seed.js").read_text(
        encoding="utf-8"
    )
    assert '"FlowNanoBanana"' in fixed_seed_source
    assert "seedWidget.value = 43" in fixed_seed_source
    assert 'controlWidget.value = "fixed"' in fixed_seed_source


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
    assert "direct_reference_ids" in source
    assert "uploaded_reference_ids" in source
    assert "direct_video_reference_ids" in source
    assert "uploaded_video_reference_ids" in source


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

    assert 'VIDEO_RESOLUTIONS = ("720p", "1080p")' in source_text
    assert '"count": ("INT", {"default": 1, "min": 1, "max": 4' in omni_source


def test_video_preview_shows_dynamic_credit_estimate():
    script_path = Path(__file__).resolve().parents[1] / "web" / "flow_video_preview.js"
    source = script_path.read_text(encoding="utf-8")

    assert '"720p": { 4: 7, 6: 10, 8: 12, 10: 15 }' in source
    assert '"360p":' not in source
    assert "Estimated Flow cost" in source
    assert "free 1080p upscale" in source
    assert "Costo estimado de Flow" not in source


def test_omni_video_mode_ui_exposes_only_relevant_inputs():
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "web" / "flow_video_mode.js"
    ).read_text(encoding="utf-8")
    preview = (root / "web" / "flow_video_preview.js").read_text(encoding="utf-8")
    labels = (root / "web" / "flow_ui_label.js").read_text(encoding="utf-8")

    assert '"text to video": []' in source
    assert '"first + last frame": ["start_image", "end_image"]' in source
    assert '"reference_video_media_ids"' in source
    assert '"reference_video_paths"' in source
    assert '"reference_video"' in source
    assert '"source_video"' in source
    assert 'count fixed to 1' in source

    edit_inputs = source.split('"edit source video": [', 1)[1].split("],", 1)[0]
    video_to_video_inputs = source.split('"video to video": [', 1)[1].split("],", 1)[0]
    assert '"source_video"' in edit_inputs
    assert '"reference_images"' not in edit_inputs
    assert '"reference_video"' not in edit_inputs
    assert '"reference_images"' in video_to_video_inputs
    assert '"reference_video"' not in video_to_video_inputs
    assert "addDOMWidget" not in source
    assert "addDOMWidget" not in preview.split("function createPreview", 1)[0]
    assert "addCustomWidget(widget)" in labels
    assert "return [width, 28]" in labels


def test_upload_media_ui_switches_between_image_and_video():
    root = Path(__file__).resolve().parents[1]
    backend = (root / "nodes.py").read_text(encoding="utf-8")
    frontend = (root / "web" / "flow_upload_media.js").read_text(encoding="utf-8")

    assert '"media_type": (("image", "video")' in backend
    assert '"video": ("VIDEO",)' in backend
    assert 'input.name === "image" || input.name === "video"' in frontend
    assert 'image input disabled' in frontend
    assert 'video input disabled' in frontend


def test_character_status_displays_and_copies_failed_shot_error():
    script_path = Path(__file__).resolve().parents[1] / "web" / "flow_character_status.js"
    source = script_path.read_text(encoding="utf-8")

    assert 'mediaId.textContent = failed ? "ERROR"' in source
    assert "error.textContent = record.error" in source
    assert '(record.error || `${record.shot_id || ""}\\tfailed`)' in source


def test_video_library_is_a_separate_visual_module():
    root = Path(__file__).resolve().parents[1]
    backend = (root / "flow_video_library.py").read_text(encoding="utf-8")
    frontend = (root / "web" / "flow_video_library.js").read_text(encoding="utf-8")
    registration = (root / "__init__.py").read_text(encoding="utf-8")

    assert "class FlowVideoLibrary" in backend
    assert '"/flow-agent/video-library"' in backend
    assert 'name: "comfyui-flow-agent.video-library"' in frontend
    assert 'refresh.textContent = "Refresh videos"' in frontend
    assert '"FlowVideoLibrary": FlowVideoLibrary' in registration
