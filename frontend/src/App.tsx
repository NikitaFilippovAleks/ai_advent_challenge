import { useState, useEffect, useCallback } from "react";
import ChatWindow from "./components/ChatWindow";
import Sidebar from "./components/Sidebar";
import {
  getModels,
  getConversations,
  createConversation,
  deleteConversation,
} from "./api/chat";
import { ModelInfo, Conversation } from "./types";

function App() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);

  // Загружаем модели и диалоги при монтировании
  useEffect(() => {
    getModels()
      .then(setModels)
      .catch(() => {});
    getConversations()
      .then(setConversations)
      .catch(() => {});
  }, []);

  const refreshConversations = useCallback(() => {
    getConversations()
      .then(setConversations)
      .catch(() => {});
  }, []);

  const handleNewConversation = async () => {
    try {
      const conv = await createConversation();
      setConversations((prev) => [conv, ...prev]);
      setActiveConversationId(conv.id);
    } catch {
      // Ошибка создания диалога
    }
  };

  const handleSelectConversation = (id: string) => {
    setActiveConversationId(id);
  };

  const handleDeleteConversation = async (id: string) => {
    try {
      await deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeConversationId === id) {
        setActiveConversationId(null);
      }
    } catch {
      // Ошибка удаления
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>GigaChat</h1>
      </header>
      <div className="app-content">
        <Sidebar
          conversations={conversations}
          activeId={activeConversationId}
          onSelect={handleSelectConversation}
          onNew={handleNewConversation}
          onDelete={handleDeleteConversation}
        />
        <ChatWindow
          key={activeConversationId}
          models={models}
          conversationId={activeConversationId}
          onConversationUpdate={refreshConversations}
        />
      </div>
    </div>
  );
}

export default App;
