"""
Module providing the main command line interface functionality.
"""

from functools import wraps
from pathlib import Path
from typing import Any, Callable

from click import (
    Context,
    Parameter,
    ParamType,
    option,
)
from click import (
    Path as PathParamType,
)
from click import (
    pass_context as ctx,
)

from elva.files import get_data_file_path


def context(arg: Callable | None = None) -> Callable:
    """
    Make a function return the subcommand.

    Arguments:
        arg: the first argument needed for convenient operation with and without paranthesis.

    Returns:
        the decorated function.
    """

    def _context(cmd: Callable) -> Callable:
        """
        Command decorator for returning the CLI context and the command function in a mapping.

        Arguments:
            fn: the command to get the CLI context from.

        Returns:
            the wrapped command.
        """

        # wrap the command to let `wrapper` look like `cmd`
        # (same name and docstring) but with altered signature
        @wraps(cmd)
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
            # save the decorated routine as an attribute as config alteration
            # routine
            ctx.alter = cmd

            # map the command's name to its context
            return {
                ctx.command.name: ctx,
            }

        return __context

    # make decorator work with and without paranthesis
    if callable(arg):
        return _context(arg)
    else:
        return _context


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
"""
The data file option for an ELVA app command.
"""


class TranslatedChoice(ParamType):
    """
    A choice from flag to parameter name translation mapping.
    """

    name = "choice"

    def __init__(self, translate: dict) -> None:
        """
        Arguments:
            translate: the flag to parameter name mapping.
        """
        self.translate = translate

    def convert(self, value: str, param: Parameter, ctx: Context) -> str:
        """
        Convert the parsed CLI value to the parameter name.

        Arguments:
            value: the parsed CLI value.
            param: the associated Parameter instance.
            ctx: the current parameter context instance.

        Returns:
            the parameter name.
        """
        tr = self.translate

        try:
            return tr[value]
        except KeyError:
            self.fail(
                f"'{value}' is not a valid choice. Use one from {list(tr.keys())}"
            )


def unset(translate: dict) -> Callable:
    """
    Return the configured `--unset` commandline option.

    Arguments:
        translate: the translation mapping from flag to parameter names.

    Returns:
        the configured `--unset` commandline option.
    """
    return option(
        "--unset",
        "-?",
        "unset",
        metavar="ENTRY",
        multiple=True,
        show_choices=False,
        help="Unset the value of a command option. Can be given multiple times.",
        type=TranslatedChoice(translate),
    )
