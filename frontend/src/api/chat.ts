import { ChatRequest, ChatResponse, ModelInfo } from "../types";

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

export async function getModels(): Promise<ModelInfo[]> {
  const res = await fetch("/api/models");

  if (!res.ok) {
    throw new Error(`Ошибка: ${res.status}`);
  }

  const data = await res.json();
  return data.models;
}
