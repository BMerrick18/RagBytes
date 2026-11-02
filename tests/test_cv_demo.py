import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build_cv_demo.py"


def _load():
    spec = importlib.util.spec_from_file_location("build_cv_demo", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_home_page_demo_matches_the_chunkers():
    module = _load()
    expected = module.render(module.build_demo())
    assert module.OUTPUT.read_text(encoding="utf-8") == expected, "Run python scripts/build_cv_demo.py"
