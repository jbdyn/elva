"""
CLI definition.
"""

from importlib import import_module as import_
from pathlib import Path

from click import Path as PathParamType
from click import UsageError, command, option

from elva.cli import app


@command(name="server")
@option(
    "--persistent",
    "-p",
    is_flag=True,
    default=None,
)
@option(
    "--directory",
    "-d",
    help="Path to stored data files.",
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
def cli(config: dict, *args: tuple, **kwargs: dict) -> None:
    """
    Run a WebSocket server.
    \f

    Arguments:
        config: the merged configuration parameters from CLI and files.
        args: unused positional arguments.
        kwargs: parameters passed from the CLI.
    """
    # imports
    logging = import_("logging")
    sys = import_("sys")

    anyio = import_("anyio")

    _log = import_("elva.log")
    app = import_(".app", __package__)

    # logging
    _log.LOGGER_NAME.set(__package__)
    log = logging.getLogger(__package__)

    if file := config.get("log", {}).get("file") is not None:
        log_handler = logging.FileHandler(file)
    else:
        log_handler = logging.StreamHandler(sys.stdout)
    log_handler.setFormatter(_log.DefaultFormatter())
    log.addHandler(log_handler)

    level = config.get("log", {}).get("level") or logging.INFO
    log.setLevel(level)

    # run app, catch file permission errors with an appropriate message
    try:
        anyio.run(app.main, config)
    except PermissionError as exc:
        raise UsageError(exc)
    except KeyboardInterrupt:
        pass
