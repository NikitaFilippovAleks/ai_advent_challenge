/**
 * API-клиент для управления задачами планировщика.
 */

import type { ScheduledTask, SchedulerResult, SchedulerSummary } from "../types";

/** Получить список всех задач */
export async function fetchSchedulerTasks(): Promise<ScheduledTask[]> {
  const res = await fetch("/api/scheduler/tasks");
  if (!res.ok) throw new Error("Не удалось получить задачи планировщика");
  return res.json();
}

/** Получить результаты сбора по задаче */
export async function fetchTaskResults(
  taskId: string,
  limit: number = 10
): Promise<SchedulerResult[]> {
  const res = await fetch(
    `/api/scheduler/tasks/${encodeURIComponent(taskId)}/results?limit=${limit}`
  );
  if (!res.ok) throw new Error("Не удалось получить результаты");
  return res.json();
}

/** Получить последнюю сводку по задаче */
export async function fetchTaskSummary(
  taskId: string
): Promise<SchedulerSummary | null> {
  const res = await fetch(
    `/api/scheduler/tasks/${encodeURIComponent(taskId)}/summary`
  );
  if (!res.ok) throw new Error("Не удалось получить сводку");
  const data = await res.json();
  return data || null;
}

/** Сгенерировать сводку вручную */
export async function triggerSummary(
  taskId: string
): Promise<SchedulerSummary> {
  const res = await fetch(
    `/api/scheduler/tasks/${encodeURIComponent(taskId)}/summarize`,
    { method: "POST" }
  );
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Не удалось сгенерировать сводку");
  }
  return res.json();
}

/** Поставить задачу на паузу */
export async function pauseTask(taskId: string): Promise<void> {
  const res = await fetch(
    `/api/scheduler/tasks/${encodeURIComponent(taskId)}/pause`,
    { method: "PUT" }
  );
  if (!res.ok) throw new Error("Не удалось поставить на паузу");
}

/** Возобновить задачу */
export async function resumeTask(taskId: string): Promise<void> {
  const res = await fetch(
    `/api/scheduler/tasks/${encodeURIComponent(taskId)}/resume`,
    { method: "PUT" }
  );
  if (!res.ok) throw new Error("Не удалось возобновить");
}

/** Удалить задачу */
export async function deleteTask(taskId: string): Promise<void> {
  const res = await fetch(
    `/api/scheduler/tasks/${encodeURIComponent(taskId)}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error("Не удалось удалить задачу");
}
