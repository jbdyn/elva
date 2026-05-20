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
@option(
    "--dump/--no-dump",
    "-d/-nd",
    "dump",
    help="Dump config or leave data file metadata config untouched.",
    default=True,
)
@option(
    "--replace/--merge",
    "-r/-m",
    "replace",
    help="Merge or replace metadata config with collected config.",
    default=False,
)
@context
def cli() -> None:
    """
    Configure config files.
    """
    return
