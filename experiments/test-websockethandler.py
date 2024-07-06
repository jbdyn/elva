import logging
from logging.handlers import DEFAULT_TCP_LOGGING_PORT, SocketHandler
from time import sleep

from elva.log import DefaultFormatter, get_default_handler

socket_handler = SocketHandler("localhost", DEFAULT_TCP_LOGGING_PORT)
socket_handler.setFormatter(DefaultFormatter())

log = logging.getLogger(__name__)
log.addHandler(get_default_handler("ws://localhost:8000"))
# log.addHandler(socket_handler)
log.setLevel(logging.DEBUG)

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
