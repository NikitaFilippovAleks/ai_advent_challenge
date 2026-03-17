import { useState, useEffect } from "react";
import ChatWindow from "./components/ChatWindow";
import { getModels } from "./api/chat";
import { ModelInfo } from "./types";

function App() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("");

  useEffect(() => {
    getModels()
      .then((list) => {
        setModels(list);
        if (list.length > 0) {
          setSelectedModel(list[0].id);
        }
      })
      .catch(() => {
        // Если не удалось загрузить — оставляем пустой список
      });
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <h1>GigaChat</h1>
        <div className="model-selector">
          <label htmlFor="model-select">Модель:</label>
          <select
            id="model-select"
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </div>
      </header>
      <div className="app-content">
        <ChatWindow title="Обычный чат" style="normal" model={selectedModel} />
        <ChatWindow title="Кастомный чат" style="custom" model={selectedModel} />
      </div>
    </div>
  );
}

export default App;
