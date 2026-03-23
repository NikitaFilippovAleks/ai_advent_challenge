// Информация об использовании токенов
export interface UsageInfo {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

// Роли сообщений — расширяемо для агентной архитектуры
export type MessageRole = "user" | "assistant" | "system" | "tool";

// Единое сообщение в диалоге
export interface Message {
  role: MessageRole;
  content: string;
  usage?: UsageInfo;        // токены (только для assistant)
  responseTime?: number;    // время ответа в мс (только для assistant)
  // Подготовка для агентной архитектуры (пока не используются)
  toolCalls?: ToolCall[];
  toolCallId?: string;
}

// Запрос к /api/chat и /api/chat/stream
export interface ChatRequest {
  messages: Array<{ role: string; content: string }>;
  model?: string;
  temperature?: number;
}

// Ответ от /api/chat (не-стриминг)
export interface ChatResponse {
  content: string;
  usage?: UsageInfo;
}

// Информация о доступной модели
export interface ModelInfo {
  id: string;
  name: string;
}

// --- Подготовка для агентной архитектуры ---

// Вызов инструмента от ассистента
export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

// SSE-событие delta (тип контента расширяем)
export interface StreamDelta {
  content: string;
  type: "content" | "tool_call" | "tool_result";
}
