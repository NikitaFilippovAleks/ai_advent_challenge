// Сравнительный режим playground: два подчата бок-о-бок с общим инпутом.
// Слева — Baseline (дефолтные параметры без оптимизации).
// Справа — Optimized (классификатор тикетов с JSON-выводом, low temperature, max_tokens=150).
// Один и тот же пользовательский ввод отправляется в оба подчата параллельно,
// чтобы визуально сравнить качество, скорость и токены.

import { useMemo, useRef, useState } from "react";
import { Message, ModelInfo } from "../types";
import MessageList from "./MessageList";
import MessageInput from "./MessageInput";
import {
  streamPlayground,
  PlaygroundMessage,
  PlaygroundProvider,
} from "../api/playground";
import {
  BASELINE_CONFIG,
  OPTIMIZED_CONFIG,
  PlaygroundChatConfig,
} from "./playgroundCompareConfig";

interface Props {
  models: ModelInfo[];
  selectedModel: string;
  provider: PlaygroundProvider;
  useRag: boolean;
  ragRerankMode: string;
}

// Полный стейт одной стороны сравнения
interface SideState {
  messages: Message[];
  isLoading: boolean;
}

// Ref-ы, которые нужны для корректного батчинга стрима через rAF
interface SideRefs {
  streamBuffer: string;
  rafId: number | null;
  startTime: number;
  abort: AbortController | null;
}

function emptySideRefs(): SideRefs {
  return { streamBuffer: "", rafId: null, startTime: 0, abort: null };
}

function PlaygroundCompareView({
  models,
  selectedModel,
  provider,
  useRag,
  ragRerankMode,
}: Props) {
  const [baseline, setBaseline] = useState<SideState>({
    messages: [],
    isLoading: false,
  });
  const [optimized, setOptimized] = useState<SideState>({
    messages: [],
    isLoading: false,
  });

  // Независимые ref-ы для стриминга каждой стороны — иначе буферы/rAF пересекутся
  const baselineRefs = useRef<SideRefs>(emptySideRefs());
  const optimizedRefs = useRef<SideRefs>(emptySideRefs());

  const isAnyLoading = baseline.isLoading || optimized.isLoading;

  // Суммарное потребление токенов — для быстрого сравнения ресурсов
  const baselineUsage = useMemo(() => sumUsage(baseline.messages), [baseline.messages]);
  const optimizedUsage = useMemo(() => sumUsage(optimized.messages), [optimized.messages]);

  const handleClear = () => {
    baselineRefs.current.abort?.abort();
    optimizedRefs.current.abort?.abort();
    setBaseline({ messages: [], isLoading: false });
    setOptimized({ messages: [], isLoading: false });
  };

  const handleStop = () => {
    baselineRefs.current.abort?.abort();
    optimizedRefs.current.abort?.abort();
  };

  const handleSend = (text: string) => {
    // Добавляем user-сообщение в обе истории
    const baselineHistory: Message[] = [
      ...baseline.messages,
      { role: "user", content: text },
    ];
    const optimizedHistory: Message[] = [
      ...optimized.messages,
      { role: "user", content: text },
    ];

    setBaseline({
      messages: [...baselineHistory, { role: "assistant", content: "" }],
      isLoading: true,
    });
    setOptimized({
      messages: [...optimizedHistory, { role: "assistant", content: "" }],
      isLoading: true,
    });

    // Запускаем обе стороны независимо, ничего не ждём друг от друга
    void runSide({
      config: BASELINE_CONFIG,
      history: baselineHistory,
      refs: baselineRefs.current,
      setState: setBaseline,
      selectedModel,
      provider,
      useRag,
      ragRerankMode,
    });
    void runSide({
      config: OPTIMIZED_CONFIG,
      history: optimizedHistory,
      refs: optimizedRefs.current,
      setState: setOptimized,
      selectedModel,
      provider,
      useRag,
      ragRerankMode,
    });
  };

  return (
    <div className="chat-main" style={{ display: "flex", flexDirection: "column" }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "1px",
          background: "#333",
          flex: 1,
          minHeight: 0,
          overflow: "hidden",
        }}
      >
        <SideColumn
          config={BASELINE_CONFIG}
          state={baseline}
          usage={baselineUsage}
          onStop={handleStop}
        />
        <SideColumn
          config={OPTIMIZED_CONFIG}
          state={optimized}
          usage={optimizedUsage}
          onStop={handleStop}
        />
      </div>
      <div
        style={{
          display: "flex",
          gap: "8px",
          alignItems: "center",
          padding: "4px 8px",
          borderTop: "1px solid #333",
        }}
      >
        <button
          className="memory-toggle-btn"
          onClick={handleClear}
          disabled={baseline.messages.length === 0 && optimized.messages.length === 0}
        >
          Очистить обе
        </button>
        <div style={{ flex: 1 }}>
          <MessageInput
            onSend={handleSend}
            disabled={isAnyLoading || models.length === 0}
          />
        </div>
      </div>
    </div>
  );
}

// Одна колонка: заголовок с параметрами + список сообщений + сводка по токенам
function SideColumn({
  config,
  state,
  usage,
  onStop,
}: {
  config: PlaygroundChatConfig;
  state: SideState;
  usage: { prompt: number; completion: number; total: number };
  onStop: () => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        background: "#1a1a1a",
        minHeight: 0,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "6px 10px",
          borderBottom: "1px solid #333",
          background: "#222",
        }}
      >
        <div style={{ fontSize: "12px", fontWeight: 600, color: "#eee" }}>
          {config.label}
        </div>
        <div style={{ fontSize: "11px", color: "#888" }}>{config.description}</div>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
        <MessageList
          messages={state.messages}
          isLoading={state.isLoading}
          onStop={onStop}
        />
      </div>
      {usage.total > 0 && (
        <div className="token-summary" style={{ borderTop: "1px solid #333" }}>
          <span className="token-summary-item prompt">↑ {usage.prompt}</span>
          <span className="token-summary-item completion">↓ {usage.completion}</span>
          <span className="token-summary-item total">Σ {usage.total}</span>
        </div>
      )}
    </div>
  );
}

function sumUsage(messages: Message[]) {
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
}

// Запуск стрима для одной стороны. Инкапсулирует rAF-батчинг и обновление стейта,
// чтобы колонки рендерились независимо и не мешали друг другу.
function runSide(params: {
  config: PlaygroundChatConfig;
  history: Message[];
  refs: SideRefs;
  setState: React.Dispatch<React.SetStateAction<SideState>>;
  selectedModel: string;
  provider: PlaygroundProvider;
  useRag: boolean;
  ragRerankMode: string;
}) {
  const {
    config,
    history,
    refs,
    setState,
    selectedModel,
    provider,
    useRag,
    ragRerankMode,
  } = params;

  refs.streamBuffer = "";
  refs.startTime = Date.now();
  const controller = new AbortController();
  refs.abort = controller;

  const wireMessages: PlaygroundMessage[] = history.map((m) => ({
    role: m.role as "user" | "assistant" | "system",
    content: m.content,
  }));

  // Заменяет последний ассистент-бабл в сообщениях этой стороны
  const patchLast = (patch: Partial<Message>) => {
    setState((prev) => {
      const updated = [...prev.messages];
      const last = updated[updated.length - 1];
      updated[updated.length - 1] = { ...last, ...patch };
      return { ...prev, messages: updated };
    });
  };

  const setLoading = (isLoading: boolean) => {
    setState((prev) => ({ ...prev, isLoading }));
  };

  return streamPlayground(
    {
      messages: wireMessages,
      provider,
      model: selectedModel || undefined,
      temperature: config.temperature,
      max_tokens: config.maxTokens,
      system_prompt: config.systemPrompt || undefined,
      use_rag: useRag || undefined,
      rag_rerank_mode: useRag ? ragRerankMode : undefined,
    },
    {
      onSources: (sources, lowRelevance) => {
        patchLast({ sources, lowRelevance });
      },
      onDelta: (content) => {
        refs.streamBuffer += content;
        if (refs.rafId === null) {
          refs.rafId = requestAnimationFrame(() => {
            const t = refs.streamBuffer;
            const elapsed = Date.now() - refs.startTime;
            patchLast({ content: t, responseTime: elapsed });
            refs.rafId = null;
          });
        }
      },
      onUsage: (usage) => {
        patchLast({ usage });
      },
      onDone: () => {
        if (refs.rafId !== null) {
          cancelAnimationFrame(refs.rafId);
          refs.rafId = null;
        }
        const finalContent = refs.streamBuffer;
        const elapsed = Date.now() - refs.startTime;
        patchLast({ content: finalContent, responseTime: elapsed });
        setLoading(false);
        refs.abort = null;
      },
      onError: (error) => {
        if (refs.rafId !== null) {
          cancelAnimationFrame(refs.rafId);
          refs.rafId = null;
        }
        patchLast({
          content: refs.streamBuffer || `Ошибка: ${error.message}`,
        });
        setLoading(false);
        refs.abort = null;
      },
    },
    controller.signal,
  );
}

export default PlaygroundCompareView;
