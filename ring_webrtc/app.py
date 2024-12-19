import logging

from aiohttp import web
from ring_doorbell import (
    Ring,
    RingDoorBell,
)
from ring_doorbell.webrtcstream import RingWebRtcStream

_LOGGER = logging.getLogger(__name__)


def create_whep_app(ring: Ring):
    """
    Creates and initializes the Ring WHEP server
    """

    app = web.Application()

    async def get_camera(device_id: str) -> RingDoorBell:
        """
        Retrieve the named (or first available if no name) Ring camera.
        This assumes the account has at least one camera.
        """

        if not ring.devices_data:
            await ring.async_update_devices()

        camera = next((
            camera for camera in ring.video_devices()
            if camera.device_id == device_id
        ), None)

        if camera is None:
            raise RuntimeError(f'No such camera "{device_id}" could be found')

        return camera

    async def whep_handler(request: web.Request) -> web.Response:
        """
        WHEP endpoint: Handle HTTP GET for consuming (egress) WebRTC answers.
        This initiates a WebRTC session with the Ring camera and returns the SDP answer.
        """

        device_id: str = request.match_info['device_id']
        offer = (await request.text()).replace('H265', 'H264')
        session_id = RingWebRtcStream.get_sdp_session_id(offer)

        _LOGGER.info(f'Starting WebRTC session "{session_id}" for device "{device_id}"')

        try:
            camera = await get_camera(device_id)
            answer = await camera.generate_webrtc_stream(offer, keep_alive_timeout=None)
            return web.Response(text=answer, status=201, headers={
                'Location': f'/{device_id}/whep/{session_id}',
            })
        except Exception:
            _LOGGER.exception('Error starting WebRTC session')
            return web.Response(status=500, text='Failed to start WebRTC session')

    async def whep_resource_handler(request: web.Request) -> web.Response:
        """
        WHEP ICE Candidate endpoint: Handle HTTP GET for ICE candidates.
        """
        session_id: str = request.match_info['session_id']
        device_id: str = request.match_info['device_id']

        _LOGGER.info(f'Terminating WebRTC session "{session_id}" for device "{device_id}"')

        try:
            camera = await get_camera(device_id)
            await camera.close_webrtc_stream(session_id)
            return web.Response(status=204)
        except Exception:
            _LOGGER.exception(f'Error deleting WebRTC session')
            return web.Response(status=500, text='Failed to terminate WebRTC session')

    app.router.add_post('/{device_id}/whep', whep_handler)
    app.router.add_delete('/{device_id}/whep/{session_id}', whep_resource_handler)

    return app
