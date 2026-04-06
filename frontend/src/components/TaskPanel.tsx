import { useState } from "react";
import { TaskInfo } from "../types";
import { transitionTask } from "../api/tasks";

interface Props {
  task: TaskInfo;
  onTaskUpdate: (task: TaskInfo | null) => void;
}

// Цвета индикатора фазы
const PHASE_COLORS: Record<string, string> = {
  planning: "#f0ad4e",
  execution: "#5cb85c",
  validation: "#5bc0de",
  paused: "#999",
  done: "#777",
  cancelled: "#777",
};

function TaskPanel({ task, onTaskUpdate }: Props) {
  const [loading, setLoading] = useState(false);

  // Прогресс: шаги выполнены / всего
  const totalSteps = task.steps?.length || 0;
  const progress =
    task.phase === "validation" || task.phase === "done"
      ? 100
      : task.phase === "planning"
        ? 0
        : totalSteps > 0
          ? Math.round((task.current_step / totalSteps) * 100)
          : 0;

  const isPaused = task.phase === "paused";
  const isTerminal = task.phase === "done" || task.phase === "cancelled";

  if (isTerminal) return null;

  const handlePauseResume = async () => {
    setLoading(true);
    try {
      if (isPaused && task.previous_phase) {
        const updated = await transitionTask(task.id, task.previous_phase);
        onTaskUpdate(updated);
      } else {
        const updated = await transitionTask(task.id, "paused");
        onTaskUpdate(updated);
      }
    } catch (e) {
      console.error("Ошибка перехода:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!confirm("Отменить задачу?")) return;
    setLoading(true);
    try {
      const updated = await transitionTask(task.id, "cancelled");
      onTaskUpdate(updated);
    } catch (e) {
      console.error("Ошибка отмены:", e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="task-panel">
      <div className="task-panel-row">
        <span
          className="task-phase-indicator"
          style={{ background: PHASE_COLORS[task.phase] || "#999" }}
        />
        <span className="task-status-text">{task.status_text}</span>
        <div className="task-panel-actions">
          <button
            className="task-btn"
            onClick={handlePauseResume}
            disabled={loading}
            title={isPaused ? "Продолжить" : "Пауза"}
          >
            {isPaused ? "▶" : "⏸"}
          </button>
          <button
            className="task-btn task-btn-cancel"
            onClick={handleCancel}
            disabled={loading}
            title="Отменить задачу"
          >
            ✕
          </button>
        </div>
      </div>
      {totalSteps > 0 && (
        <div className="task-progress-bar">
          <div
            className="task-progress-fill"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
    </div>
  );
}

export default TaskPanel;
