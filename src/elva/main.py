"""
Module with the entry point for the `elva` command.

Subcommands are defined in the respective app package.
"""

from importlib import import_module as import_
from pathlib import Path

from elva.cli import elva
from elva.core import ELVA_COMMAND_DIR_NAME, get_command_import_path


def commands() -> list[str]:
    """
    Get all namespace package names from the ELVA command directory.

    Returns:
        the namespace package names in the ELVA command directory.
    """
    root = Path(__file__).parent / ELVA_COMMAND_DIR_NAME

    commands = list()

    # check for namespace package
    for file in root.iterdir():
        if file.is_dir() and (file / "__init__.py").exists():
            commands.append(file.name)

    return commands


# read all other present commands
paths = [get_command_import_path(path) for path in commands()]

# import `cli` functions of command packages
for path in paths:
    module = import_(path)
    elva.add_command(module.cli)

if __name__ == "__main__":
    elva()
