import logging
import signal
import sys
from pathlib import Path

import anyio
import click

from elva.auth import LDAPBasicAuth
from elva.component import LOGGER_NAME
from elva.log import DefaultFormatter
from elva.server import ElvaWebsocketServer, WebsocketServer

log = logging.getLogger(__name__)


async def main(message_type, host, port, persistent, path, ldap):
    if ldap is not None:
        process_request = LDAPBasicAuth(*ldap).authenticate
    else:
        process_request = None

    options = dict(
        host=host,
        port=port,
        persistent=persistent,
        path=path,
        process_request=process_request,
    )

    match message_type:
        case "yjs":
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
@click.argument("host", default="localhost")
@click.argument("port", default=8000)
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
def cli(ctx: click.Context, host, port, persistent, ldap):
    """
    Run a websocket server.

    Arguments:

        [HOST]  hostname or IP address of the server. [default: localhost]
        [PORT]  port the server listens on. [default: 8000]

    Context:

        [-m/--message-type]
    """
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
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(DefaultFormatter())
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)

    anyio.run(main, c["message_type"], host, port, persistent, path, ldap)
