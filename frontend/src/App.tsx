import { useState, useEffect } from "react";
import ChatWindow from "./components/ChatWindow";
import { getModels } from "./api/chat";
import { ModelInfo } from "./types";

function App() {
  const [models, setModels] = useState<ModelInfo[]>([]);

  useEffect(() => {
    getModels()
      .then((list) => {
        setModels(list);
      })
      .catch(() => {
        // Если не удалось загрузить — оставляем пустой список
      });
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <h1>GigaChat</h1>
      </header>
      <div className="app-content">
        <ChatWindow title="Чат 1" style="normal" models={models} />
        <ChatWindow title="Чат 2" style="normal" models={models} />
        <ChatWindow title="Чат 3" style="normal" models={models} />
      </div>
    </div>
  );
}

export default App;
