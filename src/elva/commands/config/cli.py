from pathlib import Path

from click import Path as PathParamType
from click import command, option

from elva.cli import context, unset

TRANSLATE = {
    "defaults": "defaults",
    "include": "defaults",
    "i": "defaults",
    "exclude": "defaults",
    "x": "defaults",
    "files": "files",
    "file": "files",
    "f": "files",
    "dump": "dump",
    "d": "dump",
    "no-dump": "dump",
    "nd": "dump",
    "replace": "replace",
    "r": "replace",
    "merge": "replace",
    "m": "replace",
}
"""
Table for translations from flag to parameter names.
"""


@command(name="config")
@option(
    "--include/--exclude",
    "-i/-x",
    "defaults",
    help="Include or exclude default config file paths.",
    default=True,
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
    default=None,
)
@option(
    "--replace/--merge",
    "-r/-m",
    "replace",
    help="Merge or replace metadata config with collected config.",
    default=None,
)
@unset(TRANSLATE)
@context
def cli(config: dict) -> None:
    """
    Configure config files.
    \f

    Arguments:
        config: the merged `config` config section.
    """
    # alias
    c = config

    for param in set(c.pop("unset", [])):
        c.pop(param, None)
