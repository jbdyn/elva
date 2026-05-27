from click import command, echo, option
from tomli_w import dumps

from elva.cli import context, data, unset
from elva.config import Config, convert
from elva.files import Metadata

TRANSLATIONS = {
    "config": "config",
    "c": "config",
    "file": "data",
    "f": "data",
}
"""
Table for translation from flag to parameter names.
"""


def run(config: Config) -> None:
    """
    Run the app.

    This command stringifies all parameter values for the TOML serializer.

    Arguments:
        config: the merged config.
    """
    # alias
    c = config

    # extract interesting settings before
    dump = c.get("config.dump", False)
    replace = c.get("config.replace", True)

    if not c.get("context.config", False):
        c.pop("config", None)

    # remove own context
    own = config.pop("context", {})

    # write to file if desired
    if (file := own.get("data", None)) and dump:
        with Metadata(file) as metadata:
            metadata.set_config(config, replace=replace)

    echo(dumps(convert(config)))


@command(name="context")
@option(
    "--config",
    "-c",
    "config",
    is_flag=True,
    help="Show config parameters as well.",
)
@data
@unset(TRANSLATIONS)
@context
def cli(config: dict) -> None:
    """
    Print the parameters passed to apps and other subcommands.
    \f

    Arguments:
        config: the merged `context` config section.
    """
    return run
