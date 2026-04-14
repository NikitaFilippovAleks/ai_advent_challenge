import { RAGSource } from "../types";

interface Props {
  sources: RAGSource[];
}

// Панель отображения RAG-источников, использованных при генерации ответа
function SourcesPanel({ sources }: Props) {
  if (sources.length === 0) return null;

  return (
    <div className="sources-panel">
      <div className="sources-header">
        Источники ({sources.length})
      </div>
      <div className="sources-list">
        {sources.map((s, i) => (
          <div key={i} className="source-item">
            <div className="source-meta">
              <span className="source-file">{s.source}</span>
              {s.section && <span className="source-section">{s.section}</span>}
              <span className="source-score">{(s.score * 100).toFixed(0)}%</span>
            </div>
            <div className="source-content">{s.content}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default SourcesPanel;
