"""
Тестовый MCP-сервер с двумя инструментами.
Используется для проверки работы mcp_client.py.
"""

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from mcp.server import InitializationOptions, NotificationOptions


server = Server("test-server")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Возвращает список тестовых инструментов."""
    return [
        Tool(
            name="greet",
            description="Приветствует пользователя по имени",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Имя пользователя",
                    }
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="add",
            description="Складывает два числа",
            inputSchema={
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "Первое число"},
                    "b": {"type": "number", "description": "Второе число"},
                },
                "required": ["a", "b"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Выполняет вызов инструмента."""
    if name == "greet":
        return [TextContent(type="text", text=f"Привет, {arguments['name']}!")]
    elif name == "add":
        result = arguments["a"] + arguments["b"]
        return [TextContent(type="text", text=str(result))]
    raise ValueError(f"Неизвестный инструмент: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        init_options = InitializationOptions(
            server_name="test-server",
            server_version="0.1.0",
            capabilities=server.get_capabilities(
                notification_options=NotificationOptions(),
                experimental_capabilities=None,
            ),
        )
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
