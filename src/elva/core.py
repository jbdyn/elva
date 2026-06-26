"""
Definition of library constants.
"""

APP_NAME = "ELVA"
"""Default app name."""

CONFIG_NAME = APP_NAME.lower() + ".toml"
"""Default ELVA configuration file name."""

FILE_SUFFIX = ".y"
"""Default ELVA data file suffix."""

LOG_SUFFIX = ".log"
"""Default log file suffix."""

ELVA_COMMAND_DIR_NAME = "commands"
"""Directory name where command namespace packages are searched for."""


def get_command_import_path(command: str) -> str:
    """
    Get the Python import path for an app.

    Arguments:
        command: the command namespace package name.

    Returns:
        the import path of a command namespace package.
    """
    return f"elva.{ELVA_COMMAND_DIR_NAME}.{command}"


ELVA_WIDGET_DIR_NAME = "widgets"
"""Directory name where widget namespace packages are expected."""

LOCAL_HOSTS = frozenset(["localhost", "127.0.0.1", "::1"])
"""Hostnames considered local and allowed to serve without TLS."""
