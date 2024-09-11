import importlib
import logging
from pathlib import Path

import click
import platformdirs
from rich import print

from elva.utils import gather_context_information

###
#
# global defaults
#
# names
APP_NAME = "elva"
CONFIG_NAME = APP_NAME + ".toml"

# sort logging levels by verbosity
# source: https://docs.python.org/3/library/logging.html#logging-levels
LEVEL = [
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


###
#
# paths
#
def find_config_path():
    cwd = Path.cwd()
    for path in [cwd] + list(cwd.parents):
        config = path / CONFIG_NAME
        if config.exists():
            return config


config_path = find_config_path()
if config_path is not None:
    project_path = config_path.parent
else:
    project_path = None

default_config_path = Path(platformdirs.user_config_dir(APP_NAME)) / CONFIG_NAME
CONFIG_PATH = config_path or default_config_path


###
#
# cli input callbacks
#
def log_callback_order(ctx: click.Context, param: click.Parameter, value):
    ctx.ensure_object(dict)
    c = ctx.obj
    name = param.name

    try:
        c["order"].append(name)
    except KeyError:
        c["order"] = [name]

    return value


def ensure_dir(ctx: click.Context, param: click.Parameter, path: None | Path):
    if path is not None:
        path = path.resolve()
        if path.is_dir():
            path.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)

    return log_callback_order(ctx, param, path)


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
    help="path to logging file",
    type=click.Path(path_type=Path, dir_okay=False),
    callback=ensure_dir,
)
# logging
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
    "--user",
    "-u",
    "user",
    help="username",
    callback=log_callback_order,
)
@click.option(
    "--password",
    "-p",
    "password",
    help="password",
    callback=log_callback_order,
)
@click.option(
    "--server",
    "-s",
    "server",
    help="URI of the syncing server",
    callback=log_callback_order,
)
@click.option(
    "--identifier",
    "-i",
    "identifier",
    help="identifier for the document",
    callback=log_callback_order,
)
@click.option(
    "--message-type",
    "-m",
    "message_type",
    help="protocol used to connect to the syncing server",
    envvar="ELVA_MESSAGE_TYPE",
    show_envvar=True,
    default="yjs",
    show_default=True,
    type=click.Choice(["yjs", "elva"], case_sensitive=False),
    callback=log_callback_order,
)
#
# function definition
#
def elva(
    ctx: click.Context,
    config: Path,
    log: Path,
    verbose: int,
    user: str,
    password: str,
    server: str | None,
    identifier: str | None,
    message_type: str,
):
    """ELVA - A suite of real-time collaboration TUI apps."""

    ctx.ensure_object(dict)
    c = ctx.obj

    # paths
    c["project"] = project_path
    c["config"] = config
    c["file"] = None
    c["render"] = None
    c["log"] = log

    # logging
    c["level"] = LEVEL[verbose]

    # connection
    c["user"] = user
    c["password"] = password
    c["identifier"] = identifier
    c["server"] = server
    c["message_type"] = message_type.lower()


###
#
# config
#
@elva.command
@click.pass_context
@click.argument(
    "file",
    required=False,
    type=click.Path(path_type=Path, dir_okay=False),
)
def context(ctx: click.Context, file: None | Path):
    """print the context passed to subcommands"""
    c = ctx.obj

    gather_context_information(ctx, file)

    # sanitize password output
    if c["password"] is not None:
        c["password"] = "[REDACTED]"

    # TODO: print config in TOML syntax, so that it can be piped directly
    print(c)


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
