from pathlib import Path

from click import Path as PathParamType
from click import command, option

from elva.cli import context


@command(name="config")
@option(
    "--include/--exclude",
    "-i/-x",
    "defaults",
    help="Include or exclude default config file paths.",
    default=True,
    show_default=True,
)
@option(
    "--file",
    "-f",
    "files",
    multiple=True,
    help="Path to config file. Can be given multiple times.",
    type=PathParamType(
        path_type=Path,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        writable=False,
        executable=False,
        resolve_path=True,
        allow_dash=False,
    ),
)
@context
def cli() -> None:
    """
    Configure config files.
    """
    return
