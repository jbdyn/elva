import importlib
import logging
import uuid
from pathlib import Path

import click
import platformdirs
from rich import print

from elva.provider import ElvaProvider, WebsocketElvaProvider

###
#
# global defaults
#
# names
APP_NAME = "elva"
DOT_DIR_NAME = "." + APP_NAME
CONFIG_NAME = APP_NAME + ".ini"
LOG_NAME = APP_NAME + ".log"

# sort logging levels by verbosity
# source: https://docs.python.org/3/library/logging.html#logging-levels
LEVELS = [
    # no -v/--verbose flag
    # different from logging.NOTSET
    None,
    # -v
    logging.CRITICAL,
    # -vv
    logging.ERROR,
    # -vvv
    logging.WARNING,
    # -vvvv
    logging.INFO,
    # -vvvvv
    logging.DEBUG,
]


#
# check existence of dot directory
def _find_dot_dir():
    cwd = Path.cwd()
    for path in [cwd] + list(cwd.parents):
        dot = path / DOT_DIR_NAME
        if dot.exists():
            return dot


_dot_dir = _find_dot_dir()

#
# data path
DATA_PATH = Path(_dot_dir or platformdirs.user_data_dir(APP_NAME))

#
# config path
if _dot_dir is not None:
    # as long as there is no dedicated subcommand similar to `git config`
    # to edit the configuration, the `elva.ini` config file should reside
    # next to the `.elva` dot dir and not within it for straight forward
    # access to the user
    _config_path = Path(_dot_dir).parent
else:
    _config_path = Path(platformdirs.user_config_dir(APP_NAME))

CONFIG_PATH = _config_path / CONFIG_NAME

#
# log path
LOG_PATH = Path(_dot_dir or platformdirs.user_log_dir(APP_NAME)) / LOG_NAME


###
#
# cli input callbacks
#
def ensure_dir(ctx: click.Context, param: click.Parameter, path: Path):
    path = path.resolve()
    if path.is_dir():
        path.mkdir(parents=True, exist_ok=True)
    elif path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


###
#
# cli interface definition
#
@click.group(
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
    )
)
@click.pass_context
#
# paths
#
@click.option(
    "--data",
    "-d",
    "data",
    help="path to data directory",
    envvar="ELVA_DATA_PATH",
    show_envvar=True,
    default=DATA_PATH,
    show_default=True,
    # process this first, as it might hold a config file
    is_eager=True,
    type=click.Path(path_type=Path, file_okay=False),
    callback=ensure_dir,
)
@click.option(
    "--config",
    "-c",
    "config",
    help="path to config file or directory",
    envvar="ELVA_CONFIG_PATH",
    show_envvar=True,
    default=CONFIG_PATH,
    show_default=True,
    type=click.Path(path_type=Path),
    callback=ensure_dir,
)
@click.option(
    "--log",
    "-l",
    "log",
    help="path to log file or directory",
    envvar="ELVA_LOG_PATH",
    show_envvar=True,
    default=LOG_PATH,
    show_default=True,
    type=click.Path(path_type=Path),
    callback=ensure_dir,
)
#
# behavior
#
@click.option(
    "--verbose",
    "-v",
    "verbose",
    help="verbosity of logging output",
    count=True,
    type=click.IntRange(0, 5, clamp=True),
)
#
# connection information
#
@click.option(
    "--name",
    "-n",
    "name",
    help="username",
    default=str(uuid.uuid4()),
)
@click.option(
    "--server",
    "-s",
    "server",
    help="URI of the syncing server",
)
@click.option(
    "--identifier",
    "-i",
    "identifier",
    help="identifier for the document",
)
@click.option(
    "--provider",
    "-p",
    "provider",
    help="provider name used to connect to the syncing server",
    default="ElvaProvider",
)
#
# function definition
#
def elva(
    ctx: click.Context,
    data: Path,
    config: Path,
    log: Path,
    verbose: int,
    name: str,
    server: str | None,
    identifier: str | None,
    provider: str,
):
    """ELVA - A suite of real-time collaboration TUI apps."""

    ctx.ensure_object(dict)
    settings = ctx.obj

    # paths
    settings["project"] = None if _dot_dir is None else _dot_dir.parent
    settings["data"] = data
    settings["config"] = config
    settings["log"] = log

    # logging config
    level = LEVELS[verbose]
    settings["level"] = level

    if level is not None:
        ensure_dir(log)

    # connection
    settings["identifier"] = identifier
    settings["name"] = name
    settings["server"] = server

    if provider.lower() == "elvaprovider":
        # connect to the remote websocket server directly,
        # without using the metaprovider
        uri = server
        Provider: ElvaProvider = ElvaProvider
    else:
        # connect to the local metaprovider
        if server[-1] == "/":
            uri = f"{server}{identifier}"
        else:
            uri = f"{server}/{identifier}"

        Provider: ElvaProvider = WebsocketElvaProvider

    settings["uri"] = uri
    settings["provider"] = Provider


###
#
# config
#
@elva.command
@click.pass_context
def config(ctx: click.Context):
    """print the used configuration parameter"""
    # TODO: print config in INI syntax, so that it can be piped directly
    # TODO: convert this into a command group, so one gets a git-like
    #       config interface, e.g.
    #       $ elva config name "John Doe"
    print(ctx.obj)


###
#
# init
#
@elva.command
@click.argument(
    "path",
    default=Path.cwd(),
    type=click.Path(path_type=Path, file_okay=False),
)
def init(path):
    """initialize a data directory in the current of with PATH specified directory"""
    data = path / DOT_DIR_NAME
    data.mkdir(parents=True, exist_ok=True)
    # TODO: call also `git init`


###
#
# import `cli` functions of apps
#
apps = [
    ("elva.apps.editor", "edit"),
    ("elva.apps.chat", "chat"),
    ("elva.apps.server", "serve"),
    ("elva.apps.service", "service"),
]
for app, command in apps:
    module = importlib.import_module(app)
    elva.add_command(module.cli, command)

if __name__ == "__main__":
    elva()
