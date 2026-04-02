import { Invariant, InvariantCategory } from "../types";

// --- CRUD инвариантов ---

export async function getInvariants(): Promise<Invariant[]> {
  const res = await fetch("/api/invariants");
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}

export async function createInvariant(data: {
  name: string;
  description: string;
  category?: InvariantCategory;
  is_active?: boolean;
  priority?: number;
}): Promise<Invariant> {
  const res = await fetch("/api/invariants", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}

export async function updateInvariant(
  id: string,
  data: {
    name?: string;
    description?: string;
    category?: InvariantCategory;
    is_active?: boolean;
    priority?: number;
  }
): Promise<Invariant> {
  const res = await fetch(`/api/invariants/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}

export async function deleteInvariant(id: string): Promise<void> {
  const res = await fetch(`/api/invariants/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
}

export async function toggleInvariant(id: string): Promise<Invariant> {
  const res = await fetch(`/api/invariants/${id}/toggle`, { method: "PATCH" });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}
