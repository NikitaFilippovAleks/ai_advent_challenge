import { useState } from "react";
import { ToolEvent } from "../types";

interface Props {
  events: ToolEvent[];
}

// Отображает MCP tool calls в стиле Claude Code:
// компактный блок с именем инструмента, аргументами и сворачиваемым результатом
function ToolCallBlock({ events }: Props) {
  return (
    <div className="tool-calls-container">
      {events.map((event, i) => {
        if (event.type === "call") {
          // Ищем результат для этого вызова
          const resultEvent = events.find(
            (e, j) => j > i && e.type === "result" && e.name === event.name
          );
          return (
            <ToolCallItem
              key={i}
              name={event.name}
              arguments={event.arguments}
              result={resultEvent?.content}
              isRunning={!resultEvent}
            />
          );
        }
        return null; // результаты рендерятся вместе с вызовами
      })}
    </div>
  );
}

function ToolCallItem({
  name,
  arguments: args,
  result,
  isRunning,
}: {
  name: string;
  arguments?: Record<string, unknown>;
  result?: string;
  isRunning: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  // Сокращаем длинные аргументы
  const argsPreview = args
    ? Object.entries(args)
        .map(([k, v]) => {
          const val =
            typeof v === "string"
              ? v.length > 60
                ? v.slice(0, 60) + "…"
                : v
              : JSON.stringify(v);
          return `${k}: ${val}`;
        })
        .join(", ")
    : "";

  // Сокращаем результат для превью
  const resultPreview = result
    ? result.length > 120
      ? result.slice(0, 120) + "…"
      : result
    : "";

  return (
    <div className={`tool-call-item ${isRunning ? "running" : "completed"}`}>
      <div
        className="tool-call-header"
        onClick={() => result && setExpanded(!expanded)}
      >
        <span className="tool-call-icon">{isRunning ? "⏳" : "✓"}</span>
        <span className="tool-call-name">{name}</span>
        {argsPreview && (
          <span className="tool-call-args">({argsPreview})</span>
        )}
        {result && (
          <span className="tool-call-expand">{expanded ? "▼" : "▶"}</span>
        )}
      </div>
      {!isRunning && !expanded && resultPreview && (
        <div className="tool-call-preview">{resultPreview}</div>
      )}
      {expanded && result && (
        <pre className="tool-call-result">{result}</pre>
      )}
    </div>
  );
}

export default ToolCallBlock;
