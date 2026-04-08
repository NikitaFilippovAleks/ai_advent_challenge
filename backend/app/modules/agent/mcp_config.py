"""Управление конфигурацией MCP-серверов.

Конфигурация хранится в JSON-файле data/mcp_servers.json.
"""

import json
from pathlib import Path

# Путь к конфигу относительно корня backend/
_CONFIG_PATH = Path(__file__).resolve().parents[3] / "data" / "mcp_servers.json"


def load_config() -> dict:
    """Загружает конфигурацию MCP-серверов из JSON-файла."""
    if not _CONFIG_PATH.exists():
        return {"servers": {}}
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict) -> None:
    """Сохраняет конфигурацию MCP-серверов в JSON-файл."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")
