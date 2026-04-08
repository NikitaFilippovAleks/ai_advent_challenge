/**
 * Панель управления MCP-серверами.
 * Показывает список серверов, статус, позволяет подключать/отключать.
 */

import { useCallback, useEffect, useState } from "react";
import type { MCPServer, MCPTool } from "../types";
import {
  listServers,
  connectServer,
  disconnectServer,
  listTools,
  addServer,
  removeServer,
} from "../api/mcp";

interface MCPPanelProps {
  refreshTrigger?: number;
}

export default function MCPPanel({ refreshTrigger }: MCPPanelProps) {
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Форма добавления сервера
  const [showAddForm, setShowAddForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newCommand, setNewCommand] = useState("");
  const [newArgs, setNewArgs] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [s, t] = await Promise.all([listServers(), listTools()]);
      setServers(s);
      setTools(t);
      setError(null);
    } catch (e) {
      setError("Не удалось загрузить данные MCP");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh, refreshTrigger]);

  const handleConnect = async (name: string) => {
    setLoading(name);
    setError(null);
    try {
      await connectServer(name);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка подключения");
    } finally {
      setLoading(null);
    }
  };

  const handleDisconnect = async (name: string) => {
    setLoading(name);
    setError(null);
    try {
      await disconnectServer(name);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка отключения");
    } finally {
      setLoading(null);
    }
  };

  const handleAdd = async () => {
    if (!newName || !newCommand) return;
    try {
      const args = newArgs ? newArgs.split(" ").filter(Boolean) : [];
      await addServer(newName, newCommand, args);
      setNewName("");
      setNewCommand("");
      setNewArgs("");
      setShowAddForm(false);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка добавления");
    }
  };

  const handleRemove = async (name: string) => {
    try {
      await removeServer(name);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка удаления");
    }
  };

  return (
    <div style={{ padding: "12px", fontSize: "13px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
        <strong>MCP-серверы</strong>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          style={{
            background: "none", border: "1px solid #555", color: "#ccc",
            borderRadius: "4px", padding: "2px 8px", cursor: "pointer", fontSize: "12px",
          }}
        >
          {showAddForm ? "Отмена" : "+ Добавить"}
        </button>
      </div>

      {error && (
        <div style={{ color: "#ff6b6b", marginBottom: "8px", fontSize: "12px" }}>
          {error}
        </div>
      )}

      {showAddForm && (
        <div style={{ marginBottom: "12px", padding: "8px", background: "#2a2a2a", borderRadius: "6px" }}>
          <input
            placeholder="Имя сервера"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            style={inputStyle}
          />
          <input
            placeholder="Команда (python)"
            value={newCommand}
            onChange={(e) => setNewCommand(e.target.value)}
            style={inputStyle}
          />
          <input
            placeholder="Аргументы (через пробел)"
            value={newArgs}
            onChange={(e) => setNewArgs(e.target.value)}
            style={inputStyle}
          />
          <button onClick={handleAdd} style={btnStyle}>
            Добавить
          </button>
        </div>
      )}

      {servers.length === 0 ? (
        <div style={{ color: "#888", textAlign: "center", padding: "20px" }}>
          Нет MCP-серверов
        </div>
      ) : (
        servers.map((server) => (
          <div
            key={server.name}
            style={{
              padding: "8px",
              marginBottom: "8px",
              background: "#2a2a2a",
              borderRadius: "6px",
              borderLeft: `3px solid ${server.connected ? "#4caf50" : "#666"}`,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <span style={{ fontWeight: "bold" }}>{server.name}</span>
                <span style={{
                  marginLeft: "8px",
                  fontSize: "11px",
                  color: server.connected ? "#4caf50" : "#888",
                }}>
                  {server.connected ? `подключён (${server.tool_count} инструментов)` : "отключён"}
                </span>
              </div>
              <div style={{ display: "flex", gap: "4px" }}>
                {server.connected ? (
                  <button
                    onClick={() => handleDisconnect(server.name)}
                    disabled={loading === server.name}
                    style={{ ...smallBtnStyle, color: "#ff6b6b" }}
                  >
                    {loading === server.name ? "..." : "Откл"}
                  </button>
                ) : (
                  <button
                    onClick={() => handleConnect(server.name)}
                    disabled={loading === server.name}
                    style={{ ...smallBtnStyle, color: "#4caf50" }}
                  >
                    {loading === server.name ? "..." : "Подкл"}
                  </button>
                )}
                <button
                  onClick={() => handleRemove(server.name)}
                  style={{ ...smallBtnStyle, color: "#888" }}
                >
                  ✕
                </button>
              </div>
            </div>
            <div style={{ fontSize: "11px", color: "#888", marginTop: "4px" }}>
              {server.command} {server.args.join(" ")}
            </div>
          </div>
        ))
      )}

      {tools.length > 0 && (
        <>
          <div style={{ marginTop: "16px", marginBottom: "8px" }}>
            <strong>Доступные инструменты ({tools.length})</strong>
          </div>
          {tools.map((tool) => (
            <div
              key={`${tool.server}-${tool.name}`}
              style={{
                padding: "6px 8px",
                marginBottom: "4px",
                background: "#1e1e1e",
                borderRadius: "4px",
                fontSize: "12px",
              }}
            >
              <span style={{ color: "#82aaff" }}>{tool.name}</span>
              <span style={{ color: "#888", marginLeft: "8px" }}>{tool.description}</span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "6px 8px",
  marginBottom: "6px",
  background: "#1e1e1e",
  border: "1px solid #444",
  borderRadius: "4px",
  color: "#ccc",
  fontSize: "12px",
  boxSizing: "border-box",
};

const btnStyle: React.CSSProperties = {
  padding: "4px 12px",
  background: "#4caf50",
  color: "#fff",
  border: "none",
  borderRadius: "4px",
  cursor: "pointer",
  fontSize: "12px",
};

const smallBtnStyle: React.CSSProperties = {
  background: "none",
  border: "1px solid #444",
  borderRadius: "4px",
  padding: "1px 6px",
  cursor: "pointer",
  fontSize: "11px",
};
