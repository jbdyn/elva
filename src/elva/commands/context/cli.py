from click import command, echo, option
from tomli_w import dumps

from elva.cli import app, data
from elva.config import Config, convert


@command(name="context")
@option(
    "--config",
    "-c",
    "config",
    is_flag=True,
    help="Show config parameters as well.",
)
@data
@app
def cli(config: Config) -> None:
    """
    Print the parameters passed to apps and other subcommands.
    \f

    This command stringifies all parameter values for the TOML serializer.

    Arguments:
        config: mapping of merged configuration parameters from various sources.
    """
    if not config.get("context.config", False):
        config.pop("config", None)

    config.pop("context", None)

    echo(dumps(convert(config)))
