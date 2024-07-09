import importlib
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
ELVA_DOT_DIR_NAME = "." + APP_NAME
ELVA_CONFIG_NAME = APP_NAME + ".ini"
ELVA_LOG_NAME = APP_NAME + ".log"


#
# paths
def _find_dot_dir():
    cwd = Path.cwd()
    for path in [cwd] + list(cwd.parents):
        dot = path / ELVA_DOT_DIR_NAME
        if dot.exists():
            return dot


_dot_dir = _find_dot_dir()

ELVA_DATA_PATH = Path(_dot_dir or platformdirs.user_data_dir(APP_NAME))

ELVA_CONFIG_PATH = (
    Path(_dot_dir or platformdirs.user_config_dir(APP_NAME)) / ELVA_CONFIG_NAME
)

ELVA_LOG_PATH = Path(_dot_dir or platformdirs.user_log_dir(APP_NAME)) / ELVA_LOG_NAME


###
#
# cli input callbacks
#
def _ensure_dir(path: Path):
    if path.is_dir():
        path.mkdir(exist_ok=True)


def _add_to_ctx(ctx: click.Context, key: str, value):
    ctx.ensure_object(dict)
    ctx.obj[key] = value


def _handle_data(ctx: click.Context, param: click.Parameter, data: Path):
    _ensure_dir(data)
    _add_to_ctx(ctx, "data", data)
    return data


def _handle_config(ctx: click.Context, param: click.Parameter, config: Path):
    _ensure_dir(config)
    _add_to_ctx(ctx, "config", config)
    # TODO: load config here and put entries in `ctx`
    return config


def _handle_log(ctx: click.Context, param: click.Parameter, log: Path):
    _ensure_dir(log)
    _add_to_ctx(ctx, "log", log)
    return log


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
    default=ELVA_DATA_PATH,
    show_default=True,
    # process this first, as it might hold a config file
    is_eager=True,
    type=click.Path(path_type=Path, file_okay=False),
    callback=_handle_data,
)
@click.option(
    "--config",
    "-c",
    "config",
    help="path to config file or directory",
    envvar="ELVA_CONFIG_PATH",
    show_envvar=True,
    default=ELVA_CONFIG_PATH,
    show_default=True,
    type=click.Path(path_type=Path),
    callback=_handle_config,
)
@click.option(
    "--log",
    "-l",
    "log",
    help="path to log file or directory",
    envvar="ELVA_LOG_PATH",
    show_envvar=True,
    default=ELVA_LOG_PATH,
    show_default=True,
    type=click.Path(path_type=Path),
    callback=_handle_log,
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
    name: str,
    server: str | None,
    identifier: str | None,
    provider: str,
):
    """ELVA - A suite of real-time collaboration TUI apps."""

    ctx.ensure_object(dict)
    settings = ctx.obj
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
def init():
    """initialize a data directory in the current working directory"""
    data = Path.cwd() / ELVA_DOT_DIR_NAME
    data.mkdir(exist_ok=True)
    # TODO: call also `git init`


###
#
# import `cli` functions of apps
#
apps = [
    ("elva.apps.editor", "edit"),
    ("elva.apps.chat", "chat"),
    ("elva.websocket_server", "serve"),
    ("elva.service", "start"),
    ("elva.log", "log"),
]
for app, command in apps:
    module = importlib.import_module(app)
    elva.add_command(module.cli, command)

if __name__ == "__main__":
    elva()
