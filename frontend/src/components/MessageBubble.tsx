import ReactMarkdown from "react-markdown";
import { Message } from "../types";
import ToolCallBlock from "./ToolCallBlock";
import SourcesPanel from "./SourcesPanel";

interface Props {
  message: Message;
}

// Вырезает скрытые JSON-блоки FSM из отображаемого контента
function cleanTaskJson(content: string): string {
  // Убираем <json>...</json> теги
  let cleaned = content.replace(/<json>[\s\S]*?<\/json>/g, "");
  // Убираем ```json блоки содержащие "steps"
  cleaned = cleaned.replace(/```json\s*[\s\S]*?"steps"[\s\S]*?```/g, "");
  // Убираем лишние пустые строки подряд
  cleaned = cleaned.replace(/\n{3,}/g, "\n\n");
  return cleaned.trim();
}

function MessageBubble({ message }: Props) {
  const hasMetadata =
    message.role === "assistant" &&
    (message.usage || message.responseTime !== undefined);

  // Для ассистента — очищаем скрытые JSON-блоки FSM
  const displayContent =
    message.role === "assistant"
      ? cleanTaskJson(message.content)
      : message.content;

  return (
    <div className={`message bubble ${message.role}`}>
      {message.role === "assistant" ? (
        <div className="markdown-content">
          {message.toolEvents && message.toolEvents.length > 0 && (
            <ToolCallBlock events={message.toolEvents} />
          )}
          <ReactMarkdown>{displayContent}</ReactMarkdown>
          {message.sources && message.sources.length > 0 && (
            <SourcesPanel sources={message.sources} />
          )}
        </div>
      ) : (
        message.content
      )}
      {hasMetadata && (
        <div className="message-meta">
          {message.responseTime !== undefined && (
            <span>{(message.responseTime / 1000).toFixed(1)}с</span>
          )}
          {message.usage && (
            <>
              <span className="token-badge token-prompt">
                ↑ {message.usage.prompt_tokens}
              </span>
              <span className="token-badge token-completion">
                ↓ {message.usage.completion_tokens}
              </span>
              <span className="token-badge token-total">
                Σ {message.usage.total_tokens}
              </span>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default MessageBubble;
