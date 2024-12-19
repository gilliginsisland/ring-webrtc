import argparse
import logging
from pathlib import Path

from aiohttp import web
from ring_doorbell import (
	Auth,
	Ring,
)
from ring_doorbell.const import (
	CLI_TOKEN_FILE,
	USER_AGENT,
)

from .token_manager import TokenManager
from .app import create_whep_app

LOG_LEVELS = [logging.WARNING, logging.INFO, logging.DEBUG]


def main():
	parser = argparse.ArgumentParser(
		prog='RingWebRTC',
		description='WHEP proxy for accessing ring cameras with WebRTC',
	)
	parser.add_argument(
		'-a', '--address',
		help='The address to listen on.',
		default='0.0.0.0',
	)
	parser.add_argument(
		'-p', '--port',
		help='The port to listen on.',
		type=int,
		default=8080,
	)
	parser.add_argument(
		'-f', '--token-file',
		help='The file where the ring auth token is stored.',
		type=Path,
		default=Path(CLI_TOKEN_FILE),
	)
	parser.add_argument(
		'-v', '--verbose',
		help='Increase logging level. Defaults to WARN. Use -v for INFO and -vv for DEBUG.',
		action='count',
		default=0,
	)

	args = parser.parse_args()

	level = LOG_LEVELS[min(args.verbose, len(LOG_LEVELS) - 1)]  # cap to last level index
	logging.basicConfig(level=level)

	if not args.token_file.is_file():
		raise ValueError("Token file not found. Please run the ring-doorbell command to generate a token file.")

	token_manager = TokenManager(args.token_file)

	# Authenticate and create a Ring object
	auth = Auth(
		user_agent=USER_AGENT,
		token=token_manager.token,
		token_updater=token_manager.update_token,
	)
	ring = Ring(auth)

	logging.info(f"Starting web application on {args.address}:{args.port}")
	web.run_app(create_whep_app(ring), host=args.address, port=args.port)

if __name__ == '__main__':
	main()
