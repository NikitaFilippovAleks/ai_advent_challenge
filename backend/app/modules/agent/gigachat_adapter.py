"""Адаптер между форматами MCP и GigaChat SDK.

Конвертирует JSON Schema инструментов MCP в формат Function GigaChat,
и формирует сообщения с результатами вызова функций.
"""

from gigachat.models import Function, FunctionParameters


def mcp_schemas_to_gigachat_functions(schemas: list[dict]) -> list[Function]:
    """Конвертирует MCP tool schemas в GigaChat Function объекты.

    Args:
        schemas: список словарей с ключами name, description, inputSchema

    Returns:
        список Function для передачи в Chat(functions=...)
    """
    functions = []
    for schema in schemas:
        input_schema = schema.get("inputSchema", {})
        params = FunctionParameters(
            type=input_schema.get("type", "object"),
            properties=input_schema.get("properties", {}),
            required=input_schema.get("required"),
        )
        functions.append(
            Function(
                name=schema["name"],
                description=schema.get("description", ""),
                parameters=params,
            )
        )
    return functions


def build_function_call_message(name: str, arguments: dict) -> dict:
    """Формирует сообщение ассистента с вызовом функции (для истории messages)."""
    import json

    return {
        "role": "assistant",
        "content": "",
        "function_call": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }


def build_function_result_message(name: str, content: str) -> dict:
    """Формирует сообщение с результатом выполнения функции.

    GigaChat требует чтобы content был валидной JSON-строкой.
    """
    import json

    return {
        "role": "function",
        "name": name,
        "content": json.dumps({"result": content}, ensure_ascii=False),
    }
