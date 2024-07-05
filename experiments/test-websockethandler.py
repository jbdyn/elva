import logging
from time import sleep

from elva.log import get_default_handler

log = logging.getLogger(__name__)
log.addHandler(get_default_handler("ws://localhost:8000"))
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
