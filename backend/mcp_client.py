"""
Универсальный MCP-клиент.

Подключается к любому MCP-серверу по stdio и выводит список доступных инструментов.

Использование:
    python mcp_client.py <command> [args...]

Примеры:
    python mcp_client.py npx -y @modelcontextprotocol/server-filesystem /tmp
    python mcp_client.py python my_server.py
    python mcp_client.py uvx mcp-server-sqlite --db-path test.db
"""

import asyncio
import json
import sys
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def connect_and_list_tools(command: str, args: list[str]) -> None:
    """Подключается к MCP-серверу и выводит список его инструментов."""
    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=None,
    )

    full_command = " ".join([command, *args])
    print(f"Подключение к MCP-серверу: {full_command}")

    async with AsyncExitStack() as stack:
        # Запускаем MCP-сервер как subprocess и получаем stdio-транспорт
        stdio_transport = await stack.enter_async_context(stdio_client(server_params))
        stdio_read, stdio_write = stdio_transport

        # Создаём MCP-сессию и выполняем handshake (initialize)
        session = await stack.enter_async_context(
            ClientSession(stdio_read, stdio_write)
        )
        await session.initialize()

        print("Соединение установлено!\n")

        # Получаем список инструментов
        response = await session.list_tools()
        tools = response.tools

        if not tools:
            print("Сервер не предоставляет инструментов.")
            return

        print(f"Доступные инструменты ({len(tools)}):")
        for i, tool in enumerate(tools, 1):
            print(f"\n  {i}. {tool.name}")
            if tool.description:
                print(f"     Описание: {tool.description}")
            if tool.inputSchema:
                schema_str = json.dumps(tool.inputSchema, indent=6, ensure_ascii=False)
                print(f"     Параметры: {schema_str}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Использование: python mcp_client.py <command> [args...]")
        print()
        print("Примеры:")
        print("  python mcp_client.py npx -y @modelcontextprotocol/server-filesystem /tmp")
        print("  python mcp_client.py python my_server.py")
        sys.exit(1)

    command = sys.argv[1]
    args = sys.argv[2:]

    try:
        asyncio.run(connect_and_list_tools(command, args))
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
    except Exception as e:
        print(f"\nОшибка подключения к MCP-серверу: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
