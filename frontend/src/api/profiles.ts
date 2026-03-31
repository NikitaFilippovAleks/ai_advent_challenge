import { UserProfile, ConversationProfileInfo } from "../types";

// --- CRUD профилей ---

export async function getProfiles(): Promise<UserProfile[]> {
  const res = await fetch("/api/profiles");
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}

export async function createProfile(data: {
  name: string;
  system_prompt: string;
  is_default?: boolean;
}): Promise<UserProfile> {
  const res = await fetch("/api/profiles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}

export async function updateProfile(
  id: string,
  data: { name?: string; system_prompt?: string; is_default?: boolean }
): Promise<UserProfile> {
  const res = await fetch(`/api/profiles/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}

export async function deleteProfile(id: string): Promise<void> {
  const res = await fetch(`/api/profiles/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
}

export async function getDefaultProfile(): Promise<UserProfile | null> {
  const res = await fetch("/api/profiles/default");
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}

// --- Профиль диалога ---

export async function getConversationProfile(
  conversationId: string
): Promise<ConversationProfileInfo> {
  const res = await fetch(`/api/conversations/${conversationId}/profile`);
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
  return res.json();
}

export async function setConversationProfile(
  conversationId: string,
  profileId: string | null
): Promise<void> {
  const res = await fetch(`/api/conversations/${conversationId}/profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile_id: profileId }),
  });
  if (!res.ok) throw new Error(`Ошибка: ${res.status}`);
}
