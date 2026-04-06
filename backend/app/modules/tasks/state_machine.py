"""Конечный автомат состояний задачи.

Определяет фазы, разрешённые переходы и функцию валидации.
"""

from typing import Literal

# Все допустимые фазы задачи
TaskPhase = Literal[
    "planning", "execution", "validation", "done", "paused", "cancelled"
]

# Белый список переходов: из какой фазы в какие можно перейти
ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    "planning": ["execution", "paused", "cancelled"],
    "execution": ["validation", "paused", "cancelled"],
    "validation": ["done", "execution", "paused", "cancelled"],
    "paused": ["planning", "execution", "validation"],
    "done": [],
    "cancelled": [],
}


def validate_transition(
    current: str, target: str, previous_phase: str | None = None
) -> None:
    """Проверяет допустимость перехода. Выбрасывает ValueError при нарушении.

    Для перехода из paused разрешён только возврат в previous_phase.
    """
    allowed = ALLOWED_TRANSITIONS.get(current, [])
    if target not in allowed:
        raise ValueError(
            f"Переход {current} → {target} запрещён. "
            f"Допустимые переходы из {current}: {allowed}"
        )
    # Из paused — только в ту фазу, из которой пришли
    if current == "paused":
        if previous_phase is None:
            raise ValueError("Невозможно выйти из паузы: previous_phase не задан")
        if target != previous_phase:
            raise ValueError(
                f"Из паузы можно вернуться только в {previous_phase}, "
                f"а не в {target}"
            )
