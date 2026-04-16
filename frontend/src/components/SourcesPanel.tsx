import { RAGSource } from "../types";

interface Props {
  sources: RAGSource[];
  lowRelevance?: boolean;
}

// Панель отображения RAG-источников, использованных при генерации ответа
function SourcesPanel({ sources, lowRelevance }: Props) {
  if (sources.length === 0) return null;

  return (
    <div className="sources-panel">
      {lowRelevance && (
        <div className="sources-warning">
          ⚠ Низкая релевантность источников — ответ может быть неточным
        </div>
      )}
      <div className="sources-header">
        Источники ({sources.length})
      </div>
      <div className="sources-list">
        {sources.map((s, i) => (
          <div key={i} className="source-item">
            <div className="source-meta">
              <span className="source-index">[Источник {i + 1}]</span>
              <span className="source-file">{s.source}</span>
              {s.section && <span className="source-section">{s.section}</span>}
              {s.original_score != null && (
                <span className="source-score" style={{ opacity: 0.6 }} title="Cosine similarity">
                  cos:{(s.original_score * 100).toFixed(0)}%
                </span>
              )}
              <span className="source-score" title="Итоговый score">{(s.score * 100).toFixed(0)}%</span>
            </div>
            <div className="source-content">{s.content}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default SourcesPanel;
