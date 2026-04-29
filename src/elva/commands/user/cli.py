from click import command, option

from elva.cli import context


@command(name="user")
@option(
    "--name",
    "-n",
    "name",
    help="The display user name.",
)
@context
def cli():
    """
    Configure user details.
    """
    return
