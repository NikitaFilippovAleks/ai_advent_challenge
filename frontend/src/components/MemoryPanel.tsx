import { useState, useEffect, useCallback } from "react";
import { ShortTermInsight, WorkingMemoryEntry } from "../types";
import {
  getMemory,
  addInsight,
  deleteInsight,
  setWorkingMemory,
  deleteWorkingMemory,
} from "../api/chat";

interface Props {
  conversationId: string;
  refreshTrigger: number;
}

// Вкладки: только краткосрочная и рабочая (долгосрочная — в сайдбаре)
type MemoryTab = "short_term" | "working";

const TAB_LABELS: Record<MemoryTab, string> = {
  short_term: "Краткосрочная",
  working: "Рабочая",
};

// Категории рабочей памяти
const WORKING_CATEGORIES = ["fact", "goal", "constraint", "decision", "result"];
const WORKING_CATEGORY_LABELS: Record<string, string> = {
  fact: "Факт",
  goal: "Цель",
  constraint: "Ограничение",
  decision: "Решение",
  result: "Результат",
};

function MemoryPanel({ conversationId, refreshTrigger }: Props) {
  const [activeTab, setActiveTab] = useState<MemoryTab>("short_term");
  const [insights, setInsights] = useState<ShortTermInsight[]>([]);
  const [working, setWorking] = useState<WorkingMemoryEntry[]>([]);

  // Формы добавления
  const [newInsightContent, setNewInsightContent] = useState("");
  const [newWorkingKey, setNewWorkingKey] = useState("");
  const [newWorkingValue, setNewWorkingValue] = useState("");
  const [newWorkingCategory, setNewWorkingCategory] = useState("fact");

  // Редактирование рабочей памяти
  const [editingWorkingKey, setEditingWorkingKey] = useState<string | null>(null);
  const [editWorkingValue, setEditWorkingValue] = useState("");

  const loadMemory = useCallback(() => {
    getMemory(conversationId)
      .then((data) => {
        setInsights(data.short_term || []);
        setWorking(data.working || []);
      })
      .catch(() => {});
  }, [conversationId]);

  useEffect(() => {
    loadMemory();
  }, [loadMemory, refreshTrigger]);

  // --- Краткосрочная память ---
  const handleAddInsight = async () => {
    if (newInsightContent.trim()) {
      await addInsight(conversationId, newInsightContent.trim());
      setNewInsightContent("");
      loadMemory();
    }
  };

  const handleDeleteInsight = async (id: number) => {
    await deleteInsight(conversationId, id);
    loadMemory();
  };

  // --- Рабочая память ---
  const handleEditWorking = (entry: WorkingMemoryEntry) => {
    setEditingWorkingKey(entry.key);
    setEditWorkingValue(entry.value);
  };

  const handleSaveWorking = async (category: string) => {
    if (editingWorkingKey) {
      await setWorkingMemory(conversationId, editingWorkingKey, editWorkingValue, category);
      setEditingWorkingKey(null);
      loadMemory();
    }
  };

  const handleAddWorking = async () => {
    if (newWorkingKey.trim() && newWorkingValue.trim()) {
      await setWorkingMemory(
        conversationId,
        newWorkingKey.trim(),
        newWorkingValue.trim(),
        newWorkingCategory,
      );
      setNewWorkingKey("");
      setNewWorkingValue("");
      loadMemory();
    }
  };

  const handleDeleteWorking = async (key: string) => {
    await deleteWorkingMemory(conversationId, key);
    loadMemory();
  };

  return (
    <div className="memory-sidebar-panel">
      <div className="memory-sidebar-header">Память диалога</div>
      <div className="memory-tabs">
        {(Object.keys(TAB_LABELS) as MemoryTab[]).map((tab) => (
          <button
            key={tab}
            className={`memory-tab ${activeTab === tab ? "memory-tab-active" : ""}`}
            onClick={() => setActiveTab(tab)}
          >
            {TAB_LABELS[tab]}
            <span className="memory-tab-count">
              {tab === "short_term" ? insights.length : working.length}
            </span>
          </button>
        ))}
      </div>

      {/* Краткосрочная */}
      {activeTab === "short_term" && (
        <div className="memory-sidebar-list">
          {insights.length === 0 && (
            <div className="facts-empty">
              Наблюдения появятся после обмена сообщениями
            </div>
          )}
          {insights.map((insight) => (
            <div key={insight.id} className="fact-item">
              <div className="fact-view">
                <span className="fact-value">{insight.content}</span>
                <div className="fact-actions">
                  <button
                    className="fact-btn fact-btn-delete"
                    onClick={() => handleDeleteInsight(insight.id)}
                  >
                    ✕
                  </button>
                </div>
              </div>
            </div>
          ))}
          <div className="fact-add">
            <input
              className="fact-add-value"
              style={{ flex: 1 }}
              placeholder="Добавить наблюдение..."
              value={newInsightContent}
              onChange={(e) => setNewInsightContent(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAddInsight()}
            />
            <button className="fact-btn fact-btn-add" onClick={handleAddInsight}>
              +
            </button>
          </div>
        </div>
      )}

      {/* Рабочая */}
      {activeTab === "working" && (
        <div className="memory-sidebar-list">
          {working.length === 0 && (
            <div className="facts-empty">
              Данные задачи появятся после обмена сообщениями
            </div>
          )}
          {working.map((entry) => (
            <div key={entry.key} className="fact-item">
              {editingWorkingKey === entry.key ? (
                <div className="fact-edit">
                  <span className="fact-key">{entry.key}:</span>
                  <input
                    className="fact-edit-input"
                    value={editWorkingValue}
                    onChange={(e) => setEditWorkingValue(e.target.value)}
                    onKeyDown={(e) =>
                      e.key === "Enter" && handleSaveWorking(entry.category)
                    }
                  />
                  <button
                    className="fact-btn fact-btn-save"
                    onClick={() => handleSaveWorking(entry.category)}
                  >
                    OK
                  </button>
                </div>
              ) : (
                <div className="fact-view">
                  <span className="memory-category-badge">
                    {WORKING_CATEGORY_LABELS[entry.category] || entry.category}
                  </span>
                  <span className="fact-key">{entry.key}:</span>
                  <span className="fact-value">{entry.value}</span>
                  <div className="fact-actions">
                    <button
                      className="fact-btn fact-btn-edit"
                      onClick={() => handleEditWorking(entry)}
                    >
                      ✎
                    </button>
                    <button
                      className="fact-btn fact-btn-delete"
                      onClick={() => handleDeleteWorking(entry.key)}
                    >
                      ✕
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
          <div className="memory-add-form">
            <select
              className="memory-category-select"
              value={newWorkingCategory}
              onChange={(e) => setNewWorkingCategory(e.target.value)}
            >
              {WORKING_CATEGORIES.map((cat) => (
                <option key={cat} value={cat}>
                  {WORKING_CATEGORY_LABELS[cat]}
                </option>
              ))}
            </select>
            <input
              className="memory-add-input"
              placeholder="Ключ"
              value={newWorkingKey}
              onChange={(e) => setNewWorkingKey(e.target.value)}
            />
            <input
              className="memory-add-input"
              placeholder="Значение"
              value={newWorkingValue}
              onChange={(e) => setNewWorkingValue(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAddWorking()}
            />
            <button className="fact-btn fact-btn-add" onClick={handleAddWorking}>
              + Добавить
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default MemoryPanel;
