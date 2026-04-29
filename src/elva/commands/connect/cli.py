from click import INT, command, option

from elva.cli import context


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
@option(
    "--safe/--unsafe",
    "-s",
    "safe",
    is_flag=True,
    help="Try to establish a safe connection.",
    default=None,
)
@context
def cli() -> None:
    """
    Configure connection details.
    """
    return
