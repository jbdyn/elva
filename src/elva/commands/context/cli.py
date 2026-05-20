from collections.abc import Mapping, Sequence
from typing import Any

from click import command, echo
from tomli_w import dumps

from elva.cli import app, data
from elva.config import Config


def convert(item: Any) -> Any:
    """
    Make an item TOML-serializable.

    Containers are converted recursively.

    Arguments:
        item: the item to convert.

    Returns:
        the TOML-serializable conversion of the given item.
    """
    if isinstance(item, Sequence) and not isinstance(item, str):
        return list(convert(i) for i in item)
    elif isinstance(item, Mapping):
        return dict((key, convert(i)) for key, i in item.items())
    elif type(item) not in (str, bool, int, float):
        return str(item)
    else:
        return item


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
