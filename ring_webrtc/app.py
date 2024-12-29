import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Coroutine

from aiohttp import web
from ring_doorbell import Ring, RingDoorBell
from ring_doorbell.webrtcstream import RingWebRtcStream

from ring_webrtc.middleware import CREATE_TASK

from .decorators import cleanup_ctx, periodic_updates

_LOGGER = logging.getLogger(__name__)


@dataclass
class RuntimeData:
	ring_api: Ring
	update_lock: asyncio.Lock

RUNTIME_DATA = web.AppKey('RUNTIME_DATA', RuntimeData)


def create_whep_app(
	ring: Ring,
	*,
	update_interval: int=3600,
	backoff_interval: int=60,
):
	app = web.Application()

	app[RUNTIME_DATA] = RuntimeData(
		ring_api=ring,
		update_lock=asyncio.Lock(),
	)

	app.router.add_view('/{device_id}/whep', WhepView)
	app.router.add_view('/{device_id}/whep/{session_id}', WhepResourceView)

	@cleanup_ctx
	@periodic_updates(
		interval=update_interval,
		backoff=backoff_interval,
	)
	async def update_devices(app: web.Application):
		async with app[RUNTIME_DATA].update_lock:
			_LOGGER.info('Updating Ring devices...')
			await ring.async_update_devices()
			_LOGGER.info('Ring devices updated')

	app.cleanup_ctx.append(update_devices)

	return app


class CameraDeviceView(web.View):
	@property
	def data(self) -> RuntimeData:
		return self.request.app[RUNTIME_DATA]

	@property
	def device_id(self) -> str:
		return self.request.match_info['device_id']

	async def get_camera(self) -> RingDoorBell:
		async with self.data.update_lock:
			camera = next((
				camera for camera in self.data.ring_api.video_devices()
				if camera.device_id == self.device_id
			), None)

		if camera is None:
			raise RuntimeError(f'No such camera "{self.device_id}" could be found')

		return camera


class WhepView(CameraDeviceView):
	async def post(self) -> web.Response:
		offer = (await self.request.text()).replace('H265', 'H264')
		session_id = RingWebRtcStream.get_sdp_session_id(offer)
		assert session_id, 'Invalid SDP offer'

		_LOGGER.info(f'Starting WebRTC session "{session_id}" for device "{self.device_id}"')

		async def check_session_exists(camera: RingDoorBell, session_id: str):
			while session_id in camera._webrtc_streams:
				await asyncio.sleep(60)

		try:
			camera = await self.get_camera()
			answer = await camera.generate_webrtc_stream(offer, keep_alive_timeout=None)
			if CREATE_TASK in self.request:
				self.request[CREATE_TASK](
					check_session_exists(camera, session_id),
				)
			return web.Response(text=answer, status=201, headers={
				'Location': f'/{self.device_id}/whep/{session_id}',
			})
		except Exception:
			_LOGGER.exception('Error starting WebRTC session')
			return web.Response(status=500, text='Failed to start WebRTC session')


class WhepResourceView(CameraDeviceView):
	async def delete(self) -> web.Response:
		session_id: str = self.request.match_info['session_id']

		_LOGGER.info(f'Terminating WebRTC session "{session_id}" for device "{self.device_id}"')

		try:
			camera = await self.get_camera()
			await camera.close_webrtc_stream(session_id)
			return web.Response(status=204)
		except Exception:
			_LOGGER.exception(f'Error deleting WebRTC session')
			return web.Response(status=500, text='Failed to terminate WebRTC session')
