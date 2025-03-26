"""
Module specifying the logger context variable and the default formatter.

When writing an ELVA app, both objects are vital for a seamless integration into the suite.

Example:

```python
import logging
from elva.log import LOGGER_NAME, DefaultFormatter

# Do not set LOGGER_NAME in the module's global scope
# as it would hold the wrong name in other modules
# importing from this one.

if __name__ == "__main__":
    LOGGER_NAME.set(__name__)

    # setup logging handler
    handler = logging.FileHandler("./some.log")
    handler.setFormatter(DefaultFormatter())

    # add handler to module logger
    log = logging.getLogger(__name__)
    log.addHandler(handler)

```
"""

import logging
import logging.handlers
from contextvars import ContextVar

LOGGER_NAME: ContextVar = ContextVar("logger_name")
"""
Context variable supposed to hold the logger name.

This variable is read by the Component class on initialization.
"""


###
#
# formatter
#
class DefaultFormatter(logging.Formatter):
    """
    Default formatter for ELVA apps.

    It extends log messages with the following scheme:

        [<time>] [<log message level>] [<logger name>] <message>

    where `<time>` follows the [ISO 8601 standard](https://www.iso.org/iso-8601-date-and-time-format.html) with

        YYYY-MM-DD hh:mm:ss
    """

    def __init__(self):
        fmt = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
        datefmt = "%Y-%m-%d %H:%M:%S"
        super().__init__(fmt=fmt, datefmt=datefmt)
