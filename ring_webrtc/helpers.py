from typing import Any, AsyncGenerator, Callable, Coroutine
import asyncio
from contextlib import suppress
from functools import wraps

from aiohttp import web


def cleanup_ctx(
	func: Callable[[web.Application], Coroutine[Any, Any, Any]]
) -> Callable[[web.Application], AsyncGenerator[None, None]]:
	@wraps(func)
	async def wrapper(app: web.Application) -> AsyncGenerator[None, None]:
		task = asyncio.create_task(func(app))
		yield
		task.cancel()
		with suppress(asyncio.CancelledError):
			await task

	return wrapper
