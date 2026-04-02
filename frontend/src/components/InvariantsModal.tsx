import { useState, useEffect } from "react";
import { Invariant, InvariantCategory } from "../types";
import {
  getInvariants,
  createInvariant,
  updateInvariant,
  deleteInvariant,
  toggleInvariant,
} from "../api/invariants";

interface Props {
  open: boolean;
  onClose: () => void;
}

// Маппинг категорий на русские названия
const CATEGORY_LABELS: Record<InvariantCategory, string> = {
  architecture: "Архитектура",
  technical: "Технические",
  stack: "Стек",
  business: "Бизнес",
};

function InvariantsModal({ open, onClose }: Props) {
  const [invariants, setInvariants] = useState<Invariant[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  // Поля формы
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<InvariantCategory>("business");
  const [priority, setPriority] = useState(0);

  useEffect(() => {
    if (open) {
      loadInvariants();
    }
  }, [open]);

  const loadInvariants = async () => {
    try {
      const data = await getInvariants();
      setInvariants(data);
    } catch {
      // Ошибка загрузки
    }
  };

  const handleCreate = async () => {
    if (!name.trim() || !description.trim()) return;
    try {
      await createInvariant({
        name: name.trim(),
        description: description.trim(),
        category,
        priority,
      });
      resetForm();
      setIsCreating(false);
      await loadInvariants();
    } catch {
      // Ошибка создания
    }
  };

  const handleUpdate = async (id: string) => {
    if (!name.trim() || !description.trim()) return;
    try {
      await updateInvariant(id, {
        name: name.trim(),
        description: description.trim(),
        category,
        priority,
      });
      resetForm();
      setEditingId(null);
      await loadInvariants();
    } catch {
      // Ошибка обновления
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteInvariant(id);
      await loadInvariants();
    } catch {
      // Ошибка удаления
    }
  };

  const handleToggle = async (id: string) => {
    try {
      await toggleInvariant(id);
      await loadInvariants();
    } catch {
      // Ошибка переключения
    }
  };

  const startEdit = (inv: Invariant) => {
    setEditingId(inv.id);
    setName(inv.name);
    setDescription(inv.description);
    setCategory(inv.category);
    setPriority(inv.priority);
    setIsCreating(false);
  };

  const startCreate = () => {
    setIsCreating(true);
    setEditingId(null);
    resetForm();
  };

  const cancelEdit = () => {
    setEditingId(null);
    setIsCreating(false);
    resetForm();
  };

  const resetForm = () => {
    setName("");
    setDescription("");
    setCategory("business");
    setPriority(0);
  };

  if (!open) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content invariants-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2>Инварианты</h2>
          <button className="modal-close-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        <p className="invariants-description">
          Правила, которые ассистент обязан соблюдать. При конфликте с запросом
          — ассистент откажет и объяснит причину.
        </p>

        <div className="invariants-list">
          {invariants.map((inv) => (
            <div
              key={inv.id}
              className={`invariant-item ${inv.is_active ? "" : "invariant-inactive"}`}
            >
              {editingId === inv.id ? (
                <div className="invariant-edit-form">
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Название"
                    className="invariant-name-input"
                  />
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Описание правила"
                    className="invariant-desc-textarea"
                    rows={3}
                  />
                  <div className="invariant-form-row">
                    <select
                      value={category}
                      onChange={(e) =>
                        setCategory(e.target.value as InvariantCategory)
                      }
                      className="invariant-category-select"
                    >
                      <option value="architecture">Архитектура</option>
                      <option value="technical">Технические</option>
                      <option value="stack">Стек</option>
                      <option value="business">Бизнес</option>
                    </select>
                    <input
                      type="number"
                      value={priority}
                      onChange={(e) => setPriority(Number(e.target.value))}
                      placeholder="Приоритет"
                      className="invariant-priority-input"
                      min={0}
                    />
                  </div>
                  <div className="invariant-edit-actions">
                    <button onClick={() => handleUpdate(inv.id)}>
                      Сохранить
                    </button>
                    <button onClick={cancelEdit}>Отмена</button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="invariant-header">
                    <span
                      className={`invariant-category-badge invariant-cat-${inv.category}`}
                    >
                      {CATEGORY_LABELS[inv.category]}
                    </span>
                    <span className="invariant-name">{inv.name}</span>
                    <button
                      className={`invariant-toggle ${inv.is_active ? "invariant-toggle-on" : "invariant-toggle-off"}`}
                      onClick={() => handleToggle(inv.id)}
                      title={inv.is_active ? "Деактивировать" : "Активировать"}
                    >
                      {inv.is_active ? "ВКЛ" : "ВЫКЛ"}
                    </button>
                  </div>
                  <div className="invariant-desc-preview">
                    {inv.description.length > 150
                      ? inv.description.slice(0, 150) + "..."
                      : inv.description}
                  </div>
                  {inv.priority > 0 && (
                    <div className="invariant-priority">
                      Приоритет: {inv.priority}
                    </div>
                  )}
                  <div className="invariant-actions">
                    <button onClick={() => startEdit(inv)}>
                      Редактировать
                    </button>
                    <button
                      className="btn-danger"
                      onClick={() => handleDelete(inv.id)}
                    >
                      Удалить
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
          {invariants.length === 0 && !isCreating && (
            <div className="invariants-empty">Нет инвариантов</div>
          )}
        </div>

        {isCreating ? (
          <div className="invariant-create-form">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Название инварианта"
              className="invariant-name-input"
            />
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Описание правила (что ассистент обязан соблюдать)"
              className="invariant-desc-textarea"
              rows={3}
            />
            <div className="invariant-form-row">
              <select
                value={category}
                onChange={(e) =>
                  setCategory(e.target.value as InvariantCategory)
                }
                className="invariant-category-select"
              >
                <option value="architecture">Архитектура</option>
                <option value="technical">Технические</option>
                <option value="stack">Стек</option>
                <option value="business">Бизнес</option>
              </select>
              <input
                type="number"
                value={priority}
                onChange={(e) => setPriority(Number(e.target.value))}
                placeholder="Приоритет"
                className="invariant-priority-input"
                min={0}
              />
            </div>
            <div className="invariant-edit-actions">
              <button onClick={handleCreate}>Создать</button>
              <button onClick={cancelEdit}>Отмена</button>
            </div>
          </div>
        ) : (
          <button className="invariant-add-btn" onClick={startCreate}>
            + Новый инвариант
          </button>
        )}
      </div>
    </div>
  );
}

export default InvariantsModal;
