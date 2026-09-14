from __future__ import annotations

from collections.abc import Callable
from typing import Any


class LocalTask:
    """Small Celery-compatible wrapper used by the standalone desktop runtime."""

    def __init__(self, function: Callable[..., Any], *, bind: bool = False):
        self.function = function
        self.bind = bind
        self.__name__ = function.__name__
        self.__doc__ = function.__doc__

    def run(self, *args: Any, **kwargs: Any) -> Any:
        if self.bind:
            return self.function(self, *args, **kwargs)
        return self.function(*args, **kwargs)


class LocalTaskRegistry:
    """Implement the subset of ``Celery.task`` required by app.tasks."""

    def task(self, *decorator_args: Any, **decorator_kwargs: Any):
        bind = bool(decorator_kwargs.get("bind", False))

        def decorate(function: Callable[..., Any]) -> LocalTask:
            return LocalTask(function, bind=bind)

        if decorator_args and callable(decorator_args[0]):
            return decorate(decorator_args[0])
        return decorate
