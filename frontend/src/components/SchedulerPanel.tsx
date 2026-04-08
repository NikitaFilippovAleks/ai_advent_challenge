/**
 * Панель управления задачами планировщика.
 * Показывает задачи, результаты сбора, сводки. Позволяет управлять задачами.
 */

import { useCallback, useEffect, useState } from "react";
import type { ScheduledTask, SchedulerResult, SchedulerSummary } from "../types";
import {
  fetchSchedulerTasks,
  fetchTaskResults,
  fetchTaskSummary,
  triggerSummary,
  pauseTask,
  resumeTask,
  deleteTask,
} from "../api/scheduler";

export default function SchedulerPanel() {
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [expandedTask, setExpandedTask] = useState<string | null>(null);
  const [results, setResults] = useState<SchedulerResult[]>([]);
  const [summary, setSummary] = useState<SchedulerSummary | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchSchedulerTasks();
      setTasks(data);
      setError(null);
    } catch {
      setError("Не удалось загрузить задачи");
    }
  }, []);

  // Автообновление каждые 30 секунд
  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30000);
    return () => clearInterval(interval);
  }, [refresh]);

  const handleExpand = async (taskId: string) => {
    if (expandedTask === taskId) {
      setExpandedTask(null);
      return;
    }
    setExpandedTask(taskId);
    try {
      const [r, s] = await Promise.all([
        fetchTaskResults(taskId, 5),
        fetchTaskSummary(taskId),
      ]);
      setResults(r);
      setSummary(s);
    } catch {
      setResults([]);
      setSummary(null);
    }
  };

  const handleSummarize = async (taskId: string) => {
    setLoading(taskId);
    setError(null);
    try {
      const s = await triggerSummary(taskId);
      setSummary(s);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка генерации сводки");
    } finally {
      setLoading(null);
    }
  };

  const handlePause = async (taskId: string) => {
    try {
      await pauseTask(taskId);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка");
    }
  };

  const handleResume = async (taskId: string) => {
    try {
      await resumeTask(taskId);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка");
    }
  };

  const handleDelete = async (taskId: string) => {
    try {
      await deleteTask(taskId);
      if (expandedTask === taskId) setExpandedTask(null);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка удаления");
    }
  };

  return (
    <div style={{ padding: "12px", fontSize: "13px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
        <strong>Планировщик задач</strong>
        <button
          onClick={refresh}
          style={{
            background: "none", border: "1px solid #555", color: "#ccc",
            borderRadius: "4px", padding: "2px 8px", cursor: "pointer", fontSize: "12px",
          }}
        >
          Обновить
        </button>
      </div>

      {error && (
        <div style={{ color: "#ff6b6b", marginBottom: "8px", fontSize: "12px" }}>
          {error}
        </div>
      )}

      {tasks.length === 0 ? (
        <div style={{ color: "#888", textAlign: "center", padding: "20px" }}>
          Нет задач. Попросите агента создать задачу мониторинга в чате.
        </div>
      ) : (
        tasks.map((task) => (
          <div
            key={task.id}
            style={{
              marginBottom: "8px",
              background: "#2a2a2a",
              borderRadius: "6px",
              borderLeft: `3px solid ${task.status === "active" ? "#4caf50" : "#ff9800"}`,
            }}
          >
            {/* Заголовок задачи */}
            <div
              style={{ padding: "8px", cursor: "pointer" }}
              onClick={() => handleExpand(task.id)}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <span style={{ fontWeight: "bold" }}>{task.name}</span>
                  <span style={{
                    marginLeft: "8px", fontSize: "11px",
                    color: task.status === "active" ? "#4caf50" : "#ff9800",
                  }}>
                    {task.status === "active" ? "активна" : "пауза"}
                  </span>
                </div>
                <div style={{ display: "flex", gap: "4px" }}>
                  {task.status === "active" ? (
                    <button onClick={(e) => { e.stopPropagation(); handlePause(task.id); }}
                      style={{ ...smallBtnStyle, color: "#ff9800" }}>
                      ⏸
                    </button>
                  ) : (
                    <button onClick={(e) => { e.stopPropagation(); handleResume(task.id); }}
                      style={{ ...smallBtnStyle, color: "#4caf50" }}>
                      ▶
                    </button>
                  )}
                  <button onClick={(e) => { e.stopPropagation(); handleDelete(task.id); }}
                    style={{ ...smallBtnStyle, color: "#888" }}>
                    ✕
                  </button>
                </div>
              </div>
              <div style={{ fontSize: "11px", color: "#888", marginTop: "4px" }}>
                {task.tool_name} · cron: {task.cron_expression} · {task.results_count} сборов
                {task.summary_cron && ` · сводка: ${task.summary_cron}`}
              </div>
            </div>

            {/* Развёрнутые детали */}
            {expandedTask === task.id && (
              <div style={{ padding: "0 8px 8px", borderTop: "1px solid #333" }}>
                {/* Кнопка генерации сводки */}
                <button
                  onClick={() => handleSummarize(task.id)}
                  disabled={loading === task.id}
                  style={{
                    ...btnStyle,
                    marginTop: "8px",
                    opacity: loading === task.id ? 0.5 : 1,
                  }}
                >
                  {loading === task.id ? "Генерация..." : "Сгенерировать сводку"}
                </button>

                {/* Последняя сводка */}
                {summary && (
                  <div style={{ marginTop: "8px", padding: "8px", background: "#1e1e1e", borderRadius: "4px" }}>
                    <div style={{ fontSize: "11px", color: "#82aaff", marginBottom: "4px" }}>
                      Сводка ({summary.created_at.slice(0, 16).replace("T", " ")})
                    </div>
                    <div style={{ whiteSpace: "pre-wrap", fontSize: "12px" }}>
                      {summary.summary}
                    </div>
                  </div>
                )}

                {/* Последние результаты */}
                {results.length > 0 && (
                  <div style={{ marginTop: "8px" }}>
                    <div style={{ fontSize: "11px", color: "#888", marginBottom: "4px" }}>
                      Последние сборы ({results.length})
                    </div>
                    {results.map((r, i) => (
                      <div key={i} style={{
                        padding: "4px 8px", marginBottom: "2px",
                        background: "#1e1e1e", borderRadius: "4px", fontSize: "11px",
                      }}>
                        <span style={{ color: "#888" }}>
                          {r.collected_at.slice(11, 19)}
                        </span>
                        <span style={{ marginLeft: "8px", color: "#ccc" }}>
                          {r.data.length > 100 ? r.data.slice(0, 100) + "..." : r.data}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
}

const btnStyle: React.CSSProperties = {
  padding: "4px 12px",
  background: "#4a6fa5",
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
