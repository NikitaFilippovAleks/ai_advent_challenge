import {
  Branch,
  ChatRequest,
  ChatResponse,
  ContextStrategy,
  Conversation,
  Fact,
  LongTermMemoryEntry,
  MemoryState,
  Message,
  ModelInfo,
  UsageInfo,
} from "../types";

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

// --- Функции для работы с диалогами ---

export async function getConversations(): Promise<Conversation[]> {
  const res = await fetch("/api/conversations");
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}

export async function createConversation(): Promise<Conversation> {
  const res = await fetch("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}

export async function getMessages(conversationId: string): Promise<Message[]> {
  const res = await fetch(`/api/conversations/${conversationId}/messages`);
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const res = await fetch(`/api/conversations/${conversationId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
}

export async function getModels(): Promise<ModelInfo[]> {
  const res = await fetch("/api/models");

  if (!res.ok) {
    throw new Error(`Ошибка: ${res.status}`);
  }

  const data = await res.json();
  return data.models;
}

// --- Стратегии контекста ---

export async function getStrategy(conversationId: string): Promise<ContextStrategy> {
  const res = await fetch(`/api/conversations/${conversationId}/strategy`);
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  const data = await res.json();
  return data.strategy;
}

export async function setStrategy(
  conversationId: string,
  strategy: ContextStrategy,
): Promise<void> {
  const res = await fetch(`/api/conversations/${conversationId}/strategy`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ strategy }),
  });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
}

// --- Факты (Sticky Facts) ---

export async function getFacts(conversationId: string): Promise<Fact[]> {
  const res = await fetch(`/api/conversations/${conversationId}/facts`);
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  const data = await res.json();
  return data.facts;
}

export async function updateFact(
  conversationId: string,
  key: string,
  value: string,
): Promise<void> {
  const res = await fetch(`/api/conversations/${conversationId}/facts`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
}

export async function deleteFact(
  conversationId: string,
  key: string,
): Promise<void> {
  const res = await fetch(`/api/conversations/${conversationId}/facts/${encodeURIComponent(key)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
}

// --- Ветки (Branching) ---

export async function getBranches(
  conversationId: string,
): Promise<{ branches: Branch[]; active_branch_id: number | null }> {
  const res = await fetch(`/api/conversations/${conversationId}/branches`);
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}

export async function createBranch(
  conversationId: string,
  name: string,
  checkpointMessageId: number,
): Promise<Branch> {
  const res = await fetch(`/api/conversations/${conversationId}/branches`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, checkpoint_message_id: checkpointMessageId }),
  });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}

export async function activateBranch(
  conversationId: string,
  branchId: number,
): Promise<void> {
  const res = await fetch(
    `/api/conversations/${conversationId}/branches/${branchId}/activate`,
    { method: "PUT" },
  );
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
}

// --- Память ассистента (3 уровня) ---

// Все 3 уровня памяти одним запросом
export async function getMemory(conversationId: string): Promise<MemoryState> {
  const res = await fetch(`/api/memory/${conversationId}`);
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}

// Краткосрочная память
export async function addInsight(
  conversationId: string,
  content: string,
): Promise<{ id: number }> {
  const res = await fetch(`/api/memory/${conversationId}/short-term`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}

export async function deleteInsight(
  conversationId: string,
  insightId: number,
): Promise<void> {
  const res = await fetch(
    `/api/memory/${conversationId}/short-term/${insightId}`,
    { method: "DELETE" },
  );
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
}

// Рабочая память
export async function setWorkingMemory(
  conversationId: string,
  key: string,
  value: string,
  category: string = "fact",
): Promise<void> {
  const res = await fetch(`/api/memory/${conversationId}/working`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value, category }),
  });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
}

export async function deleteWorkingMemory(
  conversationId: string,
  key: string,
): Promise<void> {
  const res = await fetch(
    `/api/memory/${conversationId}/working/${encodeURIComponent(key)}`,
    { method: "DELETE" },
  );
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
}

// Долгосрочная память
export async function getLongTermMemories(
  category?: string,
): Promise<LongTermMemoryEntry[]> {
  const params = category ? `?category=${encodeURIComponent(category)}` : "";
  const res = await fetch(`/api/memory/long-term${params}`);
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  const data = await res.json();
  return data.long_term;
}

export async function setLongTermMemory(
  key: string,
  value: string,
  category: string,
): Promise<void> {
  const res = await fetch("/api/memory/long-term", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value, category }),
  });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
}

export async function deleteLongTermMemory(memoryId: number): Promise<void> {
  const res = await fetch(`/api/memory/long-term/${memoryId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
}
