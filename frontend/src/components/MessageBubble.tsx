import { Message } from "../types";

interface Props {
  message: Message;
}

function MessageBubble({ message }: Props) {
  // Проверяем наличие метаданных для отображения
  const hasMetadata =
    message.role === "assistant" &&
    (message.usage || message.responseTime !== undefined);

  return (
    <div className={`message bubble ${message.role}`}>
      {message.content}
      {hasMetadata && (
        <div className="message-meta">
          {message.responseTime !== undefined && (
            <span>{(message.responseTime / 1000).toFixed(1)}с</span>
          )}
          {message.usage && (
            <span>{message.usage.total_tokens} ток.</span>
          )}
        </div>
      )}
    </div>
  );
}

export default MessageBubble;
