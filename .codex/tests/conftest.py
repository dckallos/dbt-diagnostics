from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]


def load_codex_script(name: str) -> ModuleType:
    path = ROOT / ".codex" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"codex_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
