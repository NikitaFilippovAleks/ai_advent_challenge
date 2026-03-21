// Информация об использовании токенов
export interface UsageInfo {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

// Единое сообщение в диалоге
export interface Message {
  role: "user" | "assistant";
  content: string;
  usage?: UsageInfo;        // токены (только для assistant)
  responseTime?: number;    // время ответа в мс (только для assistant)
}

// Запрос к /api/chat
export interface ChatRequest {
  messages: Message[];
  style?: "normal" | "custom";
  model?: string;
  temperature?: number;
}

// Ответ от /api/chat
export interface ChatResponse {
  content: string;
  usage?: UsageInfo;
}

// Информация о доступной модели
export interface ModelInfo {
  id: string;
  name: string;
}
