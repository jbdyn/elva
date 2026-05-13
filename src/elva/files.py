"""
Module providing the main command line interface functionality.
"""

from pathlib import Path

from elva.core import (
    FILE_SUFFIX,
    LOG_SUFFIX,
)


def get_data_file_path(path: Path) -> Path:
    """
    Ensure a correct and resolved data file path.

    Arguments:
        path: the path to the data file.

    Returns:
        the correct and resolved data file path.
    """
    if path.is_dir():
        raise ValueError(f"{path} is a directory")

    # resolve given path
    path = path.resolve()

    # append the ELVA data file suffix if necessary
    if FILE_SUFFIX not in path.suffixes:
        path = path.with_name(path.name + FILE_SUFFIX)

    return path


def derive_stem(path: Path, extension: None | str = None) -> Path:
    """
    Derive the data file stem.

    Arguments:
        path: the path to the data file.
        extension: the extension to add to the stem.

    Returns:
        the data file stem.
    """
    # collect all present suffixes
    suffixes = "".join(path.suffixes)

    # get the data file basename
    name = path.name.removesuffix(suffixes)

    # strip all suffixes after the data file suffix
    suffixes = suffixes.split(FILE_SUFFIX, maxsplit=1)[0]

    # translate absent extension definition
    if extension is None:
        extension = ""

    # exchange the file name
    return path.with_name(name + suffixes + extension)


def get_render_file_path(path: Path) -> Path:
    """
    Derive the render file path from the path to a data file.

    Arguments:
        path: the path to the data file.

    Returns:
        the path to the rendered file.
    """
    return derive_stem(path)


def get_log_file_path(path: Path) -> Path:
    """
    Derive the log file path from the path to a data file.

    Arguments:
        path: the path to the data file.

    Returns:
        the path to the log file.
    """
    return derive_stem(path, extension=LOG_SUFFIX)
