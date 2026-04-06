import { TaskInfo } from "../types";

// Получить активную задачу диалога
export async function getActiveTask(conversationId: string): Promise<TaskInfo | null> {
  const res = await fetch(`/api/tasks/${conversationId}/active`);
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}

// Переход фазы задачи
export async function transitionTask(taskId: string, phase: string): Promise<TaskInfo> {
  const res = await fetch(`/api/tasks/${taskId}/transition`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phase }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: "Неизвестная ошибка" }));
    throw new Error(data.detail || `Ошибка: ${res.status}`);
  }
  return res.json();
}

// История задач диалога
export async function getTaskHistory(conversationId: string): Promise<TaskInfo[]> {
  const res = await fetch(`/api/tasks/${conversationId}/history`);
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}
