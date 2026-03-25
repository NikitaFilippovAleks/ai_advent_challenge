import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { Message, ModelInfo } from "../types";
import { streamMessage, getMessages } from "../api/chat";
import MessageList from "./MessageList";
import MessageInput from "./MessageInput";

interface Props {
  models: ModelInfo[];
  conversationId: string | null;
  onConversationUpdate: () => void;
}

function ChatWindow({ models, conversationId, onConversationUpdate }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [temperature, setTemperature] = useState<number>(0.7);
  const abortRef = useRef<AbortController | null>(null);

  // Буфер для плавного стриминга: копим текст в ref, обновляем стейт через rAF
  const streamBufferRef = useRef("");
  const rafIdRef = useRef<number | null>(null);
  const startTimeRef = useRef(0);

  useEffect(() => {
    if (models.length > 0 && !selectedModel) {
      setSelectedModel(models[0].id);
    }
  }, [models, selectedModel]);

  // Загрузка истории сообщений при монтировании (если есть conversationId)
  useEffect(() => {
    if (conversationId) {
      getMessages(conversationId)
        .then(setMessages)
        .catch(() => {});
    }
  }, [conversationId]);

  // Сброс rAF при размонтировании
  useEffect(() => {
    return () => {
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
      }
    };
  }, []);

  // Flush буфера в стейт — вызывается из rAF
  const flushBuffer = useCallback(() => {
    const content = streamBufferRef.current;
    const elapsed = Date.now() - startTimeRef.current;
    setMessages((prev) => {
      const updated = [...prev];
      const last = updated[updated.length - 1];
      updated[updated.length - 1] = {
        ...last,
        content,
        responseTime: elapsed,
      };
      return updated;
    });
    rafIdRef.current = null;
  }, []);

  // Суммарные токены за весь диалог
  const totalUsage = useMemo(() => {
    let prompt = 0;
    let completion = 0;
    let total = 0;
    for (const m of messages) {
      if (m.usage) {
        prompt += m.usage.prompt_tokens;
        completion += m.usage.completion_tokens;
        total += m.usage.total_tokens;
      }
    }
    return { prompt, completion, total };
  }, [messages]);

  const handleSend = async (text: string) => {
    const userMessage: Message = { role: "user", content: text };
    const updatedMessages = [...messages, userMessage];

    // Сбрасываем буфер
    streamBufferRef.current = "";
    startTimeRef.current = Date.now();

    setMessages([...updatedMessages, { role: "assistant", content: "" }]);
    setIsLoading(true);

    const controller = new AbortController();
    abortRef.current = controller;

    await streamMessage(
      {
        messages: updatedMessages.map((m) => ({
          role: m.role,
          content: m.content,
        })),
        model: selectedModel,
        temperature,
        conversation_id: conversationId || undefined,
      },
      {
        // Текст копится в буфер, стейт обновляется через rAF (макс 60 раз/сек)
        onDelta: (content) => {
          streamBufferRef.current += content;
          if (rafIdRef.current === null) {
            rafIdRef.current = requestAnimationFrame(flushBuffer);
          }
        },
        onUsage: (usage) => {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            updated[updated.length - 1] = { ...last, usage };
            return updated;
          });
        },
        onDone: () => {
          // Финальный flush — убеждаемся что весь текст отрисован
          if (rafIdRef.current !== null) {
            cancelAnimationFrame(rafIdRef.current);
            rafIdRef.current = null;
          }
          const finalContent = streamBufferRef.current;
          const elapsed = Date.now() - startTimeRef.current;
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            updated[updated.length - 1] = {
              ...last,
              content: finalContent,
              responseTime: elapsed,
            };
            return updated;
          });
          setIsLoading(false);
          abortRef.current = null;
          // Обновляем список диалогов (название могло измениться)
          onConversationUpdate();
        },
        onError: (error) => {
          if (rafIdRef.current !== null) {
            cancelAnimationFrame(rafIdRef.current);
            rafIdRef.current = null;
          }
          const currentContent = streamBufferRef.current;
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            updated[updated.length - 1] = {
              ...last,
              content: currentContent || `Ошибка: ${error.message}`,
            };
            return updated;
          });
          setIsLoading(false);
          abortRef.current = null;
        },
      },
      controller.signal,
    );
  };

  const handleStop = () => {
    abortRef.current?.abort();
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
    // Финальный flush при остановке
    const finalContent = streamBufferRef.current;
    const elapsed = Date.now() - startTimeRef.current;
    setMessages((prev) => {
      const updated = [...prev];
      const last = updated[updated.length - 1];
      updated[updated.length - 1] = {
        ...last,
        content: finalContent,
        responseTime: elapsed,
      };
      return updated;
    });
    setIsLoading(false);
    abortRef.current = null;
  };

  return (
    <div className="chat-window">
      <div className="chat-header">
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
              onChange={(e) =>
                setTemperature(parseFloat(e.target.value) || 0)
              }
              min={0}
              max={2}
              step={0.1}
            />
          </div>
        </div>
      </div>
      {conversationId ? (
        <>
          <MessageList
            messages={messages}
            isLoading={isLoading}
            onStop={handleStop}
          />
          {totalUsage.total > 0 && (
            <div className="token-summary">
              <span className="token-summary-item prompt">↑ Запрос: {totalUsage.prompt}</span>
              <span className="token-summary-item completion">↓ Ответ: {totalUsage.completion}</span>
              <span className="token-summary-item total">Σ Всего: {totalUsage.total}</span>
            </div>
          )}
          <MessageInput onSend={handleSend} disabled={isLoading} />
        </>
      ) : (
        <div className="chat-placeholder">
          Выберите диалог или создайте новый
        </div>
      )}
    </div>
  );
}

export default ChatWindow;
