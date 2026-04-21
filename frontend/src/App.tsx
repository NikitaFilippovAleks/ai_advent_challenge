import { useState, useEffect, useCallback } from "react";
import ChatWindow from "./components/ChatWindow";
import PlaygroundWindow from "./components/PlaygroundWindow";
import Sidebar from "./components/Sidebar";
import ProfilesModal from "./components/ProfilesModal";
import InvariantsModal from "./components/InvariantsModal";
import {
  getModels,
  getConversations,
  createConversation,
  deleteConversation,
} from "./api/chat";
import { ModelInfo, Conversation } from "./types";

// Режимы работы приложения: основной чат GigaChat и playground для локальных моделей
type AppMode = "chat" | "playground";

function App() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);
  const [profilesModalOpen, setProfilesModalOpen] = useState(false);
  const [invariantsModalOpen, setInvariantsModalOpen] = useState(false);
  const [profilesVersion, setProfilesVersion] = useState(0);
  // Режим сохраняем в localStorage, чтобы переживал перезагрузку страницы
  const [mode, setMode] = useState<AppMode>(
    () => (localStorage.getItem("app_mode") as AppMode) || "chat",
  );

  // Загружаем модели и диалоги при монтировании
  useEffect(() => {
    getModels()
      .then(setModels)
      .catch(() => {});
    getConversations()
      .then(setConversations)
      .catch(() => {});
  }, []);

  useEffect(() => {
    localStorage.setItem("app_mode", mode);
  }, [mode]);

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
        {/* Переключатель режимов: основной чат / playground для локальных моделей */}
        <div style={{ display: "flex", gap: "4px", marginLeft: "16px" }}>
          <button
            className={`memory-toggle-btn${mode === "chat" ? " active" : ""}`}
            onClick={() => setMode("chat")}
          >
            Чат
          </button>
          <button
            className={`memory-toggle-btn${mode === "playground" ? " active" : ""}`}
            onClick={() => setMode("playground")}
            title="Тестирование локальных моделей через LM Studio"
          >
            Playground
          </button>
        </div>
      </header>
      <div className="app-content">
        {mode === "chat" ? (
          <>
            <Sidebar
              conversations={conversations}
              activeId={activeConversationId}
              onSelect={handleSelectConversation}
              onNew={handleNewConversation}
              onDelete={handleDeleteConversation}
              onOpenProfiles={() => setProfilesModalOpen(true)}
              onOpenInvariants={() => setInvariantsModalOpen(true)}
            />
            <ChatWindow
              key={activeConversationId}
              models={models}
              conversationId={activeConversationId}
              onConversationUpdate={refreshConversations}
              profilesVersion={profilesVersion}
            />
          </>
        ) : (
          <PlaygroundWindow />
        )}
      </div>
      <ProfilesModal
        open={profilesModalOpen}
        onClose={() => setProfilesModalOpen(false)}
        onProfilesChange={() => setProfilesVersion((v) => v + 1)}
      />
      <InvariantsModal
        open={invariantsModalOpen}
        onClose={() => setInvariantsModalOpen(false)}
      />
    </div>
  );
}

export default App;
