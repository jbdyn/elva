"""
CLI definition.
"""

import sys
from importlib import import_module as import_
from logging import INFO, FileHandler, StreamHandler, getLogger
from pathlib import Path

from anyio import run
from click import INT, UsageError, command, option
from click import Path as PathParamType

from elva.cli import app
from elva.config import Config
from elva.log import LOGGER_NAME, DefaultFormatter


@command(name="server")
@option(
    "--host",
    "-h",
    metavar="HOST",
    help="The interface to bind to.",
)
@option(
    "--port",
    "-p",
    help="The port to listen on.",
    type=INT,
)
@option(
    "--save",
    "-s",
    is_flag=True,
    help="Save changes in local documents.",
    default=None,
)
@option(
    "--directory",
    "-d",
    help="Path to stored documents.",
    type=PathParamType(
        path_type=Path,
        exists=False,
        file_okay=False,
        dir_okay=True,
        readable=True,
        writable=True,
        executable=False,
        resolve_path=True,
        allow_dash=False,
    ),
)
@option(
    "--ldap",
    metavar="REALM SERVER BASE",
    help="Enable Basic Authentication via LDAP self bind.",
    nargs=3,
    type=str,
)
@option(
    "--dummy",
    help="Enable Dummy Basic Authentication. DO NOT USE IN PRODUCTION.",
    is_flag=True,
    default=None,
)
@app
def cli(config: Config) -> None:
    """
    Run a WebSocket server.
    \f

    Arguments:
        config: the merged configuration parameters from CLI and files.
    """
    # logging
    LOGGER_NAME.set(__package__)
    log = getLogger(__package__)

    if (file := config.get("log.file")) is not None:
        handler = FileHandler(file)
    else:
        handler = StreamHandler(sys.stdout)
    handler.setFormatter(DefaultFormatter())
    log.addHandler(handler)

    level = config.get("log.level", INFO)
    log.setLevel(level)

    # defer heavy app import
    app = import_(".app", __package__)

    # run app, catch file permission errors with an appropriate message
    try:
        run(app.main, config)
    except PermissionError as exc:
        raise UsageError(exc)
    except KeyboardInterrupt:
        pass
