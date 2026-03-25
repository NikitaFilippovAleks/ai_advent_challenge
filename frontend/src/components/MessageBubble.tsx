import ReactMarkdown from "react-markdown";
import { Message } from "../types";

interface Props {
  message: Message;
}

function MessageBubble({ message }: Props) {
  const hasMetadata =
    message.role === "assistant" &&
    (message.usage || message.responseTime !== undefined);

  return (
    <div className={`message bubble ${message.role}`}>
      {message.role === "assistant" ? (
        <div className="markdown-content">
          <ReactMarkdown>{message.content}</ReactMarkdown>
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
