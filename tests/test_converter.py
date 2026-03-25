from pathlib import Path

from sb3_to_python.converter import ScratchToPythonConverter


def test_sanitize_name_unique():
    c = ScratchToPythonConverter({"targets": [{"blocks": {}, "variables": {}, "lists": {}}]})
    assert c.sanitize_name("my var") == "my_var"
    assert c.sanitize_name("my var") == "my_var_2"


def test_convert_project_smoke(tmp_path: Path):
    loaded = ScratchToPythonConverter.load_sb3(Path(__file__).resolve().parents[1] / "word.sb3")
    converter = ScratchToPythonConverter(loaded.project_json)
    out = converter.convert_project()
    assert "Auto-generated from a Scratch/PenguinMod .sb3 project" in out
    assert "if __name__ == '__main__':" in out
