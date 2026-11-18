from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _merge(base: dict, override: dict) -> dict:
    return {
        **base,
        **{
            key: _merge(base[key], value) if isinstance(value, dict) and isinstance(base.get(key), dict) else value
            for key, value in override.items()
        },
    }


def load_config() -> dict[str, Any]:
    base = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    local_path = ROOT / "config.local.yaml"
    local = yaml.safe_load(local_path.read_text(encoding="utf-8")) if local_path.exists() else None
    return _merge(base, local or {})


def resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate
