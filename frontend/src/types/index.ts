export interface Message {
  role: "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  messages: Message[];
  style?: "normal" | "custom";
  model?: string;
}

export interface ChatResponse {
  content: string;
}

export interface ModelInfo {
  id: string;
  name: string;
}
