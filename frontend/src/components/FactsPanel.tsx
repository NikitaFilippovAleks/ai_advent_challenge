import { useState, useEffect, useCallback } from "react";
import { Fact } from "../types";
import { getFacts, updateFact, deleteFact } from "../api/chat";

interface Props {
  conversationId: string;
  // Триггер для обновления фактов после ответа LLM
  refreshTrigger: number;
}

function FactsPanel({ conversationId, refreshTrigger }: Props) {
  const [facts, setFacts] = useState<Fact[]>([]);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");

  const loadFacts = useCallback(() => {
    getFacts(conversationId)
      .then(setFacts)
      .catch(() => {});
  }, [conversationId]);

  // Загружаем факты при монтировании и при обновлении триггера
  useEffect(() => {
    loadFacts();
  }, [loadFacts, refreshTrigger]);

  const handleEdit = (fact: Fact) => {
    setEditingKey(fact.key);
    setEditValue(fact.value);
  };

  const handleSave = async () => {
    if (editingKey) {
      await updateFact(conversationId, editingKey, editValue);
      setEditingKey(null);
      loadFacts();
    }
  };

  const handleDelete = async (key: string) => {
    await deleteFact(conversationId, key);
    loadFacts();
  };

  const handleAdd = async () => {
    if (newKey.trim() && newValue.trim()) {
      await updateFact(conversationId, newKey.trim(), newValue.trim());
      setNewKey("");
      setNewValue("");
      loadFacts();
    }
  };

  return (
    <div className="facts-panel">
      <div className="facts-header">Ключевые факты</div>
      <div className="facts-list">
        {facts.length === 0 && (
          <div className="facts-empty">
            Факты появятся автоматически после обмена сообщениями
          </div>
        )}
        {facts.map((fact) => (
          <div key={fact.key} className="fact-item">
            {editingKey === fact.key ? (
              <div className="fact-edit">
                <span className="fact-key">{fact.key}:</span>
                <input
                  className="fact-edit-input"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSave()}
                />
                <button className="fact-btn fact-btn-save" onClick={handleSave}>
                  OK
                </button>
              </div>
            ) : (
              <div className="fact-view">
                <span className="fact-key">{fact.key}:</span>
                <span className="fact-value">{fact.value}</span>
                <div className="fact-actions">
                  <button
                    className="fact-btn fact-btn-edit"
                    onClick={() => handleEdit(fact)}
                  >
                    ✎
                  </button>
                  <button
                    className="fact-btn fact-btn-delete"
                    onClick={() => handleDelete(fact.key)}
                  >
                    ✕
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="fact-add">
        <input
          className="fact-add-key"
          placeholder="Ключ"
          value={newKey}
          onChange={(e) => setNewKey(e.target.value)}
        />
        <input
          className="fact-add-value"
          placeholder="Значение"
          value={newValue}
          onChange={(e) => setNewValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
        />
        <button className="fact-btn fact-btn-add" onClick={handleAdd}>
          +
        </button>
      </div>
    </div>
  );
}

export default FactsPanel;
