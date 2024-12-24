from typing import Any, AsyncGenerator, Callable, Coroutine, ParamSpec
import asyncio
import logging
from contextlib import suppress
from functools import wraps

_LOGGER = logging.getLogger(__name__)

_P = ParamSpec('_P')


def cleanup_ctx(
	func: Callable[_P, Coroutine[Any, Any, None]]
) -> Callable[_P, AsyncGenerator[None, None]]:
	@wraps(func)
	async def wrapper(*args, **kwargs) -> AsyncGenerator[None, None]:
		task = asyncio.create_task(func(*args, **kwargs))
		yield
		task.cancel()
		with suppress(asyncio.CancelledError):
			await task

	return wrapper


def periodic_updates(interval: float, backoff: float):
	"""
	Decorator to run an async function periodically with retries on errors.

	Args:
		interval (float): Interval between normal successful repetitions (in seconds).
		backoff (float): Fixed backoff for retries after an error (in seconds).
	"""
	def decorator(
		func: Callable[_P, Coroutine[Any, Any, Any]],
	) -> Callable[_P, Coroutine[Any, Any, None]]:
		@wraps(func)
		async def wrapper(*args, **kwargs):
			while True:
				try:
					await func(*args, **kwargs)
				except asyncio.CancelledError:
					raise
				except Exception:
					_LOGGER.exception(f'Error occurred while running "{func.__name__}": retrying in {backoff} seconds...')
					await asyncio.sleep(backoff)
				else:
					await asyncio.sleep(interval)
		return wrapper
	return decorator
