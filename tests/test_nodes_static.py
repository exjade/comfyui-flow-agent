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
