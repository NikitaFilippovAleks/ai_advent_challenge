// Парсер и диспатч слеш-команд для основного чата.
// Команды парсятся на фронте — бэкенд не знает про префикс «/».
// Каждая команда возвращает override-набор полей для ChatRequest и
// (опционально) переопределяет текст сообщения.

import { ChatRequest } from "../types";

// Что возвращает команда: подмена параметров запроса + текст сообщения,
// который реально пойдёт в LLM (после удаления самой команды).
export interface SlashCommandResult {
  // Текст, который отправится в messages[*].content (без префикса команды).
  messageText: string;
  // Поля ChatRequest для подмены/добавления.
  overrides: Partial<ChatRequest>;
  // Имя команды (для отображения в UI бейджем — опционально).
  commandName: string;
}

// Сигнатура обработчика конкретной команды: получает аргументы (всё после
// "/help "), возвращает результирующее сообщение + overrides.
type SlashCommandHandler = (args: string) => SlashCommandResult;

// Регистр команд. Расширяется по мере добавления.
const COMMANDS: Record<string, SlashCommandHandler> = {
  "/help": (args) => {
    // Если пользователь не задал вопрос — показываем дефолтный обзор проекта.
    const trimmed = args.trim();
    const userQuestion =
      trimmed.length > 0
        ? trimmed
        : "Расскажи кратко о структуре проекта: бэкенд, фронтенд, какие есть модули и как всё запускать.";
    return {
      messageText: userQuestion,
      overrides: {
        use_rag: true,
        rag_collection: "project_docs",
        rag_rerank_mode: "keyword",
        help_mode: true,
      },
      commandName: "/help",
    };
  },
};

// Пытается распарсить ввод как слеш-команду. Возвращает null, если ввод
// не начинается со слеша или команда неизвестна (тогда отправляем как обычно).
export function parseSlashCommand(input: string): SlashCommandResult | null {
  const text = input.trimStart();
  if (!text.startsWith("/")) return null;

  // Извлекаем имя команды (до пробела или конца строки).
  const spaceIdx = text.indexOf(" ");
  const commandName = spaceIdx === -1 ? text : text.slice(0, spaceIdx);
  const handler = COMMANDS[commandName];
  if (!handler) return null;

  const args = spaceIdx === -1 ? "" : text.slice(spaceIdx + 1);
  return handler(args);
}
