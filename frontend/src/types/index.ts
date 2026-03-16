export interface Message {
  role: "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  messages: Message[];
}

export interface ChatResponse {
  content: string;
}
