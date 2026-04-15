/**
 * Панель индексации документов: индексация, поиск, сравнение стратегий.
 */

import { useState, useEffect, useCallback } from "react";
import type {
  IndexedDocument,
  IndexResult,
  SearchResult,
  SearchResponse,
  CompareResponse,
  RerankCompareResponse,
  RerankMode,
} from "../types";
import {
  indexDocuments,
  searchDocuments,
  listDocuments,
  deleteDocument,
  compareStrategies,
  compareReranking,
} from "../api/indexing";

// Файлы проекта для индексации по умолчанию
const DEFAULT_PATHS = [
  "/repo/.claude/CLAUDE.md",
  "/repo/.claude/rules/architecture.md",
  "/repo/.claude/rules/stack.md",
  "/repo/.claude/rules/code-style.md",
  "/repo/README.md",
  "/repo/backend/app/main.py",
  "/repo/backend/app/models.py",
  "/repo/backend/app/shared/llm/gigachat.py",
  "/repo/backend/app/shared/llm/base.py",
  "/repo/backend/app/modules/chat/service.py",
  "/repo/backend/app/modules/context/service.py",
];

// Активная вкладка панели
type Tab = "index" | "search" | "compare" | "rerank";

export default function IndexingPanel() {
  const [activeTab, setActiveTab] = useState<Tab>("index");
  const [documents, setDocuments] = useState<IndexedDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // --- Состояние вкладки «Индексация» ---
  const [indexPaths, setIndexPaths] = useState(DEFAULT_PATHS.join("\n"));
  const [indexStrategy, setIndexStrategy] = useState("fixed_size");
  const [indexResults, setIndexResults] = useState<IndexResult[] | null>(null);

  // --- Состояние вкладки «Поиск» ---
  const [searchQuery, setSearchQuery] = useState("");
  const [searchTopK] = useState(5);
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null);
  const [rerankMode, setRerankMode] = useState<RerankMode>("none");
  const [scoreThreshold, setScoreThreshold] = useState(0.0);
  const [topKInitial, setTopKInitial] = useState(20);
  const [topKFinal, setTopKFinal] = useState(5);
  const [rewriteQuery, setRewriteQuery] = useState(false);

  // --- Состояние вкладки «Сравнение» ---
  const [comparePaths, setComparePaths] = useState(DEFAULT_PATHS.slice(0, 5).join("\n"));
  const [compareQuery, setCompareQuery] = useState("");
  const [compareResult, setCompareResult] = useState<CompareResponse | null>(null);

  // --- Состояние вкладки «Реранкинг» ---
  const [rerankQuery, setRerankQuery] = useState("");
  const [rerankThreshold, setRerankThreshold] = useState(0.1);
  const [rerankTopKInitial, setRerankTopKInitial] = useState(20);
  const [rerankTopKFinal, setRerankTopKFinal] = useState(5);
  const [rerankRewrite, setRerankRewrite] = useState(false);
  const [rerankResult, setRerankResult] = useState<RerankCompareResponse | null>(null);

  const refresh = useCallback(async () => {
    try {
      const docs = await listDocuments();
      setDocuments(docs);
    } catch {
      // Тихо — список документов вторичен
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // --- Обработчики ---

  const handleIndex = async () => {
    const paths = indexPaths.split("\n").map((p) => p.trim()).filter(Boolean);
    if (!paths.length) return;

    setLoading(true);
    setError(null);
    setIndexResults(null);
    try {
      const results = await indexDocuments(paths, indexStrategy);
      setIndexResults(results);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка индексации");
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;

    setLoading(true);
    setError(null);
    setSearchResults(null);
    setSearchResponse(null);
    try {
      const resp = await searchDocuments(
        searchQuery.trim(),
        searchTopK,
        rerankMode,
        scoreThreshold,
        topKInitial,
        topKFinal,
        rewriteQuery,
      );
      setSearchResults(resp.results);
      setSearchResponse(resp);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка поиска");
    } finally {
      setLoading(false);
    }
  };

  const handleCompare = async () => {
    const paths = comparePaths.split("\n").map((p) => p.trim()).filter(Boolean);
    if (!paths.length || !compareQuery.trim()) return;

    setLoading(true);
    setError(null);
    setCompareResult(null);
    try {
      const resp = await compareStrategies(paths, compareQuery.trim(), searchTopK);
      setCompareResult(resp);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка сравнения");
    } finally {
      setLoading(false);
    }
  };

  const handleRerankCompare = async () => {
    if (!rerankQuery.trim()) return;

    setLoading(true);
    setError(null);
    setRerankResult(null);
    try {
      const resp = await compareReranking(
        rerankQuery.trim(),
        rerankTopKInitial,
        rerankTopKFinal,
        rerankThreshold,
        rerankRewrite,
      );
      setRerankResult(resp);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка сравнения реранкинга");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (docId: string) => {
    setLoading(true);
    try {
      await deleteDocument(docId);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка удаления");
    } finally {
      setLoading(false);
    }
  };

  // --- Рендер ---

  const tabStyle = (tab: Tab) => ({
    padding: "6px 14px",
    border: "none",
    borderBottom: activeTab === tab ? "2px solid #4caf50" : "2px solid transparent",
    background: "transparent",
    color: activeTab === tab ? "#4caf50" : "#999",
    cursor: "pointer" as const,
    fontSize: "13px",
    fontWeight: activeTab === tab ? 600 : 400,
  });

  return (
    <div style={{ padding: "8px", color: "#ccc", fontSize: "13px" }}>
      <h3 style={{ margin: "0 0 8px", color: "#fff", fontSize: "14px" }}>
        Индексация документов
      </h3>

      {/* Вкладки */}
      <div style={{ display: "flex", gap: "2px", marginBottom: "10px", borderBottom: "1px solid #444" }}>
        <button style={tabStyle("index")} onClick={() => setActiveTab("index")}>Индексация</button>
        <button style={tabStyle("search")} onClick={() => setActiveTab("search")}>Поиск</button>
        <button style={tabStyle("compare")} onClick={() => setActiveTab("compare")}>Сравнение</button>
        <button style={tabStyle("rerank")} onClick={() => setActiveTab("rerank")}>Реранкинг</button>
      </div>

      {error && (
        <div style={{ color: "#ff6b6b", marginBottom: "8px", fontSize: "12px" }}>
          {error}
        </div>
      )}

      {/* ===== ВКЛАДКА: Индексация ===== */}
      {activeTab === "index" && (
        <div>
          <label style={{ display: "block", marginBottom: "4px", color: "#aaa", fontSize: "12px" }}>
            Пути к файлам (по одному на строку):
          </label>
          <textarea
            value={indexPaths}
            onChange={(e) => setIndexPaths(e.target.value)}
            rows={6}
            style={{
              width: "100%",
              background: "#1e1e1e",
              color: "#ccc",
              border: "1px solid #444",
              borderRadius: "4px",
              padding: "6px",
              fontSize: "11px",
              fontFamily: "monospace",
              resize: "vertical",
              boxSizing: "border-box",
            }}
          />

          <div style={{ display: "flex", gap: "8px", alignItems: "center", margin: "8px 0" }}>
            <label style={{ color: "#aaa", fontSize: "12px" }}>Стратегия:</label>
            <select
              value={indexStrategy}
              onChange={(e) => setIndexStrategy(e.target.value)}
              style={{
                background: "#1e1e1e",
                color: "#ccc",
                border: "1px solid #444",
                borderRadius: "4px",
                padding: "4px 8px",
                fontSize: "12px",
              }}
            >
              <option value="fixed_size">Фиксированный размер</option>
              <option value="structural">Структурная</option>
            </select>
            <button
              onClick={handleIndex}
              disabled={loading}
              style={{
                background: "#4caf50",
                color: "#fff",
                border: "none",
                borderRadius: "4px",
                padding: "5px 14px",
                cursor: loading ? "wait" : "pointer",
                fontSize: "12px",
                opacity: loading ? 0.7 : 1,
              }}
            >
              {loading ? "Индексация..." : "Индексировать"}
            </button>
          </div>

          {/* Результат индексации */}
          {indexResults && (
            <div style={{ marginTop: "8px" }}>
              <div style={{ color: "#4caf50", fontSize: "12px", marginBottom: "4px" }}>
                Проиндексировано файлов: {indexResults.length}
              </div>
              {indexResults.map((r) => (
                <div
                  key={r.document_id}
                  style={{
                    background: "#1e1e1e",
                    padding: "6px 8px",
                    borderRadius: "4px",
                    marginBottom: "4px",
                    fontSize: "11px",
                  }}
                >
                  <span style={{ color: "#fff" }}>{r.filename.split("/").pop()}</span>
                  <span style={{ color: "#888", marginLeft: "8px" }}>
                    {r.chunk_count} чанков • {r.strategy}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Список документов */}
          {documents.length > 0 && (
            <div style={{ marginTop: "12px" }}>
              <div style={{ color: "#aaa", fontSize: "12px", marginBottom: "4px" }}>
                Проиндексированные документы ({documents.length}):
              </div>
              {documents.map((doc) => (
                <div
                  key={doc.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    background: "#1e1e1e",
                    padding: "5px 8px",
                    borderRadius: "4px",
                    marginBottom: "3px",
                    fontSize: "11px",
                  }}
                >
                  <div>
                    <span style={{ color: "#fff" }}>{doc.title}</span>
                    <span style={{
                      color: doc.chunking_strategy === "structural" ? "#ff9800" : "#64b5f6",
                      marginLeft: "6px",
                      fontSize: "10px",
                    }}>
                      {doc.chunking_strategy === "structural" ? "структ." : "фикс."}
                    </span>
                    <span style={{ color: "#888", marginLeft: "6px" }}>
                      {doc.chunk_count} чанков
                    </span>
                  </div>
                  <button
                    onClick={() => handleDelete(doc.id)}
                    disabled={loading}
                    style={{
                      background: "transparent",
                      color: "#ff6b6b",
                      border: "none",
                      cursor: "pointer",
                      fontSize: "12px",
                      padding: "0 4px",
                    }}
                    title="Удалить"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ===== ВКЛАДКА: Поиск ===== */}
      {activeTab === "search" && (
        <div>
          <div style={{ display: "flex", gap: "6px", marginBottom: "8px" }}>
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="Поисковый запрос..."
              style={{
                flex: 1,
                background: "#1e1e1e",
                color: "#ccc",
                border: "1px solid #444",
                borderRadius: "4px",
                padding: "6px 8px",
                fontSize: "12px",
              }}
            />
            <button
              onClick={handleSearch}
              disabled={loading || !searchQuery.trim()}
              style={{
                background: "#4caf50",
                color: "#fff",
                border: "none",
                borderRadius: "4px",
                padding: "5px 14px",
                cursor: loading ? "wait" : "pointer",
                fontSize: "12px",
                opacity: loading || !searchQuery.trim() ? 0.7 : 1,
              }}
            >
              {loading ? "..." : "Найти"}
            </button>
          </div>

          {/* Настройки реранкинга */}
          <div style={{
            background: "#1a1a1a",
            padding: "8px",
            borderRadius: "4px",
            marginBottom: "8px",
            fontSize: "11px",
          }}>
            <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
              <label style={{ color: "#aaa" }}>Реранкинг:</label>
              <select
                value={rerankMode}
                onChange={(e) => setRerankMode(e.target.value as RerankMode)}
                style={{
                  background: "#1e1e1e",
                  color: "#ccc",
                  border: "1px solid #444",
                  borderRadius: "4px",
                  padding: "3px 6px",
                  fontSize: "11px",
                }}
              >
                <option value="none">Без реранкинга</option>
                <option value="threshold">Порог отсечения</option>
                <option value="keyword">Keyword overlap</option>
                <option value="llm_cross_encoder">LLM cross-encoder</option>
              </select>

              <label style={{ color: "#aaa" }}>Порог:</label>
              <input
                type="number"
                value={scoreThreshold}
                onChange={(e) => setScoreThreshold(Number(e.target.value))}
                min={0}
                max={1}
                step={0.05}
                style={{
                  width: "55px",
                  background: "#1e1e1e",
                  color: "#ccc",
                  border: "1px solid #444",
                  borderRadius: "4px",
                  padding: "3px 6px",
                  fontSize: "11px",
                  textAlign: "center",
                }}
              />

              <label style={{ color: "#aaa" }}>top_k до:</label>
              <input
                type="number"
                value={topKInitial}
                onChange={(e) => setTopKInitial(Number(e.target.value))}
                min={1}
                max={50}
                style={{
                  width: "40px",
                  background: "#1e1e1e",
                  color: "#ccc",
                  border: "1px solid #444",
                  borderRadius: "4px",
                  padding: "3px 6px",
                  fontSize: "11px",
                  textAlign: "center",
                }}
              />

              <label style={{ color: "#aaa" }}>после:</label>
              <input
                type="number"
                value={topKFinal}
                onChange={(e) => setTopKFinal(Number(e.target.value))}
                min={1}
                max={20}
                style={{
                  width: "40px",
                  background: "#1e1e1e",
                  color: "#ccc",
                  border: "1px solid #444",
                  borderRadius: "4px",
                  padding: "3px 6px",
                  fontSize: "11px",
                  textAlign: "center",
                }}
              />
            </div>
            <div style={{ display: "flex", gap: "8px", alignItems: "center", marginTop: "6px" }}>
              <label style={{ color: "#aaa", display: "flex", alignItems: "center", gap: "4px", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={rewriteQuery}
                  onChange={(e) => setRewriteQuery(e.target.checked)}
                />
                Переписать запрос через LLM
              </label>
            </div>
          </div>

          {/* Мета-информация о поиске */}
          {searchResponse && (
            <div style={{ fontSize: "11px", color: "#aaa", marginBottom: "6px" }}>
              {searchResponse.rewritten_query && (
                <div style={{ marginBottom: "3px" }}>
                  Переписанный запрос: <span style={{ color: "#64b5f6" }}>{searchResponse.rewritten_query}</span>
                </div>
              )}
              <div>
                Найдено: {searchResults?.length ?? 0} результатов
                {searchResponse.rerank_mode !== "none" && (
                  <span style={{ marginLeft: "8px" }}>
                    | Режим: <span style={{ color: "#ff9800" }}>{searchResponse.rerank_mode}</span>
                    {(searchResponse.filtered_count ?? 0) > 0 && (
                      <span> | Отфильтровано: {searchResponse.filtered_count}</span>
                    )}
                  </span>
                )}
              </div>
            </div>
          )}

          {searchResults && searchResults.length > 0 && (
            <div>
              {searchResults.map((r, i) => (
                <div
                  key={r.chunk_id}
                  style={{
                    background: "#1e1e1e",
                    padding: "8px",
                    borderRadius: "4px",
                    marginBottom: "6px",
                    borderLeft: `3px solid ${scoreColor(r.score)}`,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                    <span style={{ color: "#fff", fontSize: "12px" }}>
                      #{i + 1} {r.source.split("/").pop()}
                      {r.section && (
                        <span style={{ color: "#ff9800", marginLeft: "6px" }}>
                          [{r.section}]
                        </span>
                      )}
                    </span>
                    <div style={{ display: "flex", gap: "6px", fontSize: "11px" }}>
                      {r.original_score != null && (
                        <span style={{ color: "#888" }} title="Cosine similarity">
                          cos: {(r.original_score * 100).toFixed(1)}%
                        </span>
                      )}
                      {r.rerank_score != null && (
                        <span style={{ color: "#64b5f6" }} title="Rerank score">
                          rr: {(r.rerank_score * 100).toFixed(1)}%
                        </span>
                      )}
                      <span style={{
                        color: scoreColor(r.score),
                        fontWeight: 600,
                      }}>
                        {(r.score * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                  <div style={{
                    color: "#bbb",
                    fontSize: "11px",
                    lineHeight: "1.4",
                    maxHeight: "80px",
                    overflow: "hidden",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                  }}>
                    {r.content.slice(0, 300)}{r.content.length > 300 ? "..." : ""}
                  </div>
                </div>
              ))}
            </div>
          )}

          {searchResults && searchResults.length === 0 && (
            <div style={{ color: "#888", fontSize: "12px", textAlign: "center", padding: "20px" }}>
              Ничего не найдено. Попробуйте другой запрос или проиндексируйте документы.
            </div>
          )}
        </div>
      )}

      {/* ===== ВКЛАДКА: Сравнение ===== */}
      {activeTab === "compare" && (
        <div>
          <label style={{ display: "block", marginBottom: "4px", color: "#aaa", fontSize: "12px" }}>
            Пути к файлам для сравнения:
          </label>
          <textarea
            value={comparePaths}
            onChange={(e) => setComparePaths(e.target.value)}
            rows={4}
            style={{
              width: "100%",
              background: "#1e1e1e",
              color: "#ccc",
              border: "1px solid #444",
              borderRadius: "4px",
              padding: "6px",
              fontSize: "11px",
              fontFamily: "monospace",
              resize: "vertical",
              boxSizing: "border-box",
            }}
          />

          <div style={{ display: "flex", gap: "6px", margin: "8px 0" }}>
            <input
              value={compareQuery}
              onChange={(e) => setCompareQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCompare()}
              placeholder="Запрос для сравнения..."
              style={{
                flex: 1,
                background: "#1e1e1e",
                color: "#ccc",
                border: "1px solid #444",
                borderRadius: "4px",
                padding: "6px 8px",
                fontSize: "12px",
              }}
            />
            <button
              onClick={handleCompare}
              disabled={loading || !compareQuery.trim()}
              style={{
                background: "#ff9800",
                color: "#fff",
                border: "none",
                borderRadius: "4px",
                padding: "5px 14px",
                cursor: loading ? "wait" : "pointer",
                fontSize: "12px",
                opacity: loading || !compareQuery.trim() ? 0.7 : 1,
              }}
            >
              {loading ? "Сравнение..." : "Сравнить"}
            </button>
          </div>

          {compareResult && (
            <div>
              <div style={{ color: "#aaa", fontSize: "12px", marginBottom: "8px" }}>
                Запрос: «{compareResult.query}»
              </div>
              <div style={{ display: "flex", gap: "8px" }}>
                {compareResult.strategies.map((s) => (
                  <div
                    key={s.strategy}
                    style={{
                      flex: 1,
                      background: "#1e1e1e",
                      padding: "8px",
                      borderRadius: "4px",
                      borderTop: `3px solid ${s.strategy === "structural" ? "#ff9800" : "#64b5f6"}`,
                    }}
                  >
                    <div style={{
                      color: s.strategy === "structural" ? "#ff9800" : "#64b5f6",
                      fontSize: "12px",
                      fontWeight: 600,
                      marginBottom: "6px",
                    }}>
                      {s.strategy === "structural" ? "Структурная" : "Фиксированный размер"}
                    </div>
                    <div style={{ fontSize: "11px", color: "#aaa", marginBottom: "8px" }}>
                      <div>Чанков: <b style={{ color: "#fff" }}>{s.chunk_count}</b></div>
                      <div>Средняя длина: <b style={{ color: "#fff" }}>{s.avg_chunk_length.toFixed(0)}</b> симв.</div>
                    </div>
                    <div style={{ fontSize: "11px", color: "#aaa", marginBottom: "4px" }}>
                      Топ результаты:
                    </div>
                    {s.results.map((r, i) => (
                      <div
                        key={r.chunk_id}
                        style={{
                          background: "#2a2a2a",
                          padding: "5px 6px",
                          borderRadius: "3px",
                          marginBottom: "4px",
                          borderLeft: `2px solid ${scoreColor(r.score)}`,
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span style={{ color: "#ddd", fontSize: "10px" }}>
                            #{i + 1} {r.source.split("/").pop()}
                            {r.section && (
                              <span style={{ color: "#ff9800" }}> [{r.section}]</span>
                            )}
                          </span>
                          <span style={{ color: scoreColor(r.score), fontSize: "10px", fontWeight: 600 }}>
                            {(r.score * 100).toFixed(1)}%
                          </span>
                        </div>
                        <div style={{
                          color: "#999",
                          fontSize: "10px",
                          marginTop: "3px",
                          maxHeight: "40px",
                          overflow: "hidden",
                          whiteSpace: "pre-wrap",
                          wordBreak: "break-word",
                        }}>
                          {r.content.slice(0, 150)}{r.content.length > 150 ? "..." : ""}
                        </div>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ===== ВКЛАДКА: Реранкинг ===== */}
      {activeTab === "rerank" && (
        <div>
          <div style={{ display: "flex", gap: "6px", marginBottom: "8px" }}>
            <input
              value={rerankQuery}
              onChange={(e) => setRerankQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleRerankCompare()}
              placeholder="Запрос для сравнения режимов..."
              style={{
                flex: 1,
                background: "#1e1e1e",
                color: "#ccc",
                border: "1px solid #444",
                borderRadius: "4px",
                padding: "6px 8px",
                fontSize: "12px",
              }}
            />
            <button
              onClick={handleRerankCompare}
              disabled={loading || !rerankQuery.trim()}
              style={{
                background: "#9c27b0",
                color: "#fff",
                border: "none",
                borderRadius: "4px",
                padding: "5px 14px",
                cursor: loading ? "wait" : "pointer",
                fontSize: "12px",
                opacity: loading || !rerankQuery.trim() ? 0.7 : 1,
              }}
            >
              {loading ? "Сравнение..." : "Сравнить"}
            </button>
          </div>

          {/* Настройки */}
          <div style={{
            background: "#1a1a1a",
            padding: "8px",
            borderRadius: "4px",
            marginBottom: "8px",
            fontSize: "11px",
            display: "flex",
            gap: "8px",
            alignItems: "center",
            flexWrap: "wrap",
          }}>
            <label style={{ color: "#aaa" }}>Порог:</label>
            <input
              type="number"
              value={rerankThreshold}
              onChange={(e) => setRerankThreshold(Number(e.target.value))}
              min={0}
              max={1}
              step={0.05}
              style={{
                width: "55px",
                background: "#1e1e1e",
                color: "#ccc",
                border: "1px solid #444",
                borderRadius: "4px",
                padding: "3px 6px",
                fontSize: "11px",
                textAlign: "center",
              }}
            />
            <label style={{ color: "#aaa" }}>top_k до:</label>
            <input
              type="number"
              value={rerankTopKInitial}
              onChange={(e) => setRerankTopKInitial(Number(e.target.value))}
              min={1}
              max={50}
              style={{
                width: "40px",
                background: "#1e1e1e",
                color: "#ccc",
                border: "1px solid #444",
                borderRadius: "4px",
                padding: "3px 6px",
                fontSize: "11px",
                textAlign: "center",
              }}
            />
            <label style={{ color: "#aaa" }}>после:</label>
            <input
              type="number"
              value={rerankTopKFinal}
              onChange={(e) => setRerankTopKFinal(Number(e.target.value))}
              min={1}
              max={20}
              style={{
                width: "40px",
                background: "#1e1e1e",
                color: "#ccc",
                border: "1px solid #444",
                borderRadius: "4px",
                padding: "3px 6px",
                fontSize: "11px",
                textAlign: "center",
              }}
            />
            <label style={{ color: "#aaa", display: "flex", alignItems: "center", gap: "4px", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={rerankRewrite}
                onChange={(e) => setRerankRewrite(e.target.checked)}
              />
              Переписать запрос
            </label>
          </div>

          {/* Результаты сравнения */}
          {rerankResult && (
            <div>
              <div style={{ color: "#aaa", fontSize: "12px", marginBottom: "4px" }}>
                Запрос: «{rerankResult.query}»
                {rerankResult.rewritten_query && (
                  <span style={{ marginLeft: "8px", color: "#64b5f6" }}>
                    (переписан: «{rerankResult.rewritten_query}»)
                  </span>
                )}
              </div>
              <div style={{ display: "flex", gap: "6px", overflowX: "auto" }}>
                {Object.entries(rerankResult.modes).map(([mode, resp]) => {
                  const modeColors: Record<string, string> = {
                    none: "#888",
                    threshold: "#ff9800",
                    keyword: "#4caf50",
                  };
                  const modeLabels: Record<string, string> = {
                    none: "Без реранкинга",
                    threshold: "Порог",
                    keyword: "Keyword",
                  };
                  return (
                    <div
                      key={mode}
                      style={{
                        flex: 1,
                        minWidth: "200px",
                        background: "#1e1e1e",
                        padding: "8px",
                        borderRadius: "4px",
                        borderTop: `3px solid ${modeColors[mode] || "#666"}`,
                      }}
                    >
                      <div style={{
                        color: modeColors[mode] || "#666",
                        fontSize: "12px",
                        fontWeight: 600,
                        marginBottom: "4px",
                      }}>
                        {modeLabels[mode] || mode}
                      </div>
                      <div style={{ fontSize: "10px", color: "#aaa", marginBottom: "6px" }}>
                        Результатов: {resp.results.length}
                        {(resp.filtered_count ?? 0) > 0 && (
                          <span> | Отфильтровано: {resp.filtered_count}</span>
                        )}
                      </div>
                      {resp.results.map((r, i) => (
                        <div
                          key={r.chunk_id}
                          style={{
                            background: "#2a2a2a",
                            padding: "5px 6px",
                            borderRadius: "3px",
                            marginBottom: "4px",
                            borderLeft: `2px solid ${scoreColor(r.score)}`,
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between" }}>
                            <span style={{ color: "#ddd", fontSize: "10px" }}>
                              #{i + 1} {r.source.split("/").pop()}
                              {r.section && (
                                <span style={{ color: "#ff9800" }}> [{r.section}]</span>
                              )}
                            </span>
                            <div style={{ display: "flex", gap: "4px", fontSize: "10px" }}>
                              {r.original_score != null && (
                                <span style={{ color: "#888" }}>{(r.original_score * 100).toFixed(1)}%</span>
                              )}
                              <span style={{ color: scoreColor(r.score), fontWeight: 600 }}>
                                {(r.score * 100).toFixed(1)}%
                              </span>
                            </div>
                          </div>
                          <div style={{
                            color: "#999",
                            fontSize: "10px",
                            marginTop: "3px",
                            maxHeight: "40px",
                            overflow: "hidden",
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-word",
                          }}>
                            {r.content.slice(0, 150)}{r.content.length > 150 ? "..." : ""}
                          </div>
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Цвет оценки релевантности */
function scoreColor(score: number): string {
  if (score >= 0.3) return "#4caf50";
  if (score >= 0.15) return "#ff9800";
  return "#888";
}
