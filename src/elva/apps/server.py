"""
ELVA server app.
"""

import logging
import signal
import sys
from pathlib import Path

import anyio
import click

from elva.auth import DummyAuth, LDAPBasicAuth
from elva.log import LOGGER_NAME, DefaultFormatter
from elva.server import ElvaWebsocketServer, WebsocketServer
from elva.utils import gather_context_information

log = logging.getLogger(__name__)


async def main(
    messages: str,
    host: str,
    port: int,
    persistent: bool,
    path: None | Path,
    ldap: None | bool,
    dummy: bool,
):
    """
    Main app routine.

    Starts a server component and handles process signals.

    Arguments:
        messages: the message type to use.
        host: the host address to listen on for new connections.
        port: the port to listen on for new connections.
        persistent: flag whether to store Y updates somewhere.
        path: path where to store Y updates. If `None`, Y updates are stored in volatile memory, else under the given path.
        ldap: flag whether to use LDAP self bind authentication.
        dummy: flag whether to use dummy authentication.
    """
    if ldap is not None:
        process_request = LDAPBasicAuth(*ldap).authenticate
    elif dummy:
        process_request = DummyAuth("dummy").authenticate
    else:
        process_request = None

    options = dict(
        host=host,
        port=port,
        persistent=persistent,
        path=path,
        process_request=process_request,
    )

    match messages:
        case "yjs" | None:
            Server = WebsocketServer
        case "elva":
            Server = ElvaWebsocketServer

    server = Server(**options)

    async with anyio.create_task_group() as tg:
        await tg.start(server.start)
        with anyio.open_signal_receiver(signal.SIGINT, signal.SIGTERM) as signals:
            async for signum in signals:
                if signum == signal.SIGINT:
                    server.log.info("process received SIGINT")
                else:
                    server.log.info("process received SIGTERM")

                await server.stop()
                break


@click.command()
@click.pass_context
@click.argument("host", required=False)
@click.argument("port", required=False)
@click.option(
    "--persistent",
    # one needs to set this manually here since one cannot use
    # the keyword argument `type=click.Path(...)` as it would collide
    # with `flag_value=""`
    metavar="[DIRECTORY]",
    help=(
        "Hold the received content in a local YDoc in volatile memory "
        "or also save it under DIRECTORY if given. "
        "Without this flag, the server simply broadcasts all incoming messages "
        "within the respective room."
    ),
    # explicitely stating that the argument to this option is optional
    # see: https://github.com/pallets/click/pull/1618#issue-649167183
    is_flag=False,
    # used when no argument is given to flag
    flag_value="",
)
@click.option(
    "--ldap",
    metavar="REALM SERVER BASE",
    help="Enable Basic Authentication via LDAP self bind.",
    nargs=3,
    type=str,
)
@click.option(
    "--dummy",
    help="Enable Dummy Basic Authentication. DO NOT USE IN PRODUCTION.",
    is_flag=True,
)
def cli(
    ctx: click.Context,
    host: str,
    port: int,
    persistent: None | str,
    ldap: str,
    dummy: bool,
):
    """
    Run a websocket server.
    \f

    Arguments:
        ctx: the click context holding the configuration parameter object.
        host: the host address to listen on for new connections.
        port: the port to listen on for new connections.
        persistent: flag whether and how Y updates should be stored.
        ldap: flag how to setup an LDAP self bind authentication.
        dummy: flag whether to use dummy authentication.
    """

    gather_context_information(ctx, app="server")

    match persistent:
        # no flag given
        case None:
            path = None
        # flag given, but without a path
        case "":
            path = None
            persistent = True
        # anything else, i.e. a flag given with a path
        case _:
            path = Path(persistent).resolve()
            if path.exists() and not path.is_dir():
                raise click.BadArgumentUsage(
                    f"the given path '{path}' is not a directory", ctx
                )
            path.mkdir(exist_ok=True, parents=True)
            persistent = True

    c = ctx.obj

    # logging
    LOGGER_NAME.set(__name__)
    if c["log"] is not None:
        log_handler = logging.FileHandler(c["log"])
    else:
        log_handler = logging.StreamHandler(sys.stdout)
    log_handler.setFormatter(DefaultFormatter())
    log.addHandler(log_handler)
    if c["level"] is None:
        level = logging.INFO
    else:
        level = min(logging.INFO, c["level"])
    log.setLevel(level)

    for name, param in [
        ("persistent", persistent),
        ("path", path),
        ("ldap", ldap),
        ("dummy", dummy),
    ]:
        if c.get(name) is None:
            c[name] = param

    for name, param in (("host", host), ("port", port)):
        if param is not None:
            c[name] = param

    anyio.run(
        main,
        c["messages"],
        c["host"],
        c["port"],
        c["persistent"],
        c["path"],
        c["ldap"],
        c["dummy"],
    )
