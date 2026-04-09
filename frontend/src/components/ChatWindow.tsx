import { useState, useEffect, useRef, useMemo } from "react";
import { Message, ModelInfo, ContextStrategy, TaskInfo } from "../types";
import type { ToolCallEvent, ToolResultEvent } from "../types";
import { streamMessage, getMessages, getStrategy, setStrategy } from "../api/chat";
import MessageList from "./MessageList";
import MessageInput from "./MessageInput";
import FactsPanel from "./FactsPanel";
import BranchPanel from "./BranchPanel";
import MemoryPanel from "./MemoryPanel";
import MCPPanel from "./MCPPanel";
import SchedulerPanel from "./SchedulerPanel";
import ProfileSelector from "./ProfileSelector";
import TaskPanel from "./TaskPanel";
import { getActiveTask } from "../api/tasks";

interface Props {
  models: ModelInfo[];
  conversationId: string | null;
  onConversationUpdate: () => void;
  profilesVersion?: number;
}

// Названия стратегий для UI (memory убрана — память работает всегда)
const STRATEGY_LABELS: Record<string, string> = {
  summary: "Суммаризация",
  sliding_window: "Скользящее окно",
  sticky_facts: "Ключевые факты",
  branching: "Ветки диалога",
};

function ChatWindow({ models, conversationId, onConversationUpdate, profilesVersion }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [temperature, setTemperature] = useState<number>(0.7);
  const [contextStrategy, setContextStrategy] = useState<ContextStrategy>("summary");
  // Триггер для обновления панели памяти после ответа LLM
  const [memoryRefreshTrigger, setMemoryRefreshTrigger] = useState(0);
  // Состояние сворачивания правой панели памяти
  const [memoryPanelOpen, setMemoryPanelOpen] = useState(true);
  const [activeTask, setActiveTask] = useState<TaskInfo | null>(null);
  // Панель MCP-серверов
  const [mcpPanelOpen, setMcpPanelOpen] = useState(false);
  // Панель планировщика
  const [schedulerPanelOpen, setSchedulerPanelOpen] = useState(false);
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
      getActiveTask(conversationId)
        .then(setActiveTask)
        .catch(() => setActiveTask(null));
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

  // Флаг: автоматическое продолжение (сообщение "Продолжай" не показывается в UI)
  const autoSendRef = useRef(false);

  const handleSend = async (text: string) => {
    const isAuto = autoSendRef.current;
    autoSendRef.current = false;

    // Автоматические сообщения не показываем в UI
    const updatedMessages = isAuto
      ? messages
      : [...messages, { role: "user" as const, content: text }];

    // Сбрасываем буфер стриминга
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
            rafIdRef.current = requestAnimationFrame(() => {
              const text = streamBufferRef.current;
              const elapsed = Date.now() - startTimeRef.current;
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                updated[updated.length - 1] = {
                  ...last,
                  content: text,
                  responseTime: elapsed,
                };
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
          // Память работает всегда — обновляем панель после каждого ответа.
          // Первый refresh сразу, затем отложенные (ждём фоновый extract_memories на бэкенде)
          setMemoryRefreshTrigger((prev) => prev + 1);
          setTimeout(() => setMemoryRefreshTrigger((prev) => prev + 1), 5000);
          setTimeout(() => setMemoryRefreshTrigger((prev) => prev + 1), 12000);
          // Обновляем статус задачи после ответа LLM
          if (conversationId) {
            setTimeout(() => {
              getActiveTask(conversationId)
                .then((task) => {
                  setActiveTask(task);
                  // Автопродолжение: если задача в execution — отправляем следующий шаг
                  if (task && task.phase === "execution") {
                    autoSendRef.current = true;
                    handleSend("Продолжай");
                  }
                })
                .catch(() => {});
            }, 1500);
          }
        },
        onToolCall: (event: ToolCallEvent) => {
          // Добавляем событие вызова инструмента в toolEvents сообщения
          setMessages((prev) => {
            const updated = [...prev];
            const last = { ...updated[updated.length - 1] };
            const events = [...(last.toolEvents || [])];
            events.push({
              type: "call",
              name: event.name,
              arguments: event.arguments,
              timestamp: Date.now(),
            });
            last.toolEvents = events;
            last.content = "";
            updated[updated.length - 1] = last;
            return updated;
          });
        },
        onToolResult: (event: ToolResultEvent) => {
          // Добавляем результат инструмента в toolEvents сообщения
          setMessages((prev) => {
            const updated = [...prev];
            const last = { ...updated[updated.length - 1] };
            const events = [...(last.toolEvents || [])];
            events.push({
              type: "result",
              name: event.name,
              content: event.content,
              timestamp: Date.now(),
            });
            last.toolEvents = events;
            updated[updated.length - 1] = last;
            return updated;
          });
          // Сбрасываем буфер — после tool calls пойдёт финальный текст
          streamBufferRef.current = "";
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
              {(Object.keys(STRATEGY_LABELS)).map((s) => (
                <option key={s} value={s}>
                  {STRATEGY_LABELS[s]}
                </option>
              ))}
            </select>
          )}
          {/* Селектор профиля */}
          {conversationId && (
            <ProfileSelector
              key={profilesVersion}
              conversationId={conversationId}
            />
          )}
          {/* Кнопка MCP-серверов */}
          <button
            className="memory-toggle-btn"
            onClick={() => setMcpPanelOpen((prev) => !prev)}
            title={mcpPanelOpen ? "Скрыть MCP" : "Показать MCP"}
            style={{ marginRight: "4px" }}
          >
            {mcpPanelOpen ? "▶" : "◀"} MCP
          </button>
          {/* Кнопка планировщика */}
          <button
            className="memory-toggle-btn"
            onClick={() => setSchedulerPanelOpen((prev) => !prev)}
            title={schedulerPanelOpen ? "Скрыть планировщик" : "Показать планировщик"}
            style={{ marginRight: "4px" }}
          >
            {schedulerPanelOpen ? "▶" : "◀"} Расписание
          </button>
          {/* Кнопка сворачивания/разворачивания панели памяти */}
          {conversationId && (
            <button
              className="memory-toggle-btn"
              onClick={() => setMemoryPanelOpen((prev) => !prev)}
              title={memoryPanelOpen ? "Скрыть память" : "Показать память"}
            >
              {memoryPanelOpen ? "▶" : "◀"} Память
            </button>
          )}
        </div>
      </div>
      {conversationId ? (
        <div className="chat-body">
          <div className="chat-main">
            {/* Панель фактов — отображается при стратегии sticky_facts */}
            {contextStrategy === "sticky_facts" && (
              <FactsPanel
                conversationId={conversationId}
                refreshTrigger={memoryRefreshTrigger}
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
            {/* Панель задачи (FSM) — отображается при активной задаче */}
            {activeTask && (
              <TaskPanel
                task={activeTask}
                onTaskUpdate={setActiveTask}
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
          </div>
          {/* Панель MCP-серверов (сворачиваемая) */}
          {mcpPanelOpen && (
            <div className="memory-panel">
              <MCPPanel />
            </div>
          )}
          {/* Панель планировщика (сворачиваемая) */}
          {schedulerPanelOpen && (
            <div className="memory-panel">
              <SchedulerPanel />
            </div>
          )}
          {/* Панель памяти — ВСЕГДА справа от чата (сворачиваемая) */}
          {memoryPanelOpen && (
            <MemoryPanel
              conversationId={conversationId}
              refreshTrigger={memoryRefreshTrigger}
            />
          )}
        </div>
      ) : (
        <div className="chat-placeholder">
          Выберите диалог или создайте новый
        </div>
      )}
    </div>
  );
}

export default ChatWindow;
