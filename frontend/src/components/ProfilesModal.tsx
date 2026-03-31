import { useState, useEffect } from "react";
import { UserProfile } from "../types";
import {
  getProfiles,
  createProfile,
  updateProfile,
  deleteProfile,
} from "../api/profiles";

interface Props {
  open: boolean;
  onClose: () => void;
  onProfilesChange: () => void;
}

function ProfilesModal({ open, onClose, onProfilesChange }: Props) {
  const [profiles, setProfiles] = useState<UserProfile[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    if (open) {
      loadProfiles();
    }
  }, [open]);

  const loadProfiles = async () => {
    try {
      const data = await getProfiles();
      setProfiles(data);
    } catch {
      // Ошибка загрузки
    }
  };

  const handleCreate = async () => {
    if (!name.trim() || !systemPrompt.trim()) return;
    try {
      await createProfile({ name: name.trim(), system_prompt: systemPrompt.trim() });
      setName("");
      setSystemPrompt("");
      setIsCreating(false);
      await loadProfiles();
      onProfilesChange();
    } catch {
      // Ошибка создания
    }
  };

  const handleUpdate = async (id: string) => {
    if (!name.trim() || !systemPrompt.trim()) return;
    try {
      await updateProfile(id, { name: name.trim(), system_prompt: systemPrompt.trim() });
      setEditingId(null);
      setName("");
      setSystemPrompt("");
      await loadProfiles();
      onProfilesChange();
    } catch {
      // Ошибка обновления
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteProfile(id);
      await loadProfiles();
      onProfilesChange();
    } catch {
      // Ошибка удаления
    }
  };

  const handleSetDefault = async (id: string) => {
    try {
      await updateProfile(id, { is_default: true });
      await loadProfiles();
      onProfilesChange();
    } catch {
      // Ошибка
    }
  };

  const startEdit = (profile: UserProfile) => {
    setEditingId(profile.id);
    setName(profile.name);
    setSystemPrompt(profile.system_prompt);
    setIsCreating(false);
  };

  const startCreate = () => {
    setIsCreating(true);
    setEditingId(null);
    setName("");
    setSystemPrompt("");
  };

  const cancelEdit = () => {
    setEditingId(null);
    setIsCreating(false);
    setName("");
    setSystemPrompt("");
  };

  if (!open) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content profiles-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Профили</h2>
          <button className="modal-close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="profiles-list">
          {profiles.map((p) => (
            <div key={p.id} className={`profile-item ${p.is_default ? "profile-default" : ""}`}>
              {editingId === p.id ? (
                <div className="profile-edit-form">
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Название"
                    className="profile-name-input"
                  />
                  <textarea
                    value={systemPrompt}
                    onChange={(e) => setSystemPrompt(e.target.value)}
                    placeholder="System prompt — инструкции для LLM"
                    className="profile-prompt-textarea"
                    rows={4}
                  />
                  <div className="profile-edit-actions">
                    <button onClick={() => handleUpdate(p.id)}>Сохранить</button>
                    <button onClick={cancelEdit}>Отмена</button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="profile-info">
                    <span className="profile-name">{p.name}</span>
                    {p.is_default && <span className="profile-badge">по умолчанию</span>}
                  </div>
                  <div className="profile-prompt-preview">
                    {p.system_prompt.length > 100
                      ? p.system_prompt.slice(0, 100) + "..."
                      : p.system_prompt}
                  </div>
                  <div className="profile-actions">
                    <button onClick={() => startEdit(p)}>Редактировать</button>
                    {!p.is_default && (
                      <button onClick={() => handleSetDefault(p.id)}>По умолчанию</button>
                    )}
                    <button className="btn-danger" onClick={() => handleDelete(p.id)}>
                      Удалить
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
          {profiles.length === 0 && !isCreating && (
            <div className="profiles-empty">Нет профилей</div>
          )}
        </div>

        {isCreating ? (
          <div className="profile-create-form">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Название профиля"
              className="profile-name-input"
            />
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="System prompt — инструкции для LLM (стиль, формат, ограничения)"
              className="profile-prompt-textarea"
              rows={4}
            />
            <div className="profile-edit-actions">
              <button onClick={handleCreate}>Создать</button>
              <button onClick={cancelEdit}>Отмена</button>
            </div>
          </div>
        ) : (
          <button className="profile-add-btn" onClick={startCreate}>
            + Новый профиль
          </button>
        )}
      </div>
    </div>
  );
}

export default ProfilesModal;
