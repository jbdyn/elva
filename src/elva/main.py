"""
Module with the entry point for the `elva` command.

Subcommands are defined in the respective app package.
"""

from importlib import import_module as import_
from pathlib import Path

from setuptools import find_namespace_packages

from elva.cli import elva
from elva.core import ELVA_COMMAND_DIR_NAME, get_command_import_path

# read all other present commands
pkgs = find_namespace_packages(Path(__file__).parent / ELVA_COMMAND_DIR_NAME)
commands = [get_command_import_path(pkg) for pkg in pkgs]

# import `cli` functions of command packages
for command in commands:
    module = import_(command)
    elva.add_command(module.cli)

if __name__ == "__main__":
    elva()
