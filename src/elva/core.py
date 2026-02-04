"""
Definition of library constants.
"""

from ipaddress import ip_address

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

PORT = 41536
"""Default port for server and client connections."""


def is_valid_ip(address: str) -> bool:
    """
    Check whether the given address is a valid IPv4 or IPv6 address.

    Arguments:
        address: the address to check.

    Returns:
        `True` if `address` is a valid IPv4 or IPv6 address, else `False`.
    """
    try:
        ip_address(address)
        return True
    except ValueError:
        return False


def needs_port(address: str) -> bool:
    """
    Check whether the given address needs a port to be defined.

    Arguments:
        address: the address to check.

    Returns:
        `True` if `address` needs a port defined, else `False`.
    """
    return address in LOCAL_HOSTS or is_valid_ip(address)


def update_port(address: str, port: int | None = None) -> int | None:
    """
    Set the default ELVA port if necessary.

    Arguments:
        address: the address to check for the need of a port.
        port: the port to return if no default is needed.

    Returns:
        the updated port.
    """
    if port is None and needs_port(address):
        return PORT
    else:
        return port
