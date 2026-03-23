import { ChatRequest, ChatResponse, ModelInfo, UsageInfo } from "../types";

// Отправка сообщения без стриминга (обратная совместимость)
export async function sendMessage(request: ChatRequest): Promise<ChatResponse> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    throw new Error(`Ошибка: ${res.status}`);
  }

  return res.json();
}

// Колбэки для обработки SSE-событий стриминга
export interface StreamCallbacks {
  onDelta: (content: string) => void;
  onUsage: (usage: UsageInfo) => void;
  onDone: () => void;
  onError: (error: Error) => void;
}

// Стриминг ответа через SSE (fetch + ReadableStream)
export async function streamMessage(
  request: ChatRequest,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal,
    });
  } catch (err) {
    // AbortError — пользователь прервал генерацию
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

      // Разбираем SSE-события из буфера
      const parts = buffer.split("\n\n");
      // Последний элемент — неполное событие, оставляем в буфере
      buffer = parts.pop() || "";

      for (const part of parts) {
        let eventType = "";
        let eventData = "";

        for (const line of part.split("\n")) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7);
          } else if (line.startsWith("data: ")) {
            eventData = line.slice(6);
          }
        }

        if (!eventType || !eventData) continue;

        const data = JSON.parse(eventData);

        if (eventType === "delta") {
          callbacks.onDelta(data.content);
        } else if (eventType === "usage") {
          callbacks.onUsage(data);
        } else if (eventType === "done") {
          callbacks.onDone();
        } else if (eventType === "error") {
          callbacks.onError(new Error(data.message));
        }
      }
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return;
    callbacks.onError(err instanceof Error ? err : new Error(String(err)));
  }
}

export async function getModels(): Promise<ModelInfo[]> {
  const res = await fetch("/api/models");

  if (!res.ok) {
    throw new Error(`Ошибка: ${res.status}`);
  }

  const data = await res.json();
  return data.models;
}
