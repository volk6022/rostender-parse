"""Инструменты для мониторинга и логирования производительности."""

import time
import asyncio
from contextlib import ContextDecorator
from typing import Any, Callable, TypeVar
from loguru import logger

T = TypeVar("T", bound=Callable[..., Any])


class timed_operation(ContextDecorator):
    """Контекстный менеджер и декоратор для замера времени выполнения операции.

    Пример использования:
        with timed_operation("Поиск тендеров"):
            await do_search()

        @timed_operation("Анализ")
        async def analyze():
            ...
    """

    def __init__(self, name: str):
        self.name = name
        self.start_time: float = 0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.perf_counter() - self.start_time
        logger.info("{} завершено за {:.2f}с", self.name, elapsed)

    def __call__(self, func: T) -> T:
        if asyncio.iscoroutinefunction(func):

            async def async_wrapper(*args, **kwargs):
                with self:
                    return await func(*args, **kwargs)

            return async_wrapper  # type: ignore
        else:

            def sync_wrapper(*args, **kwargs):
                with self:
                    return func(*args, **kwargs)

            return sync_wrapper  # type: ignore


class StageStats:
    """Сбор и вывод статистики этапа."""

    def __init__(self, stage_name: str):
        self.stage_name = stage_name
        self.start_time = time.perf_counter()
        self.processed = 0
        self.success = 0
        self.failed = 0

    def add(self, success: bool = True):
        self.processed += 1
        if success:
            self.success += 1
        else:
            self.failed += 1

    def log_final(self):
        elapsed = time.perf_counter() - self.start_time
        avg_time = elapsed / self.processed if self.processed > 0 else 0
        ratio = (self.success / self.processed * 100) if self.processed > 0 else 0

        logger.info("=== Статистика {}: ===", self.stage_name)
        logger.info("  Всего обработано: {}", self.processed)
        logger.info("  Успешно: {} ({:.1f}%)", self.success, ratio)
        logger.info("  Ошибок: {}", self.failed)
        logger.info("  Общее время: {:.1f}с", elapsed)
        logger.info("  Среднее время на объект: {:.2f}с", avg_time)
        logger.info("============================")
