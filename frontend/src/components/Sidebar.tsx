import { Conversation } from "../types";
import ConversationItem from "./ConversationItem";

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

function Sidebar({ conversations, activeId, onSelect, onNew, onDelete }: Props) {
  return (
    <div className="sidebar">
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
    </div>
  );
}

export default Sidebar;
