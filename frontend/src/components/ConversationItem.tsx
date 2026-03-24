import { Conversation } from "../types";

interface Props {
  conversation: Conversation;
  isActive: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}

function ConversationItem({ conversation, isActive, onSelect, onDelete }: Props) {
  return (
    <div
      className={`conversation-item${isActive ? " active" : ""}`}
      onClick={() => onSelect(conversation.id)}
    >
      <span className="conversation-title">{conversation.title}</span>
      <button
        className="conversation-delete"
        onClick={(e) => {
          e.stopPropagation();
          onDelete(conversation.id);
        }}
        title="Удалить диалог"
      >
        &times;
      </button>
    </div>
  );
}

export default ConversationItem;
