/**
 * API-клиент для модуля индексации документов.
 */

import type {
  IndexedDocument,
  IndexResult,
  SearchResponse,
  CompareResponse,
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

/** Семантический поиск по проиндексированным документам */
export async function searchDocuments(
  query: string,
  topK: number = 5
): Promise<SearchResponse> {
  const res = await fetch("/api/indexing/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
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
