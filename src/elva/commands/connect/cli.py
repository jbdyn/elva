from click import INT, command, option

from elva.cli import context, unset

TRANSLATE = {
    "host": "host",
    "h": "host",
    "port": "port",
    "p": "port",
    "identifier": "identifier",
    "i": "identifier",
}
"""
Table for translation from flag to parameter names.
"""


@command(name="connect")
@option(
    "--host",
    "-h",
    "host",
    metavar="ADDRESS",
    help="Host of the syncing server.",
)
@option(
    "--port",
    "-p",
    "port",
    type=INT,
    help="Port of the syncing server.",
)
@option(
    "--identifier",
    "-i",
    "identifier",
    help="Unique identifier of the shared document.",
)
@unset(TRANSLATE)
@context
def cli(config: dict) -> None:
    """
    Configure connection details.
    \f

    Arguments:
        config: the merged `connect` config section.
    """
    return
