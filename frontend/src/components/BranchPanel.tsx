import { useState, useEffect, useCallback } from "react";
import { Branch, Message } from "../types";
import { getBranches, createBranch, activateBranch } from "../api/chat";

interface Props {
  conversationId: string;
  messages: Message[];
  onBranchSwitch: () => void;
}

function BranchPanel({ conversationId, messages, onBranchSwitch }: Props) {
  const [branches, setBranches] = useState<Branch[]>([]);
  const [activeBranchId, setActiveBranchId] = useState<number | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newBranchName, setNewBranchName] = useState("");
  const [checkpointIdx, setCheckpointIdx] = useState<number>(0);

  const loadBranches = useCallback(() => {
    getBranches(conversationId)
      .then((data) => {
        setBranches(data.branches);
        setActiveBranchId(data.active_branch_id);
      })
      .catch(() => {});
  }, [conversationId]);

  useEffect(() => {
    loadBranches();
  }, [loadBranches]);

  // Сообщения с реальными ID из БД (для выбора чекпоинта)
  const messagesWithIds = messages.filter((m) => m.id != null) as Array<
    Message & { id: number }
  >;

  const handleCreate = async () => {
    if (!newBranchName.trim() || messagesWithIds.length === 0) return;

    const checkpointId = messagesWithIds[checkpointIdx]?.id;
    if (!checkpointId) return;

    try {
      await createBranch(conversationId, newBranchName.trim(), checkpointId);
      setNewBranchName("");
      setShowCreateForm(false);
      loadBranches();
      onBranchSwitch();
    } catch {
      // Ошибка создания ветки
    }
  };

  const handleSwitch = async (branchId: number) => {
    try {
      await activateBranch(conversationId, branchId);
      setActiveBranchId(branchId);
      onBranchSwitch();
    } catch {
      // Ошибка переключения
    }
  };

  return (
    <div className="branch-panel">
      <div className="branch-header">
        <span>Ветки диалога</span>
        <button
          className="branch-btn branch-btn-new"
          onClick={() => setShowCreateForm(!showCreateForm)}
        >
          {showCreateForm ? "Отмена" : "+ Ветка"}
        </button>
      </div>

      {showCreateForm && (
        <div className="branch-create-form">
          <input
            className="branch-name-input"
            placeholder="Название ветки"
            value={newBranchName}
            onChange={(e) => setNewBranchName(e.target.value)}
          />
          <div className="branch-checkpoint-select">
            <label>Чекпоинт (от какого сообщения):</label>
            <select
              value={checkpointIdx}
              onChange={(e) => setCheckpointIdx(Number(e.target.value))}
            >
              {messagesWithIds.map((m, idx) => (
                <option key={idx} value={idx}>
                  #{idx + 1} [{m.role}] {m.content.slice(0, 40)}
                  {m.content.length > 40 ? "..." : ""}
                </option>
              ))}
            </select>
          </div>
          <button className="branch-btn branch-btn-create" onClick={handleCreate}>
            Создать ветку
          </button>
        </div>
      )}

      <div className="branch-list">
        {branches.length === 0 && (
          <div className="branch-empty">
            Нет веток. Создайте ветку, чтобы продолжить диалог в нескольких направлениях.
          </div>
        )}
        {branches.map((branch) => (
          <div
            key={branch.id}
            className={`branch-item ${branch.id === activeBranchId ? "branch-active" : ""}`}
          >
            <div className="branch-info">
              <span className="branch-name">{branch.name}</span>
              <span className="branch-checkpoint">
                от сообщения #{branch.checkpoint_message_id}
              </span>
            </div>
            {branch.id !== activeBranchId && (
              <button
                className="branch-btn branch-btn-switch"
                onClick={() => handleSwitch(branch.id)}
              >
                Переключить
              </button>
            )}
            {branch.id === activeBranchId && (
              <span className="branch-active-label">Активна</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default BranchPanel;
