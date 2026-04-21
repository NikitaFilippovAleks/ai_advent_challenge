// API-клиент для playground-режима (локальные модели через LM Studio).
// Stateless: вся история сообщений живёт в стейте компонента и шлётся в каждом запросе.

import { ModelInfo, UsageInfo } from "../types";

export interface PlaygroundMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface PlaygroundRequest {
  messages: PlaygroundMessage[];
  model?: string;
  temperature?: number;
  system_prompt?: string;
}

export interface PlaygroundStreamCallbacks {
  onDelta: (content: string) => void;
  onUsage: (usage: UsageInfo) => void;
  onDone: () => void;
  onError: (error: Error) => void;
}

// Получить список моделей из LM Studio.
// Возвращает пустой массив, если сервер недоступен — UI покажет подсказку.
export async function getPlaygroundModels(): Promise<ModelInfo[]> {
  const res = await fetch("/api/playground/models");
  if (!res.ok) {
    // 503 — LM Studio выключен; вернём пусто и дадим UI показать hint
    if (res.status === 503) return [];
    throw new Error(`Ошибка: ${res.status}`);
  }
  const data = await res.json();
  return data.models;
}

// Стриминг через SSE. Та же схема, что в основном чате, но меньше типов событий.
export async function streamPlayground(
  request: PlaygroundRequest,
  callbacks: PlaygroundStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch("/api/playground/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return;
    callbacks.onError(err instanceof Error ? err : new Error(String(err)));
    return;
  }

  if (!res.ok) {
    callbacks.onError(new Error(`Ошибка: ${res.status}`));
    return;
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";

      for (const part of parts) {
        let eventType = "";
        let eventData = "";
        for (const line of part.split("\n")) {
          if (line.startsWith("event: ")) eventType = line.slice(7);
          else if (line.startsWith("data: ")) eventData = line.slice(6);
        }
        if (!eventType || !eventData) continue;

        const data = JSON.parse(eventData);
        if (eventType === "delta") callbacks.onDelta(data.content);
        else if (eventType === "usage") callbacks.onUsage(data);
        else if (eventType === "done") callbacks.onDone();
        else if (eventType === "error") callbacks.onError(new Error(data.message));
      }
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return;
    callbacks.onError(err instanceof Error ? err : new Error(String(err)));
  }
}
