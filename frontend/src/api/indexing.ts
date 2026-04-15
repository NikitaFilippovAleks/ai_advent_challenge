/**
 * API-клиент для модуля индексации документов.
 */

import type {
  IndexedDocument,
  IndexResult,
  SearchResponse,
  CompareResponse,
  RerankCompareResponse,
  RerankMode,
} from "../types";

/** Индексирует документы указанной стратегией */
export async function indexDocuments(
  paths: string[],
  strategy: string = "fixed_size"
): Promise<IndexResult[]> {
  const res = await fetch("/api/indexing/index", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths, strategy }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Ошибка индексации");
  }
  return res.json();
}

/** Семантический поиск по проиндексированным документам с опциональным реранкингом */
export async function searchDocuments(
  query: string,
  topK: number = 5,
  rerankMode: RerankMode = "none",
  scoreThreshold: number = 0.0,
  topKInitial: number = 20,
  topKFinal: number = 5,
  rewriteQuery: boolean = false
): Promise<SearchResponse> {
  const res = await fetch("/api/indexing/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      top_k: topK,
      rerank_mode: rerankMode,
      score_threshold: scoreThreshold,
      top_k_initial: topKInitial,
      top_k_final: topKFinal,
      rewrite_query: rewriteQuery,
    }),
  });
  if (!res.ok) throw new Error("Ошибка поиска");
  return res.json();
}

/** Список проиндексированных документов */
export async function listDocuments(): Promise<IndexedDocument[]> {
  const res = await fetch("/api/indexing/documents");
  if (!res.ok) throw new Error("Не удалось загрузить документы");
  return res.json();
}

/** Удалить проиндексированный документ */
export async function deleteDocument(docId: string): Promise<void> {
  const res = await fetch(`/api/indexing/documents/${encodeURIComponent(docId)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Не удалось удалить документ");
}

/** Сравнение режимов переранжирования */
export async function compareReranking(
  query: string,
  topKInitial: number = 20,
  topKFinal: number = 5,
  scoreThreshold: number = 0.0,
  rewriteQuery: boolean = false
): Promise<RerankCompareResponse> {
  const res = await fetch("/api/indexing/rerank-compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      top_k_initial: topKInitial,
      top_k_final: topKFinal,
      score_threshold: scoreThreshold,
      rewrite_query: rewriteQuery,
    }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Ошибка сравнения реранкинга");
  }
  return res.json();
}

/** Сравнение двух стратегий разбиения */
export async function compareStrategies(
  paths: string[],
  query: string,
  topK: number = 5
): Promise<CompareResponse> {
  const res = await fetch("/api/indexing/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths, query, top_k: topK }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Ошибка сравнения");
  }
  return res.json();
}
