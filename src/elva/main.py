"""
Module with the entry point for the `elva` command.

Subcommands are defined in the respective app package.
"""

import importlib
from pathlib import Path

import click
import tomli_w
from setuptools import find_namespace_packages

from elva.cli import (
    common_options,
    file_paths_option_and_argument,
    pass_config,
)
from elva.core import APP_NAME, ELVA_APP_DIR_NAME, get_app_import_path


@click.group()
@click.version_option(prog_name=APP_NAME)
def elva():
    """
    ELVA - A suite of real-time collaboration TUI apps.
    """
    return


@elva.command
@common_options
@click.option(
    "--app",
    "app",
    metavar="APP",
    help="Include the parameters defined in the [APP] config file table.",
)
@file_paths_option_and_argument
@pass_config
def context(config: dict, *args: tuple, **kwargs: dict):
    """
    Print the parameters passed to apps and other subcommands.
    \f

    This command stringifies all parameter values for the TOML serializer.

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
for app_name in find_namespace_packages(Path(__file__).parent / ELVA_APP_DIR_NAME):
    app = get_app_import_path(app_name)
    module = importlib.import_module(app)
    elva.add_command(module.cli)

if __name__ == "__main__":
    elva()
