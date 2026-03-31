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
  id?: number;              // ID из БД (для branching)
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
  conversation_id?: string;
}

// Диалог (для списка в сайдбаре)
export interface Conversation {
  id: string;
  title: string;
  updated_at: string;
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

// --- Стратегии управления контекстом ---

// Доступные стратегии контекста
export type ContextStrategy = "summary" | "sliding_window" | "sticky_facts" | "branching" | "memory";

// Факт из диалога (для стратегии Sticky Facts)
export interface Fact {
  key: string;
  value: string;
  updated_at?: string;
}

// Ветка диалога (для стратегии Branching)
export interface Branch {
  id: number;
  name: string;
  checkpoint_message_id: number;
  created_at: string;
}

// --- Трёхуровневая память ассистента ---

// Краткосрочная память — наблюдение из текущего диалога
export interface ShortTermInsight {
  id: number;
  content: string;
  source_message_id?: number;
  created_at: string;
}

// Рабочая память — данные текущей задачи
export interface WorkingMemoryEntry {
  key: string;
  value: string;
  category: string;
  updated_at: string;
}

// Долгосрочная память — кросс-диалоговые знания
export interface LongTermMemoryEntry {
  id: number;
  category: string;
  key: string;
  value: string;
  source_conversation_id?: string;
  updated_at: string;
}

// Объединённое состояние всех 3 уровней памяти
export interface MemoryState {
  short_term: ShortTermInsight[];
  working: WorkingMemoryEntry[];
  long_term: LongTermMemoryEntry[];
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
