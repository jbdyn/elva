from pathlib import Path

from click import IntRange, command, option
from click import Path as PathParamType

from elva.cli import context


@command(name="render")
@option(
    "--auto/--manual",
    "-a/-m",
    "auto",
    help="Enable or disable automatic rendering of the file contents.",
    default=None,
)
@option(
    "--timeout",
    "-t",
    "timeout",
    metavar="INTEGER",
    help="The time interval in seconds between consecutive renderings.",
    type=IntRange(min=0),
)
@option(
    "--file",
    "-f",
    help="Path to rendered file.",
    type=PathParamType(
        path_type=Path,
        exists=False,
        file_okay=True,
        dir_okay=False,
        readable=False,
        writable=True,
        executable=False,
        resolve_path=True,
        allow_dash=False,
    ),
)
@context
def cli() -> None:
    """
    Configure file rendering.
    """
    return
