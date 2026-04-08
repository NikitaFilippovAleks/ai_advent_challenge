/**
 * API-клиент для управления MCP-серверами.
 */

import type { MCPServer, MCPTool } from "../types";

/** Получить список всех MCP-серверов */
export async function listServers(): Promise<MCPServer[]> {
  const res = await fetch("/api/mcp/servers");
  if (!res.ok) throw new Error("Не удалось получить список серверов");
  return res.json();
}

/** Добавить новый MCP-сервер */
export async function addServer(
  name: string,
  command: string,
  args: string[] = []
): Promise<MCPServer> {
  const res = await fetch("/api/mcp/servers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, command, args }),
  });
  if (!res.ok) throw new Error("Не удалось добавить сервер");
  return res.json();
}

/** Удалить MCP-сервер */
export async function removeServer(name: string): Promise<void> {
  const res = await fetch(`/api/mcp/servers/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Не удалось удалить сервер");
}

/** Подключиться к MCP-серверу */
export async function connectServer(
  name: string
): Promise<{ status: string; tools: number }> {
  const res = await fetch(
    `/api/mcp/servers/${encodeURIComponent(name)}/connect`,
    { method: "POST" }
  );
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Не удалось подключиться");
  }
  return res.json();
}

/** Отключиться от MCP-сервера */
export async function disconnectServer(name: string): Promise<void> {
  const res = await fetch(
    `/api/mcp/servers/${encodeURIComponent(name)}/disconnect`,
    { method: "POST" }
  );
  if (!res.ok) throw new Error("Не удалось отключиться");
}

/** Получить список всех доступных инструментов */
export async function listTools(): Promise<MCPTool[]> {
  const res = await fetch("/api/mcp/tools");
  if (!res.ok) throw new Error("Не удалось получить список инструментов");
  return res.json();
}
