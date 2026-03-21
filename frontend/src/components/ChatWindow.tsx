import { useState, useEffect } from "react";
import { Message, ModelInfo } from "../types";
import { sendMessage } from "../api/chat";
import MessageList from "./MessageList";
import MessageInput from "./MessageInput";

interface Props {
  title: string;
  style?: "normal" | "custom";
  models: ModelInfo[];
}

function ChatWindow({ title, style = "normal", models }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [temperature, setTemperature] = useState<number>(0.7);

  // Устанавливаем первую модель по умолчанию при загрузке списка
  useEffect(() => {
    if (models.length > 0 && !selectedModel) {
      setSelectedModel(models[0].id);
    }
  }, [models, selectedModel]);

  const handleSend = async (text: string) => {
    const userMessage: Message = { role: "user", content: text };
    const updated = [...messages, userMessage];
    setMessages(updated);
    setIsLoading(true);

    const startTime = Date.now();

    try {
      const response = await sendMessage({
        messages: updated,
        style,
        model: selectedModel,
        temperature,
      });
      const responseTime = Date.now() - startTime;
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: response.content,
          usage: response.usage,
          responseTime,
        },
      ]);
    } catch (e) {
      const responseTime = Date.now() - startTime;
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Ошибка: ${e}`,
          responseTime,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="chat-window">
      <div className="chat-header">
        <span className="chat-title">{title}</span>
        <div className="chat-controls">
          <select
            className="chat-model-select"
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
          <div className="chat-temperature">
            <label>t=</label>
            <input
              type="number"
              className="chat-temperature-input"
              value={temperature}
              onChange={(e) => setTemperature(parseFloat(e.target.value) || 0)}
              min={0}
              max={2}
              step={0.1}
            />
          </div>
        </div>
      </div>
      <MessageList messages={messages} isLoading={isLoading} />
      <MessageInput onSend={handleSend} disabled={isLoading} />
    </div>
  );
}

export default ChatWindow;
