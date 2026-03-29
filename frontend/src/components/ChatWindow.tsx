import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { Message, ModelInfo, ContextStrategy } from "../types";
import { streamMessage, getMessages, getStrategy, setStrategy } from "../api/chat";
import MessageList from "./MessageList";
import MessageInput from "./MessageInput";
import FactsPanel from "./FactsPanel";
import BranchPanel from "./BranchPanel";

interface Props {
  models: ModelInfo[];
  conversationId: string | null;
  onConversationUpdate: () => void;
}

// Названия стратегий для UI
const STRATEGY_LABELS: Record<ContextStrategy, string> = {
  summary: "Суммаризация",
  sliding_window: "Скользящее окно",
  sticky_facts: "Ключевые факты",
  branching: "Ветки диалога",
};

function ChatWindow({ models, conversationId, onConversationUpdate }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [temperature, setTemperature] = useState<number>(0.7);
  const [contextStrategy, setContextStrategy] = useState<ContextStrategy>("summary");
  // Триггер для обновления панели фактов после ответа LLM
  const [factsRefreshTrigger, setFactsRefreshTrigger] = useState(0);
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

  // Загрузка истории сообщений и стратегии при смене диалога
  useEffect(() => {
    if (conversationId) {
      getMessages(conversationId)
        .then(setMessages)
        .catch(() => {});
      getStrategy(conversationId)
        .then(setContextStrategy)
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

  // Смена стратегии контекста
  const handleStrategyChange = async (newStrategy: ContextStrategy) => {
    setContextStrategy(newStrategy);
    if (conversationId) {
      await setStrategy(conversationId, newStrategy).catch(() => {});
    }
  };

  // Перезагрузка сообщений после переключения ветки
  const handleBranchSwitch = () => {
    if (conversationId) {
      getMessages(conversationId)
        .then(setMessages)
        .catch(() => {});
    }
  };

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

    // При наличии диалога отправляем только последнее сообщение —
    // бэкенд возьмёт историю из БД и подставит суммаризации
    const requestMessages = conversationId
      ? [{ role: "user" as const, content: text }]
      : updatedMessages.map((m) => ({ role: m.role, content: m.content }));

    await streamMessage(
      {
        messages: requestMessages,
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
          // Обновляем факты (если стратегия sticky_facts)
          if (contextStrategy === "sticky_facts") {
            setFactsRefreshTrigger((prev) => prev + 1);
          }
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
          {conversationId && (
            <select
              className="chat-strategy-select"
              value={contextStrategy}
              onChange={(e) =>
                handleStrategyChange(e.target.value as ContextStrategy)
              }
            >
              {(Object.keys(STRATEGY_LABELS) as ContextStrategy[]).map((s) => (
                <option key={s} value={s}>
                  {STRATEGY_LABELS[s]}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>
      {conversationId ? (
        <>
          {/* Панель фактов — отображается при стратегии sticky_facts */}
          {contextStrategy === "sticky_facts" && (
            <FactsPanel
              conversationId={conversationId}
              refreshTrigger={factsRefreshTrigger}
            />
          )}
          {/* Панель веток — отображается при стратегии branching */}
          {contextStrategy === "branching" && (
            <BranchPanel
              conversationId={conversationId}
              messages={messages}
              onBranchSwitch={handleBranchSwitch}
            />
          )}
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
