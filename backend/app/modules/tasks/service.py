"""Сервис управления задачами и их жизненным циклом.

Содержит бизнес-логику: классификацию сообщений, управление FSM,
построение system prompt по фазе, парсинг ответа LLM.
"""

import json
import logging
import re

from app.modules.tasks.repository import (
    create_task,
    get_active_task,
    get_task,
    update_task,
)
from app.modules.tasks.state_machine import validate_transition
from app.shared.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

# Промпт классификатора: определяет тип сообщения
_CLASSIFY_SYSTEM = (
    "Определи тип запроса пользователя. Ответь ОДНИМ словом:\n"
    "- chat: обычное общение, вопрос, перевод, объяснение, короткая просьба, "
    "одношаговая задача (написать функцию, объяснить код), "
    "запросы на мониторинг, расписание, напоминания, периодические задачи, "
    "работу с git (статус, лог, ветки, diff)\n"
    "- task: сложная многошаговая задача, требующая плана и поэтапной реализации "
    "(создать приложение, спроектировать систему, провести рефакторинг)"
)

# Промпты для каждой фазы FSM
_PHASE_PROMPTS = {
    "planning": (
        "Ты в фазе ПЛАНИРОВАНИЕ. Пользователь поставил задачу.\n"
        "Составь пошаговый план реализации (3-7 шагов).\n\n"
        "Формат ответа:\n"
        "1. Напиши план в человекочитаемом виде — нумерованный список шагов "
        "с кратким описанием каждого.\n"
        '2. В самом конце добавь JSON для системы (СКРЫТЫЙ, между тегами <json> и </json>):\n'
        '<json>{"steps": [{"description": "Шаг 1"}, {"description": "Шаг 2"}]}</json>\n'
        '3. После JSON спроси: "План готов. Утверждаете?"\n\n'
        "ВАЖНО: JSON должен использовать ОДИНАРНЫЕ фигурные скобки { }, НЕ двойные.\n"
        "НЕ пиши код. НЕ начинай реализацию.\n"
        "Если доступны MCP-инструменты — используй их через function_call."
    ),
    "execution": (
        "Ты в фазе РЕАЛИЗАЦИЯ.\n"
        "Задача: {title}\n"
        "План:\n{steps_text}\n"
        "Текущий шаг: {current} из {total} — {step_desc}\n"
        "Выполни текущий шаг подробно.\n"
        "Если для выполнения шага доступны MCP-инструменты — используй их через function_call.\n"
        'В конце ответа ОБЯЗАТЕЛЬНО напиши на отдельной строке: "Шаг выполнен."'
    ),
    "validation": (
        "Ты в фазе ВАЛИДАЦИЯ.\n"
        "Задача: {title}\n"
        "Выполненные шаги:\n{steps_text}\n"
        'Проверь результат. Если всё корректно — напиши "Валидация пройдена."\n'
        'Если есть проблемы — опиши их и напиши "Требуется доработка."'
    ),
    "paused_resume": (
        "Задача была на паузе. Фаза: {phase}, шаг {current} из {total}.\n"
        "Продолжи без повторных объяснений. Не пересказывай план."
    ),
}


class TaskService:
    """Управляет жизненным циклом задач."""

    def __init__(self, llm: BaseLLMProvider) -> None:
        self._llm = llm

    # Ключевые слова, при которых сообщение всегда считается "chat"
    # (обрабатывается MCP-инструментами, а не Task FSM)
    _MCP_KEYWORDS = [
        "мониторинг", "следи", "каждые", "расписани", "периодич",
        "напомни", "cron", "git_log", "git_status", "git_diff",
        "планировщик", "сводк", "search_files", "summarize", "save_to_file",
        "research", "найди файл", "поиск по файлам",
    ]

    async def classify_message(self, user_text: str) -> str:
        """Классифицирует сообщение: 'chat' или 'task'.

        Один короткий LLM-вызов (~50-100 токенов).
        """
        # Быстрая проверка: запросы на мониторинг/расписание → chat (для MCP-инструментов)
        text_lower = user_text.lower()
        if any(kw in text_lower for kw in self._MCP_KEYWORDS):
            return "chat"

        messages = [
            {"role": "system", "content": _CLASSIFY_SYSTEM},
            {"role": "user", "content": user_text},
        ]
        try:
            result = await self._llm.chat(messages)
            answer = result["content"].strip().lower()
            if "task" in answer:
                return "task"
            return "chat"
        except Exception as e:
            logger.error("Ошибка классификации: %s", e)
            return "chat"

    async def create(self, conversation_id: str, title: str) -> dict:
        """Создаёт новую задачу в фазе planning."""
        return await create_task(conversation_id, title)

    async def get_active(self, conversation_id: str) -> dict | None:
        """Возвращает активную задачу диалога или None."""
        return await get_active_task(conversation_id)

    async def transition(self, task_id: str, target_phase: str) -> dict:
        """Выполняет переход фазы с валидацией FSM.

        Возвращает обновлённую задачу. Выбрасывает ValueError при нарушении.
        """
        task = await get_task(task_id)
        if task is None:
            raise ValueError("Задача не найдена")

        validate_transition(task["phase"], target_phase, task["previous_phase"])

        fields: dict = {"phase": target_phase}

        if target_phase == "paused":
            fields["previous_phase"] = task["phase"]
            fields["status_text"] = f"На паузе ({self._phase_label(task['phase'])})"
        elif task["phase"] == "paused":
            # Возврат из паузы — восстанавливаем status_text
            fields["previous_phase"] = None
            fields["status_text"] = self._build_status_text(
                target_phase, task["steps"], task["current_step"]
            )
        elif target_phase == "cancelled":
            fields["status_text"] = "Задача отменена"
        elif target_phase == "done":
            fields["status_text"] = "Задача завершена"
        elif target_phase == "execution":
            fields["status_text"] = self._build_status_text(
                "execution", task["steps"], task["current_step"]
            )
        elif target_phase == "validation":
            fields["status_text"] = "Валидация: проверяю результат"

        return await update_task(task_id, **fields)

    async def save_plan(self, task_id: str, steps: list[dict]) -> dict:
        """Сохраняет план задачи (список шагов)."""
        # Добавляем статус к каждому шагу
        for step in steps:
            if "status" not in step:
                step["status"] = "pending"
        plan_json = json.dumps(steps, ensure_ascii=False)
        total = len(steps)
        return await update_task(
            task_id,
            plan_json=plan_json,
            current_step=0,
            status_text=f"Планирование: план готов ({total} шагов), жду подтверждения",
        )

    def build_system_prompt(self, task: dict) -> str:
        """Формирует system-промпт для текущей фазы задачи."""
        phase = task["phase"]
        steps = task["steps"] or []
        current = task["current_step"]
        total = len(steps)

        if phase == "planning":
            return _PHASE_PROMPTS["planning"]

        if phase == "execution":
            step_desc = steps[current]["description"] if current < total else "—"
            return _PHASE_PROMPTS["execution"].format(
                title=task["title"],
                steps_text=self._format_steps(steps, current),
                current=current + 1,
                total=total,
                step_desc=step_desc,
            )

        if phase == "validation":
            return _PHASE_PROMPTS["validation"].format(
                title=task["title"],
                steps_text=self._format_steps(steps, total),
            )

        if phase == "paused":
            prev = task["previous_phase"] or "execution"
            return _PHASE_PROMPTS["paused_resume"].format(
                phase=self._phase_label(prev),
                current=current + 1,
                total=total,
            )

        return ""

    async def process_user_message(self, task: dict, user_text: str) -> dict | None:
        """Обрабатывает сообщение пользователя для автоматических переходов.

        Вызывается ДО отправки в LLM. Например, "да"/"утверждаю" при готовом плане
        → автопереход planning → execution.
        """
        phase = task["phase"]

        # В фазе planning с готовым планом — проверяем подтверждение
        if phase == "planning" and task["steps"]:
            confirm_markers = ["да", "утверждаю", "приступай", "го", "ок", "ok", "yes", "начинай"]
            text_lower = user_text.strip().lower().rstrip("!.")
            if text_lower in confirm_markers or "утвержда" in text_lower:
                return await self.transition(task["id"], "execution")

        return None

    async def process_llm_response(self, task: dict, response_text: str) -> dict | None:
        """Анализирует ответ LLM и выполняет автоматические переходы.

        Возвращает обновлённую задачу или None если изменений нет.
        """
        phase = task["phase"]

        if phase == "planning":
            return await self._process_planning_response(task, response_text)
        if phase == "execution":
            return await self._process_execution_response(task, response_text)
        if phase == "validation":
            return await self._process_validation_response(task, response_text)

        return None

    async def _process_planning_response(self, task: dict, text: str) -> dict | None:
        """Парсит план из ответа LLM в фазе planning."""
        # Сначала ищем JSON в тегах <json>...</json>
        tag_match = re.search(r'<json>([\s\S]*?)</json>', text)
        if tag_match:
            raw = tag_match.group(1).strip()
            # Исправляем двойные скобки {{ → { если LLM их использовал
            raw = raw.replace("{{", "{").replace("}}", "}")
            try:
                data = json.loads(raw)
                steps = data.get("steps", [])
                if steps:
                    return await self.save_plan(task["id"], steps)
            except json.JSONDecodeError:
                logger.warning("Не удалось распарсить JSON из <json> тегов")

        # Фолбэк: ищем JSON в ```json ... ``` блоке
        code_match = re.search(r'```json\s*([\s\S]*?)```', text)
        if code_match:
            raw = code_match.group(1).strip()
            raw = raw.replace("{{", "{").replace("}}", "}")
            try:
                data = json.loads(raw)
                steps = data.get("steps", [])
                if steps:
                    return await self.save_plan(task["id"], steps)
            except json.JSONDecodeError:
                logger.warning("Не удалось распарсить JSON из code block")

        # Фолбэк: ищем любой JSON с "steps" в тексте
        match = re.search(r'\{[\s\S]*"steps"\s*:\s*\[[\s\S]*\]\s*\}', text)
        if match:
            raw = match.group().replace("{{", "{").replace("}}", "}")
            try:
                data = json.loads(raw)
                steps = data.get("steps", [])
                if steps:
                    return await self.save_plan(task["id"], steps)
            except json.JSONDecodeError:
                logger.warning("Не удалось распарсить JSON плана из ответа LLM")
        return None

    async def _process_execution_response(self, task: dict, text: str) -> dict | None:
        """Обрабатывает маркеры 'Шаг выполнен' в фазе execution.

        Считает ВСЕ вхождения маркера — LLM может выполнить несколько шагов за раз.
        """
        text_lower = text.lower()
        # Считаем сколько раз встречается маркер
        completed_count = text_lower.count("шаг выполнен")
        if completed_count == 0:
            return None

        steps = task["steps"] or []
        current = task["current_step"]
        total = len(steps)

        # Отмечаем выполненные шаги
        for i in range(completed_count):
            step_idx = current + i
            if step_idx < total:
                steps[step_idx]["status"] = "done"

        next_step = min(current + completed_count, total)
        plan_json = json.dumps(steps, ensure_ascii=False)

        if next_step >= total:
            # Все шаги выполнены — переход в validation
            return await update_task(
                task["id"],
                plan_json=plan_json,
                current_step=next_step,
                phase="validation",
                status_text="Валидация: проверяю результат",
            )
        else:
            # Переход к следующему шагу
            step_desc = steps[next_step]["description"]
            return await update_task(
                task["id"],
                plan_json=plan_json,
                current_step=next_step,
                status_text=f"Выполнение: шаг {next_step + 1}/{total} — {step_desc}",
            )

    async def _process_validation_response(self, task: dict, text: str) -> dict | None:
        """Обрабатывает маркеры валидации."""
        text_lower = text.lower()
        if "валидация пройдена" in text_lower:
            return await update_task(
                task["id"],
                phase="done",
                status_text="Задача завершена",
            )
        if "требуется доработка" in text_lower:
            return await update_task(
                task["id"],
                phase="execution",
                status_text=self._build_status_text(
                    "execution", task["steps"], task["current_step"]
                ),
            )
        return None

    def _format_steps(self, steps: list[dict], highlight_idx: int) -> str:
        """Форматирует список шагов для промпта."""
        lines = []
        for i, step in enumerate(steps):
            marker = "→" if i == highlight_idx else ("✓" if step.get("status") == "done" else " ")
            lines.append(f"  {marker} {i + 1}. {step['description']}")
        return "\n".join(lines)

    def _build_status_text(
        self, phase: str, steps: list[dict] | None, current_step: int
    ) -> str:
        """Строит текст статуса для UI."""
        if phase == "planning":
            return "Планирование: составляю план"
        if phase == "execution":
            if steps and current_step < len(steps):
                total = len(steps)
                desc = steps[current_step]["description"]
                return f"Выполнение: шаг {current_step + 1}/{total} — {desc}"
            return "Выполнение"
        if phase == "validation":
            return "Валидация: проверяю результат"
        return ""

    def _phase_label(self, phase: str) -> str:
        """Русское название фазы."""
        labels = {
            "planning": "планирование",
            "execution": "выполнение",
            "validation": "валидация",
        }
        return labels.get(phase, phase)
