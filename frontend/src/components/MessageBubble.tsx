import { Message } from "../types";

interface Props {
  message: Message;
}

function MessageBubble({ message }: Props) {
  return (
    <div className={`message bubble ${message.role}`}>
      {message.content}
    </div>
  );
}

export default MessageBubble;
