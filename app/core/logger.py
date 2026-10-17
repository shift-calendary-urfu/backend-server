"""
Цветной логгер для проекта "Календарь смен".

Использование:
    from app.core.logger import get_logger

    logger = get_logger(__name__)
    logger.info("Сообщение")
    logger.warning("Предупреждение")
    logger.error("Ошибка")
"""

import logging
import sys


# ANSI-коды цветов
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"

    # Цвета текста
    GRAY = "\033[90m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BRIGHT_RED = "\033[91m"
    MAGENTA = "\033[35m"


# Цвет для каждого уровня логирования
LEVEL_COLORS = {
    logging.DEBUG: Colors.GRAY,
    logging.INFO: Colors.GREEN,
    logging.WARNING: Colors.YELLOW,
    logging.ERROR: Colors.RED,
    logging.CRITICAL: Colors.BRIGHT_RED,
}


class ColorFormatter(logging.Formatter):
    """
    Форматтер, который раскрашивает вывод в терминале.

    Формат:
        2026-10-17 10:30:00 | INFO     | app.auth.services | Пользователь зарегистрирован
    """

    def __init__(self):
        super().__init__()
        self.default_fmt = (
            "{gray}%(asctime)s{reset} | "
            "{level_color}%(levelname)-8s{reset} | "
            "{cyan}%(name)s{reset} | "
            "{level_color}%(message)s{reset}"
        )
        self.datefmt = "%Y-%m-%d %H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        level_color = LEVEL_COLORS.get(record.levelno, Colors.RESET)

        fmt = self.default_fmt.format(
            gray=Colors.GRAY,
            reset=Colors.RESET,
            level_color=level_color,
            cyan=Colors.CYAN,
        )

        formatter = logging.Formatter(fmt, datefmt=self.datefmt)
        return formatter.format(record)


def get_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """
    Возвращает настроенный цветной логгер.

    Args:
        name: Имя логгера (обычно __name__).
        level: Уровень логирования (по умолчанию DEBUG).

    Returns:
        Настроенный логгер с цветным выводом в консоль.
    """
    logger = logging.getLogger(name)

    # Предотвращаем дублирование обработчиков при повторных вызовах
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Обработчик — вывод в консоль (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(ColorFormatter())

    logger.addHandler(console_handler)

    # Не передавать сообщения родительскому логгеру (избегаем дублей)
    logger.propagate = False

    return logger
