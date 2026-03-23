import { useEffect, useRef, useCallback } from "react";
import { Message } from "../types";
import MessageBubble from "./MessageBubble";

interface Props {
  messages: Message[];
  isLoading: boolean;
  onStop: () => void;
}

function MessageList({ messages, isLoading, onStop }: Props) {
  const listRef = useRef<HTMLDivElement>(null);
  const isNearBottomRef = useRef(true);

  // Проверяем, находится ли пользователь у нижнего края
  const checkIfNearBottom = useCallback(() => {
    const el = listRef.current;
    if (!el) return;
    const threshold = 80;
    isNearBottomRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
  }, []);

  // Скроллим вниз только если пользователь был у нижнего края
  useEffect(() => {
    if (isNearBottomRef.current && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <div className="message-list" ref={listRef} onScroll={checkIfNearBottom}>
      {messages.map((msg, i) => (
        <MessageBubble key={i} message={msg} />
      ))}
      {isLoading && (
        <button className="stop-button" onClick={onStop}>
          Остановить
        </button>
      )}
    </div>
  );
}

export default MessageList;
