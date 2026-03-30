"""Базовые исключения приложения.

Используются в сервисах и репозиториях для типизированной обработки ошибок.
Роутеры преобразуют их в соответствующие HTTP-ответы.
"""


class NotFoundError(Exception):
    """Запрашиваемый ресурс не найден."""

    def __init__(self, detail: str = "Ресурс не найден"):
        self.detail = detail
        super().__init__(self.detail)


class ValidationError(Exception):
    """Ошибка валидации входных данных."""

    def __init__(self, detail: str = "Ошибка валидации"):
        self.detail = detail
        super().__init__(self.detail)
