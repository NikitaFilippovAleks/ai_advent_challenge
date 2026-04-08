"""REST API для управления MCP-серверами."""

from fastapi import APIRouter, Depends, HTTPException

from app.modules.agent.dependencies import get_mcp_manager
from app.modules.agent.mcp_manager import MCPManager
from app.modules.agent.schemas import AddServerRequest, MCPServerStatus, MCPToolInfo

router = APIRouter(tags=["mcp"])


@router.get("/api/mcp/servers", response_model=list[MCPServerStatus])
async def list_servers(
    mcp: MCPManager = Depends(get_mcp_manager),
) -> list[dict]:
    """Возвращает список всех MCP-серверов с их статусом."""
    return mcp.list_servers()


@router.post("/api/mcp/servers", response_model=MCPServerStatus)
async def add_server(
    request: AddServerRequest,
    mcp: MCPManager = Depends(get_mcp_manager),
) -> dict:
    """Добавляет новый MCP-сервер в конфигурацию."""
    mcp.add_server(request.name, request.command, request.args)
    servers = mcp.list_servers()
    for s in servers:
        if s["name"] == request.name:
            return s
    return {"name": request.name, "command": request.command, "args": request.args,
            "enabled": False, "connected": False, "tool_count": 0}


@router.delete("/api/mcp/servers/{name}")
async def remove_server(
    name: str,
    mcp: MCPManager = Depends(get_mcp_manager),
) -> dict:
    """Удаляет MCP-сервер из конфигурации (и отключает если подключён)."""
    await mcp.disconnect(name)
    mcp.remove_server(name)
    return {"status": "ok"}


@router.post("/api/mcp/servers/{name}/connect")
async def connect_server(
    name: str,
    mcp: MCPManager = Depends(get_mcp_manager),
) -> dict:
    """Подключается к MCP-серверу."""
    try:
        tools = await mcp.connect(name)
        return {"status": "connected", "tools": len(tools)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка подключения: {e}")


@router.post("/api/mcp/servers/{name}/disconnect")
async def disconnect_server(
    name: str,
    mcp: MCPManager = Depends(get_mcp_manager),
) -> dict:
    """Отключается от MCP-сервера."""
    await mcp.disconnect(name)
    return {"status": "disconnected"}


@router.get("/api/mcp/tools", response_model=list[MCPToolInfo])
async def list_tools(
    mcp: MCPManager = Depends(get_mcp_manager),
) -> list[dict]:
    """Возвращает список всех доступных инструментов из подключённых серверов."""
    return mcp.list_tools()
