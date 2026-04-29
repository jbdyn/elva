"""
Module with the entry point for the `elva` command.

Subcommands are defined in the respective app package.
"""

from importlib import import_module as import_
from pathlib import Path

from click import group
from click import version_option as version
from setuptools import find_namespace_packages

from elva.cli import OrderedGroup, run
from elva.core import APP_NAME, ELVA_COMMAND_DIR_NAME, get_command_import_path


@group(
    cls=OrderedGroup,
    chain=True,
    result_callback=run,
)
@version(prog_name=APP_NAME)
def elva():
    """
    ELVA - A suite of real-time collaboration TUI apps.
    """
    return


# import `cli` functions of command packages
for command_name in find_namespace_packages(
    Path(__file__).parent / ELVA_COMMAND_DIR_NAME
):
    command = get_command_import_path(command_name)
    module = import_(command)
    elva.add_command(module.cli)

if __name__ == "__main__":
    elva()
