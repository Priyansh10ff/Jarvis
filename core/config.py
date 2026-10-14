"""Load settings from config/settings.yaml, overlaid by config/settings.local.yaml."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
BASE_FILE = CONFIG_DIR / "settings.yaml"
LOCAL_FILE = CONFIG_DIR / "settings.local.yaml"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a mapping at the top level")
    return data


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


@dataclass(frozen=True)
class Settings:
    raw: dict[str, Any]

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    @property
    def assistant_name(self) -> str:
        return self.get("assistant.name", "Jarvis")

    @property
    def user_name(self) -> str:
        return self.get("user.name", "there")


def load_settings() -> Settings:
    return Settings(_merge(_read_yaml(BASE_FILE), _read_yaml(LOCAL_FILE)))
