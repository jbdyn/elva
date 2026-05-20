from click import command, echo
from tomli_w import dumps

from elva.cli import app, data
from elva.config import Config, convert


@command(name="context")
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
    echo(dumps(convert(config)))
