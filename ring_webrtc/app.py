import asyncio
import logging

from aiohttp import web
from ring_doorbell import Ring, RingDoorBell
from ring_doorbell.webrtcstream import RingWebRtcStream

from .decorators import cleanup_ctx, periodic_updates

APP_RING_API = web.AppKey('ring_api', Ring)
APP_UPDATE_LOCK = web.AppKey('update_lock', asyncio.Lock)
APP_UPDATE_INTERVAL = web.AppKey('update_lock', float)
APP_BACKOFF_INTERVAL = web.AppKey('update_lock', float)

_LOGGER = logging.getLogger(__name__)


def create_whep_app(
	ring: Ring,
	*,
	update_interval: int=3600,
	backoff_interval: int=60,
):
	app = web.Application()

	app[APP_RING_API] = ring
	app[APP_UPDATE_LOCK] = asyncio.Lock()
	app[APP_UPDATE_INTERVAL] = update_interval
	app[APP_BACKOFF_INTERVAL] = backoff_interval

	app.router.add_view('/{device_id}/whep', WhepView)
	app.router.add_view('/{device_id}/whep/{session_id}', WhepResourceView)

	@cleanup_ctx
	@periodic_updates(
		interval=app[APP_UPDATE_INTERVAL],
		backoff=app[APP_BACKOFF_INTERVAL],
	)
	async def update_devices(app: web.Application):
		while True:
			async with app[APP_UPDATE_LOCK]:
				_LOGGER.info('Updating Ring devices...')
				await app[APP_RING_API].async_update_devices()
				_LOGGER.info('Ring devices updated')

			await asyncio.sleep(app[APP_UPDATE_INTERVAL])

	app.cleanup_ctx.append(update_devices)

	return app


class CameraDeviceView(web.View):
	@property
	def ring_api(self) -> Ring:
		return self.request.app[APP_RING_API]

	@property
	def device_id(self) -> str:
		return self.request.match_info['device_id']

	async def get_camera(self) -> RingDoorBell:
		async with self.request.app[APP_UPDATE_LOCK]:
			camera = next((
				camera for camera in self.ring_api.video_devices()
				if camera.device_id == self.device_id
			), None)

		if camera is None:
			raise RuntimeError(f'No such camera "{self.device_id}" could be found')

		return camera


class WhepView(CameraDeviceView):
	async def post(self) -> web.Response:
		offer = (await self.request.text()).replace('H265', 'H264')
		session_id = RingWebRtcStream.get_sdp_session_id(offer)

		_LOGGER.info(f'Starting WebRTC session "{session_id}" for device "{self.device_id}"')

		try:
			camera = await self.get_camera()
			answer = await camera.generate_webrtc_stream(offer, keep_alive_timeout=None)
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
