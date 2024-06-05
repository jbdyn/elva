import logging.config

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s %(name)s %(process)d %(lineno)d : %(levelname)s %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "simple": {
            "format": "%(name)s\t%(message)s",
        },
        "json": {
            "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "level": "DEBUG",
            "stream": "ext://sys.stdout",
        },
        "textual": {
            "class": "textual.logging.TextualHandler",
            "formatter": "json",
            "level": "DEBUG",
            "stderr": True,
            "stdout": True,
        },
        "rich": {
            "class": "rich.logging.RichHandler",
            "formatter": "simple",
            "level": "DEBUG",
            "markup": True,
            "rich_tracebacks": True,
        },
    },
    "loggers": {
#        "root": { # all loggers
#            "handlers": ["stdout"],
#            "level": "INFO",
#        },
        "elva": {
            "handlers": ["textual"],
            "level": "DEBUG",
        },
    },
}


logging.config.dictConfig(LOGGING)

