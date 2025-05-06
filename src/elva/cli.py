"""
Module providing the main command line interface functionality.

Subcommands are defined in the respective app module.
"""

import importlib
import logging
from pathlib import Path

import click
import platformdirs
from click.core import ParameterSource
from rich import print

from elva.utils import gather_context_information

###
#
# global defaults
#
# names
APP_NAME = "elva"
"""Default app name."""

CONFIG_NAME = APP_NAME + ".toml"
"""Default ELVA configuration file name."""

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
"""Logging levels sorted by verbosity."""


###
#
# paths
#

CONFIG_PATHS = list()
"""List containing all found default ELVA configuration file paths."""

USER_HOME_CONFIG = Path(platformdirs.user_config_dir(APP_NAME)) / CONFIG_NAME
"""Path to the calling system user's ELVA configuration file."""

if USER_HOME_CONFIG.exists():
    CONFIG_PATHS.append(USER_HOME_CONFIG)


def find_config_path():
    """
    Find the next ELVA configuration file.

    This function searches the directory tree from bottom to top.
    """
    cwd = Path.cwd()
    for path in [cwd] + list(cwd.parents):
        config = path / CONFIG_NAME
        if config.exists():
            return config


config_path = find_config_path()

PROJECT_PATH = None
"""The path to the current active project."""

if config_path is not None:
    CONFIG_PATHS.insert(0, config_path)
    PROJECT_PATH = config_path.parent


###
#
# cli input callbacks
#
def resolve_configs(
    ctx: click.Context, param: click.Parameter, paths: None | list[Path]
) -> list[Path]:
    """
    Hook sanitizing configuration file paths on invoking the ELVA command.

    Arguments:
        ctx: the click context of the current invokation.
        param: the parameter currently being parsed.
        paths: the paths given to the parameter.

    Returns:
        a list of paths to all given and found ELVA configuration files.
    """
    if paths is not None:
        paths = [path.resolve() for path in paths]
        param_source = ctx.get_parameter_source(param.name)
        if not param_source == ParameterSource.DEFAULT:
            paths.extend(CONFIG_PATHS)

    return paths


def resolve_log(
    ctx: click.Context, param: click.Parameter, log: None | Path
) -> None | Path:
    """
    Hook sanitizing the log file path on invoking the ELVA command.

    Arguments:
        ctx: the click context of the current invokation.
        param: the parameter currently being parsed.
        log: the path of the log file given to the parameter.

    Returns:
       the resolved path of the log file if one was given, else `None`.
    """
    if log is not None:
        log = log.resolve()

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
    "--config",
    "-c",
    "configs",
    help="Path to config file or directory. Can be specified multiple times.",
    envvar="ELVA_CONFIG_PATH",
    multiple=True,
    show_envvar=True,
    # a list, as multiple=True
    default=CONFIG_PATHS,
    show_default=True,
    type=click.Path(path_type=Path),
    callback=resolve_configs,
)
@click.option(
    "--log",
    "-l",
    "log",
    help="Path to logging file.",
    envvar="ELVA_LOG",
    show_envvar=True,
    type=click.Path(path_type=Path, dir_okay=False),
    callback=resolve_log,
)
# logging
@click.option(
    "--verbose",
    "-v",
    "verbose",
    help="Verbosity of logging output.",
    count=True,
    default=LEVEL.index(logging.INFO),
    type=click.IntRange(0, 5, clamp=True),
)
#
# connection information
#
@click.option(
    "--name",
    "-n",
    "name",
    help="User display username.",
    envvar="ELVA_NAME",
    show_envvar=True,
)
@click.option(
    "--user",
    "-u",
    "user",
    help="Username for authentication.",
    envvar="ELVA_USER",
    show_envvar=True,
)
@click.option(
    "--password",
    "-p",
    "password",
    help="Password for authentication",
    # we don't support bad secret management,
    # so the password is not settable via an envvar
)
@click.option(
    "--server",
    "-s",
    "server",
    help="URI of the syncing server.",
    envvar="ELVA_SERVER",
    show_envvar=True,
)
@click.option(
    "--identifier",
    "-i",
    "identifier",
    help="Unique identifier of the shared document.",
    envvar="ELVA_IDENTIFIER",
    show_envvar=True,
)
@click.option(
    "--messages",
    "-m",
    "messages",
    help="Protocol used to connect to the syncing server.",
    envvar="ELVA_MESSAGES",
    show_envvar=True,
    type=click.Choice(["yjs", "elva"], case_sensitive=False),
)
#
# function definition
#
def elva(
    ctx: click.Context,
    configs: list[Path],
    log: Path,
    verbose: int,
    name: str,
    user: str,
    password: str,
    server: str | None,
    identifier: str | None,
    messages: str,
):
    """
    ELVA - A suite of real-time collaboration TUI apps.
    \f

    Arguments:
        ctx: the click context holding the configuration parameter object.
        configs: list of configuration files to parse.
        log: path of the log file.
        verbose: verbosity, i.e. log level, indicator from 0 (no logging) to 5 (log everything).
        name: the name to display instead of the user name.
        user: the user name to login with.
        password: the password to login with.
        server: the address of the remote server for synchronization.
        identifier: the identifier of the Y document.
        messages: the type of messages to use for synchronization.
    """

    ctx.ensure_object(dict)
    c = ctx.obj

    # paths
    c["project"] = PROJECT_PATH
    c["configs"] = configs
    c["file"] = None
    c["render"] = None
    c["log"] = log

    # logging
    c["level"] = LEVEL[verbose]

    # connection
    c["name"] = name
    c["user"] = user
    c["password"] = password
    c["identifier"] = identifier
    c["server"] = server
    c["messages"] = messages


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
@click.option(
    "--app",
    "-a",
    "app",
    metavar="APP",
    help="Include the parameters defined in the app.APP config file section.",
)
def context(ctx: click.Context, file: None | Path, app: None | str):
    """
    Print the parameters passed to apps and other subcommands.

    Arguments:
        ctx: the click context holding the configuration parameter object.
        file: the path to the ELVA SQLite database file.
        app: the app section to take additional configuration parameters from.
    """
    c = ctx.obj

    gather_context_information(ctx, file, app)

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
