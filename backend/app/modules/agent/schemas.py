"""Pydantic-схемы для MCP API."""

from pydantic import BaseModel


class AddServerRequest(BaseModel):
    """Запрос на добавление MCP-сервера."""

    name: str
    command: str
    args: list[str] = []


class MCPServerStatus(BaseModel):
    """Статус MCP-сервера."""

    name: str
    command: str
    args: list[str]
    enabled: bool
    connected: bool
    tool_count: int


class MCPToolInfo(BaseModel):
    """Информация об инструменте MCP."""

    server: str
    name: str
    description: str
