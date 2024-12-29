from typing import (
    Callable,
    Self,
)
import asyncio
import signal
from datetime import (
    datetime,
    timezone,
)
import logging

from aiohttp.web import Application

_LOGGER = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc)


# Global shutdown function
def shutdown(_: Application) -> None:
    """
    Default shutdown function to send a SIGTERM to the current process.
    """

    _LOGGER.info("Sending SIGTERM to terminate the application.")
    signal.raise_signal(signal.SIGTERM)


class TaskWaitGroup:
    """
    Tracks active tasks and allows managing the group as a single unit.
    """
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()
        self._group_task: asyncio.Task | None = None
        self._done_callbacks: list[Callable[[Self], object]] = []

    def __bool__(self) -> bool:
        return bool(self._tasks)

    def __len__(self) -> int:
        return len(self._tasks)

    def add(self, task: asyncio.Task) -> None:
        """
        Add a task to the wait group.
        """
        if self._group_task is not None:
            raise RuntimeError("Cannot add tasks to a running group.")

        self._tasks.add(task)
        _LOGGER.debug(f"Tracking new task: {task}. Total tasks: {len(self._tasks)}")

    def remove(self, task: asyncio.Task) -> None:
        """
        Remove a task from the wait group.
        """
        if self._group_task is not None:
            raise RuntimeError("Cannot remove tasks from a running group.")

        self._tasks.discard(task)
        _LOGGER.debug(f"Task removed: {task}. Remaining tasks: {len(self._tasks)}")

    def run(self) -> asyncio.Task:
        """
        Run all tasks in the group concurrently and optionally attach a callback.
        """
        if self._group_task is not None:
            return self._group_task

        _LOGGER.debug(f"Running {len(self._tasks)} tasks concurrently.")
        self._group_task = asyncio.create_task(
            asyncio.wait(self._tasks, return_when=asyncio.ALL_COMPLETED)
        )

        self._group_task.add_done_callback(self._on_group_done)

        return self._group_task

    def _on_group_done(self, _: asyncio.Task) -> None:
        _LOGGER.debug("Task group completed.")
        self._tasks.clear()
        self._group_task = None

        for callback in self._done_callbacks:
            try:
                callback(self)
            except Exception:
                _LOGGER.error(f'Error in task group callback')

    def add_done_callback(self, callback: Callable[[Self], object]) -> None:
        """
        Add a callback to the group task.
        """
        self._done_callbacks.append(callback)
