import { useState } from "react";
import { Message } from "../types";
import { sendMessage } from "../api/chat";
import MessageList from "./MessageList";
import MessageInput from "./MessageInput";

interface Props {
  title: string;
  style?: "normal" | "custom";
  model?: string;
}

function ChatWindow({ title, style = "normal", model }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const handleSend = async (text: string) => {
    const userMessage: Message = { role: "user", content: text };
    const updated = [...messages, userMessage];
    setMessages(updated);
    setIsLoading(true);

    try {
      const response = await sendMessage({ messages: updated, style, model });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: response.content },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Ошибка: ${e}` },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="chat-window">
      <div className="chat-title">{title}</div>
      <MessageList messages={messages} isLoading={isLoading} />
      <MessageInput onSend={handleSend} disabled={isLoading} />
    </div>
  );
}

export default ChatWindow;
