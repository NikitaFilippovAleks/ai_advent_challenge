import { useState, useEffect, useCallback } from "react";
import { LongTermMemoryEntry } from "../types";
import { getLongTermMemories, setLongTermMemory, deleteLongTermMemory } from "../api/chat";

// Категории долгосрочной памяти
const LONG_TERM_CATEGORIES = ["knowledge", "preference", "decision"];
const LONG_TERM_CATEGORY_LABELS: Record<string, string> = {
  knowledge: "Знание",
  preference: "Предпочтение",
  decision: "Решение",
};

function LongTermMemoryPanel() {
  const [memories, setMemories] = useState<LongTermMemoryEntry[]>([]);
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [newCategory, setNewCategory] = useState("knowledge");

  const loadMemories = useCallback(() => {
    getLongTermMemories()
      .then(setMemories)
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadMemories();
  }, [loadMemories]);

  const handleAdd = async () => {
    if (newKey.trim() && newValue.trim()) {
      await setLongTermMemory(newKey.trim(), newValue.trim(), newCategory);
      setNewKey("");
      setNewValue("");
      loadMemories();
    }
  };

  const handleDelete = async (id: number) => {
    await deleteLongTermMemory(id);
    loadMemories();
  };

  return (
    <div className="long-term-memory-panel">
      <div className="long-term-memory-header">Долгосрочная память</div>
      <div className="long-term-memory-description">
        Накопленные знания о пользователе, сохраняются между диалогами
      </div>
      <div className="long-term-memory-list">
        {memories.length === 0 && (
          <div className="facts-empty">
            Долгосрочные знания накапливаются по мере общения
          </div>
        )}
        {memories.map((entry) => (
          <div key={entry.id} className="fact-item">
            <div className="fact-view">
              <span className="memory-category-badge">
                {LONG_TERM_CATEGORY_LABELS[entry.category] || entry.category}
              </span>
              <span className="fact-key">{entry.key}:</span>
              <span className="fact-value">{entry.value}</span>
              <div className="fact-actions">
                <button
                  className="fact-btn fact-btn-delete"
                  onClick={() => handleDelete(entry.id)}
                >
                  ✕
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
      <div className="memory-add-form">
        <select
          className="memory-category-select"
          value={newCategory}
          onChange={(e) => setNewCategory(e.target.value)}
        >
          {LONG_TERM_CATEGORIES.map((cat) => (
            <option key={cat} value={cat}>
              {LONG_TERM_CATEGORY_LABELS[cat]}
            </option>
          ))}
        </select>
        <input
          className="memory-add-input"
          placeholder="Ключ"
          value={newKey}
          onChange={(e) => setNewKey(e.target.value)}
        />
        <input
          className="memory-add-input"
          placeholder="Значение"
          value={newValue}
          onChange={(e) => setNewValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
        />
        <button className="fact-btn fact-btn-add" onClick={handleAdd}>
          + Добавить
        </button>
      </div>
    </div>
  );
}

export default LongTermMemoryPanel;
