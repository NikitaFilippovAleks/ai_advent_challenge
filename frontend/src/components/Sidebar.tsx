import { useState } from "react";
import { Conversation } from "../types";
import ConversationItem from "./ConversationItem";
import LongTermMemoryPanel from "./LongTermMemoryPanel";

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onOpenProfiles: () => void;
}

// Вкладки сайдбара
type SidebarTab = "conversations" | "memory";

function Sidebar({ conversations, activeId, onSelect, onNew, onDelete, onOpenProfiles }: Props) {
  const [activeTab, setActiveTab] = useState<SidebarTab>("conversations");

  return (
    <div className="sidebar">
      {/* Переключатель вкладок */}
      <div className="sidebar-tabs">
        <button
          className={`sidebar-tab ${activeTab === "conversations" ? "sidebar-tab-active" : ""}`}
          onClick={() => setActiveTab("conversations")}
        >
          Диалоги
        </button>
        <button
          className={`sidebar-tab ${activeTab === "memory" ? "sidebar-tab-active" : ""}`}
          onClick={() => setActiveTab("memory")}
        >
          Память
        </button>
        <button
          className="sidebar-tab"
          onClick={onOpenProfiles}
        >
          Профили
        </button>
      </div>

      {/* Содержимое: диалоги */}
      {activeTab === "conversations" && (
        <>
          <button className="sidebar-new-btn" onClick={onNew}>
            + Новый диалог
          </button>
          <div className="sidebar-list">
            {conversations.length === 0 ? (
              <div className="sidebar-empty">Нет диалогов</div>
            ) : (
              conversations.map((conv) => (
                <ConversationItem
                  key={conv.id}
                  conversation={conv}
                  isActive={conv.id === activeId}
                  onSelect={onSelect}
                  onDelete={onDelete}
                />
              ))
            )}
          </div>
        </>
      )}

      {/* Содержимое: долгосрочная память */}
      {activeTab === "memory" && (
        <div className="sidebar-memory-content">
          <LongTermMemoryPanel />
        </div>
      )}
    </div>
  );
}

export default Sidebar;
