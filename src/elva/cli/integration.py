"""
Module providing the main command line interface functionality.
"""

from functools import partial, wraps
from pathlib import Path
from typing import Any, Callable

from click import (
    Context,
    Parameter,
    option,
)
from click import (
    Path as PathParamType,
)
from click import (
    pass_context as ctx,
)

from elva.files import get_data_file_path


def context(arg: Callable | None = None, /, cmd: bool = False) -> Callable:
    """
    Make a function return the subcommand.

    Arguments:
        arg: the first argument needed for convenient operation with and without paranthesis.
        cmd: flag whether to include decorated function in the returned mapping.

    Returns:
        the decorated function.
    """

    def _context(fn: Callable) -> Callable:
        """
        Command decorator for returning the CLI context and the command function in a mapping.

        Arguments:
            fn: the command to get the CLI context from.

        Returns:
            the wrapped command.
        """

        # wrap the command to let `wrapper` look like `cmd`
        # (same name and docstring) but with altered signature
        @wraps(fn)
        @ctx
        def __context(ctx: Context, **kwargs: Any) -> Any:
            """
            Command wrapper returning the CLI context and, the command function if `cmd` is `True`.

            Arguments:
                ctx: the context of the current command invokation.
                kwargs: keyword arguments passed in from the CLI parser.

            Returns:
                the mapping of the command name to its associated CLI context.
            """
            # map the command's name to its context
            mapping = {
                ctx.command.name: ctx,
            }

            if cmd:
                # include the command function itself
                mapping["cmd"] = fn

            return mapping

        return __context

    # make decorator work with and without paranthesis
    if callable(arg):
        return _context(arg)
    else:
        return _context


app = partial(context, cmd=True)
"""App subcommand decorator returning a routine to run in addition to its CLI context."""


#
# CONFIGURATION READING AND MERGING
#


def resolve_data_file_path(ctx: Context, param: Parameter, path: Path) -> None | Path:
    """
    CLI callback ensuring a correct and resolved data file path.

    Arguments:
        ctx: the context of the current command invokation.
        param: the data file CLI parameter object.
        path: the value of the data file CLI parameter.

    Returns:
        the correct and resolved data file path if given else `None`.
    """
    if path is not None:
        path = get_data_file_path(path)

    return path


data = option(
    "--file",
    "-f",
    "data",
    help="Set the path to the data file.",
    type=PathParamType(
        path_type=Path,
        exists=False,
        file_okay=True,
        dir_okay=False,
        readable=True,
        writable=True,
        executable=False,
        resolve_path=True,
        allow_dash=False,
    ),
    callback=resolve_data_file_path,
)
