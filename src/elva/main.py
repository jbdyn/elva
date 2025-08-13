"""
Module providing the main command line interface functionality.

Subcommands are defined in the respective app module.
"""

import importlib

import click
import tomli_w

from elva.cli import (
    common_options,
    data_file_path_argument,
    pass_config,
    render_file_path_option,
)
from elva.core import APP_NAME


@click.group()
@click.version_option(prog_name=APP_NAME)
def elva():
    """
    ELVA - A suite of real-time collaboration TUI apps.
    """
    return


@elva.command
@common_options
@render_file_path_option
@click.option(
    "--app",
    "app",
    metavar="APP",
    help="Include the parameters defined in the [APP] config file table.",
)
@data_file_path_argument
@pass_config
def context(config: dict, *args: tuple, **kwargs: dict):
    """
    Print the parameters passed to apps and other subcommands in TOML format,
    optionally with parameters from data file FILE.
    \f

    This command stringifies all [`Path`][pathlib.Path] objects for the TOML
    serializer.
    Also, the password gets redacted if present.

    Arguments:
        config: mapping of merged configuration parameters from various sources.
        *args: additional positional arguments as container for passed CLI parameters.
        **kwargs: additional keyword arguments as container for passed CLI parameters.
    """
    # convert all non-string objects to strings
    if config.get("configs"):
        config["configs"] = [str(path) for path in config["configs"]]

    for param in ("file", "log", "render", "password"):
        if config.get(param):
            config[param] = str(config[param])

    click.echo(tomli_w.dumps(config))


###
#
# import `cli` functions of apps
#
apps = [
    ("elva.apps.editor", "edit"),
    ("elva.apps.chat", "chat"),
    ("elva.apps.server", "serve"),
]
for app, command in apps:
    module = importlib.import_module(app)
    elva.add_command(module.cli, command)

if __name__ == "__main__":
    elva()
