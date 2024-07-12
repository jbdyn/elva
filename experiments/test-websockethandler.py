import logging
from time import sleep

from elva.log import (
    DefaultFormatter,
    WebsocketHandler,
)

# URI = "ws://localhost:8000/log/home/someuser/projects/elva/.elva/elva.log"
URI = "ws://localhost:8000"

log = logging.getLogger(__name__)
websocket_handler = WebsocketHandler(URI)
websocket_handler.setFormatter(DefaultFormatter())
log.addHandler(websocket_handler)
log.setLevel(logging.DEBUG)

try:
    while True:
        log.debug("DEBUG")
        sleep(1)
        log.info("INFO")
        sleep(1)
        log.warning("WARNING")
        sleep(1)
        log.error("ERROR")
        sleep(1)
        log.critical("CRITICAL")
        sleep(1)
except KeyboardInterrupt:
    # websocket_handler.sock.close()
    exit()
