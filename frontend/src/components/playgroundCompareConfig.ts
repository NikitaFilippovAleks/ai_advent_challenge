// Конфигурации для сравнительного playground.
// Baseline — "дефолтная" локальная LLM без оптимизации.
// Optimized — узкий кейс: классификатор обращений в поддержку с выдачей строгого JSON.
// Prompt и параметры захардкожены специально: цель дня — показать разницу
// между неоптимизированным и оптимизированным под кейс вариантом.

export interface PlaygroundChatConfig {
  label: string;
  description: string;
  temperature: number;
  maxTokens: number;
  // Пустая строка = без user-level system prompt
  systemPrompt: string;
}

// Baseline: дефолтные настройки, как если бы пользователь пришёл в LM Studio и
// начал задавать вопросы. Никаких инструкций, большое окно ответа, творческая температура.
export const BASELINE_CONFIG: PlaygroundChatConfig = {
  label: "Baseline",
  description: "t=0.7, max=2048, без system prompt",
  temperature: 0.7,
  maxTokens: 2048,
  systemPrompt: "",
};

// Optimized: узкий кейс — классификатор тикетов поддержки.
// Few-shot, строгая схема, низкая температура, жёсткий лимит токенов.
export const OPTIMIZED_CONFIG: PlaygroundChatConfig = {
  label: "Optimized",
  description: "t=0.1, max=150, few-shot JSON-classifier",
  temperature: 0.1,
  maxTokens: 150,
  systemPrompt: `Ты — классификатор обращений в поддержку. На вход — текст тикета на русском.
Отвечай СТРОГО одним JSON-объектом без пояснений, без markdown, без префикса.

Схема:
{
  "category": "billing" | "technical" | "account" | "feature_request" | "other",
  "priority": "low" | "medium" | "high" | "urgent",
  "summary": "<=120 символов, одна фраза, на русском"
}

Примеры:
Вход: "У меня третий день не приходит счёт на почту, оплата нужна срочно"
Выход: {"category":"billing","priority":"high","summary":"Не приходит счёт на почту, нужна срочная оплата"}

Вход: "Приложение падает при открытии профиля на iOS 17"
Выход: {"category":"technical","priority":"high","summary":"Краш приложения при открытии профиля на iOS 17"}

Вход: "Было бы круто добавить тёмную тему"
Выход: {"category":"feature_request","priority":"low","summary":"Запрос на добавление тёмной темы"}`,
};
