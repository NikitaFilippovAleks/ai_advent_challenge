"""Менеджер MCP-серверов — управляет жизненным циклом подключений.

Запускает MCP-серверы как subprocess через stdio-транспорт,
кеширует сессии и инструменты, маршрутизирует вызовы.
"""

import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.modules.agent.mcp_config import load_config, save_config

logger = logging.getLogger(__name__)


@dataclass
class MCPConnection:
    """Активное подключение к MCP-серверу."""

    session: ClientSession
    exit_stack: AsyncExitStack
    tools: list[dict] = field(default_factory=list)


class MCPManager:
    """Управляет подключениями к MCP-серверам."""

    def __init__(self) -> None:
        self._connections: dict[str, MCPConnection] = {}
        # Индекс: имя_инструмента → имя_сервера (для маршрутизации вызовов)
        self._tool_index: dict[str, str] = {}

    async def connect(self, name: str) -> list[dict]:
        """Подключается к MCP-серверу по имени из конфига.

        Returns:
            список инструментов сервера
        """
        if name in self._connections:
            logger.info("Сервер '%s' уже подключён", name)
            return self._connections[name].tools

        config = load_config()
        server_cfg = config.get("servers", {}).get(name)
        if not server_cfg:
            raise ValueError(f"Сервер '{name}' не найден в конфигурации")

        server_params = StdioServerParameters(
            command=server_cfg["command"],
            args=server_cfg.get("args", []),
            env=server_cfg.get("env"),
        )

        exit_stack = AsyncExitStack()
        try:
            # Запускаем subprocess и получаем stdio-транспорт
            stdio_transport = await exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            read_stream, write_stream = stdio_transport

            # Создаём MCP-сессию и выполняем handshake
            session = await exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()

            # Получаем список инструментов
            response = await session.list_tools()
            tools = [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": tool.inputSchema or {},
                }
                for tool in response.tools
            ]

            # Сохраняем подключение
            conn = MCPConnection(session=session, exit_stack=exit_stack, tools=tools)
            self._connections[name] = conn

            # Обновляем индекс инструментов
            for tool in tools:
                self._tool_index[tool["name"]] = name

            logger.info(
                "Подключён к MCP-серверу '%s': %d инструментов",
                name, len(tools),
            )
            return tools

        except Exception:
            await exit_stack.aclose()
            raise

    async def disconnect(self, name: str) -> None:
        """Отключается от MCP-сервера."""
        conn = self._connections.pop(name, None)
        if not conn:
            return

        # Удаляем инструменты из индекса
        for tool in conn.tools:
            self._tool_index.pop(tool["name"], None)

        try:
            await conn.exit_stack.aclose()
        except RuntimeError as e:
            # anyio cancel scope может ругаться при закрытии из другого task
            logger.warning("Предупреждение при отключении '%s': %s", name, e)
        logger.info("Отключён от MCP-сервера '%s'", name)

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Вызывает инструмент через соответствующий MCP-сервер.

        Returns:
            текстовый результат выполнения инструмента
        """
        server_name = self._tool_index.get(tool_name)
        if not server_name or server_name not in self._connections:
            return f"Инструмент '{tool_name}' недоступен"

        conn = self._connections[server_name]
        try:
            result = await conn.session.call_tool(tool_name, arguments)
            # Собираем текстовые части результата
            parts = []
            for content in result.content:
                if hasattr(content, "text"):
                    parts.append(content.text)
            return "\n".join(parts) if parts else "(пустой результат)"
        except Exception as e:
            logger.error("Ошибка вызова инструмента '%s': %s", tool_name, e)
            return f"Ошибка выполнения: {e}"

    def get_all_tool_schemas(self) -> list[dict]:
        """Возвращает JSON-схемы всех инструментов всех подключённых серверов."""
        schemas = []
        for conn in self._connections.values():
            schemas.extend(conn.tools)
        return schemas

    def list_servers(self) -> list[dict]:
        """Возвращает список всех серверов из конфига с их статусом."""
        config = load_config()
        servers = []
        for name, cfg in config.get("servers", {}).items():
            conn = self._connections.get(name)
            servers.append({
                "name": name,
                "command": cfg.get("command", ""),
                "args": cfg.get("args", []),
                "enabled": cfg.get("enabled", False),
                "connected": conn is not None,
                "tool_count": len(conn.tools) if conn else 0,
            })
        return servers

    def list_tools(self) -> list[dict]:
        """Возвращает список всех доступных инструментов с указанием сервера."""
        tools = []
        for server_name, conn in self._connections.items():
            for tool in conn.tools:
                tools.append({
                    "server": server_name,
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                })
        return tools

    def add_server(self, name: str, command: str, args: list[str] | None = None) -> None:
        """Добавляет новый сервер в конфигурацию."""
        config = load_config()
        config.setdefault("servers", {})[name] = {
            "command": command,
            "args": args or [],
            "enabled": False,
        }
        save_config(config)

    def remove_server(self, name: str) -> None:
        """Удаляет сервер из конфигурации."""
        config = load_config()
        config.get("servers", {}).pop(name, None)
        save_config(config)

    async def auto_connect(self) -> None:
        """Подключает все серверы с enabled=true."""
        config = load_config()
        for name, cfg in config.get("servers", {}).items():
            if cfg.get("enabled"):
                try:
                    await self.connect(name)
                except Exception as e:
                    logger.error("Не удалось подключить MCP-сервер '%s': %s", name, e)

    async def shutdown(self) -> None:
        """Отключает все серверы при остановке приложения."""
        names = list(self._connections.keys())
        for name in names:
            try:
                await self.disconnect(name)
            except Exception as e:
                logger.error("Ошибка при отключении '%s': %s", name, e)
