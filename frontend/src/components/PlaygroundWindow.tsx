// Playground — отдельный минималистичный раздел для тестирования локальных моделей.
// Stateless: история живёт только в стейте компонента. Без БД, памяти, RAG, агента, стратегий.

import { useEffect, useRef, useState, useMemo } from "react";
import { Message, ModelInfo, RAGSource } from "../types";
import MessageList from "./MessageList";
import MessageInput from "./MessageInput";
import {
  getPlaygroundModels,
  streamPlayground,
  PlaygroundMessage,
} from "../api/playground";

// Ключи localStorage — чтобы RAG-настройки сохранялись между сессиями
const LS_USE_RAG = "playground.useRag";
const LS_RAG_RERANK = "playground.ragRerank";

function PlaygroundWindow() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [temperature, setTemperature] = useState<number>(0.7);
  const [systemPrompt, setSystemPrompt] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  // Ошибка загрузки моделей / подключения к LM Studio
  const [connectionError, setConnectionError] = useState<string | null>(null);
  // Переключатели RAG — та же семантика, что в основном ChatWindow.
  const [useRag, setUseRag] = useState<boolean>(
    () => localStorage.getItem(LS_USE_RAG) === "1",
  );
  const [ragRerankMode, setRagRerankMode] = useState<string>(
    () => localStorage.getItem(LS_RAG_RERANK) || "keyword",
  );

  useEffect(() => {
    localStorage.setItem(LS_USE_RAG, useRag ? "1" : "0");
  }, [useRag]);
  useEffect(() => {
    localStorage.setItem(LS_RAG_RERANK, ragRerankMode);
  }, [ragRerankMode]);

  const abortRef = useRef<AbortController | null>(null);
  const streamBufferRef = useRef("");
  const rafIdRef = useRef<number | null>(null);
  const startTimeRef = useRef(0);

  // Загружаем модели при монтировании
  useEffect(() => {
    loadModels();
    return () => {
      if (rafIdRef.current !== null) cancelAnimationFrame(rafIdRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadModels = async () => {
    setConnectionError(null);
    try {
      const list = await getPlaygroundModels();
      setModels(list);
      if (list.length === 0) {
        setConnectionError(
          "LM Studio не отвечает. Запусти локальный сервер (port 1234) и загрузи модель.",
        );
      } else if (!selectedModel) {
        setSelectedModel(list[0].id);
      }
    } catch (e) {
      setConnectionError(e instanceof Error ? e.message : String(e));
    }
  };

  // Суммарные токены по всем ответам ассистента
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

  const handleClear = () => {
    abortRef.current?.abort();
    setMessages([]);
  };

  const handleStop = () => {
    abortRef.current?.abort();
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
    const finalContent = streamBufferRef.current;
    const elapsed = Date.now() - startTimeRef.current;
    setMessages((prev) => {
      const updated = [...prev];
      const last = updated[updated.length - 1];
      updated[updated.length - 1] = { ...last, content: finalContent, responseTime: elapsed };
      return updated;
    });
    setIsLoading(false);
    abortRef.current = null;
  };

  const handleSend = async (text: string) => {
    const history: Message[] = [...messages, { role: "user", content: text }];
    streamBufferRef.current = "";
    startTimeRef.current = Date.now();
    setMessages([...history, { role: "assistant", content: "" }]);
    setIsLoading(true);

    const controller = new AbortController();
    abortRef.current = controller;

    // Вся история пересылается на бэк — он ничего не хранит
    const wireMessages: PlaygroundMessage[] = history.map((m) => ({
      role: m.role as "user" | "assistant" | "system",
      content: m.content,
    }));

    await streamPlayground(
      {
        messages: wireMessages,
        model: selectedModel || undefined,
        temperature,
        system_prompt: systemPrompt.trim() || undefined,
        use_rag: useRag || undefined,
        rag_rerank_mode: useRag ? ragRerankMode : undefined,
      },
      {
        onSources: (sources: RAGSource[], lowRelevance: boolean) => {
          // Привязываем источники к последнему ассистент-сообщению.
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            updated[updated.length - 1] = { ...last, sources, lowRelevance };
            return updated;
          });
        },
        onDelta: (content) => {
          streamBufferRef.current += content;
          if (rafIdRef.current === null) {
            rafIdRef.current = requestAnimationFrame(() => {
              const t = streamBufferRef.current;
              const elapsed = Date.now() - startTimeRef.current;
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                updated[updated.length - 1] = { ...last, content: t, responseTime: elapsed };
                return updated;
              });
              rafIdRef.current = null;
            });
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
        },
        onError: (error) => {
          if (rafIdRef.current !== null) {
            cancelAnimationFrame(rafIdRef.current);
            rafIdRef.current = null;
          }
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            updated[updated.length - 1] = {
              ...last,
              content: streamBufferRef.current || `Ошибка: ${error.message}`,
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

  return (
    <div className="chat-window">
      <div className="chat-header">
        <div className="chat-controls" style={{ flexWrap: "wrap", gap: "6px" }}>
          <select
            className="chat-model-select"
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            disabled={models.length === 0}
          >
            {models.length === 0 ? (
              <option value="">нет моделей</option>
            ) : (
              models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))
            )}
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
          <input
            type="text"
            placeholder="System prompt (опционально)"
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            style={{
              flex: "1 1 240px",
              minWidth: "200px",
              background: "#1e1e1e",
              color: "#ccc",
              border: "1px solid #444",
              borderRadius: "4px",
              padding: "4px 8px",
              fontSize: "12px",
            }}
          />
          <button className="memory-toggle-btn" onClick={loadModels} title="Обновить список моделей">
            ↻ Модели
          </button>
          {/* Переключатель RAG: по той же логике, что в ChatWindow */}
          <button
            className={`memory-toggle-btn${useRag ? " active" : ""}`}
            onClick={() => setUseRag((prev) => !prev)}
            title={useRag ? "Выключить RAG" : "Включить RAG"}
          >
            RAG {useRag ? "✓" : ""}
          </button>
          {useRag && (
            <select
              value={ragRerankMode}
              onChange={(e) => setRagRerankMode(e.target.value)}
              title="Режим реранкинга RAG"
              style={{
                background: "#1e1e1e",
                color: "#ccc",
                border: "1px solid #444",
                borderRadius: "4px",
                padding: "2px 4px",
                fontSize: "11px",
              }}
            >
              <option value="none">Без реранкинга</option>
              <option value="keyword">Keyword</option>
            </select>
          )}
          <button
            className="memory-toggle-btn"
            onClick={handleClear}
            disabled={messages.length === 0}
            title="Очистить историю"
          >
            Очистить
          </button>
        </div>
      </div>

      <div className="chat-body">
        <div className="chat-main">
          {connectionError && (
            <div
              style={{
                background: "#3a1e1e",
                color: "#f88",
                border: "1px solid #6a2e2e",
                borderRadius: "6px",
                padding: "8px 12px",
                margin: "8px",
                fontSize: "13px",
              }}
            >
              {connectionError}
            </div>
          )}
          {messages.length === 0 && !connectionError && (
            <div
              style={{
                color: "#888",
                padding: "16px",
                fontSize: "13px",
                textAlign: "center",
              }}
            >
              Playground для тестирования локальных моделей через LM Studio.
              <br />
              Stateless-чат без памяти и агента. Опционально можно включить RAG
              (retrieval и генерация — полностью локально).
            </div>
          )}
          <MessageList messages={messages} isLoading={isLoading} onStop={handleStop} />
          {totalUsage.total > 0 && (
            <div className="token-summary">
              <span className="token-summary-item prompt">↑ Запрос: {totalUsage.prompt}</span>
              <span className="token-summary-item completion">↓ Ответ: {totalUsage.completion}</span>
              <span className="token-summary-item total">Σ Всего: {totalUsage.total}</span>
            </div>
          )}
          <MessageInput onSend={handleSend} disabled={isLoading || models.length === 0} />
        </div>
      </div>
    </div>
  );
}

export default PlaygroundWindow;
