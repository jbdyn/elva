"""
ELVA server app.
"""

import signal

import anyio
from websockets.asyncio.server import basic_auth

from elva.auth import DummyAuth, LDAPAuth
from elva.server import WebsocketServer, free_tcp_port


async def main(config):
    """
    Main app routine.

    Starts a server component and handles process signals.

    Arguments:
        host: the host address to listen on for new connections.
        port: the port to listen on for new connections.
        persistent: flag whether to store Y updates somewhere.
        path: path where to store Y updates. If `None`, Y updates are stored in volatile memory, else under the given path.
        ldap: flag whether to use LDAP self bind authentication.
        dummy: flag whether to use dummy authentication.
    """
    c = config

    host = c.get("host", "0.0.0.0")
    port = c.get("port") or free_tcp_port()
    persistent = c.get("persistent", False)
    path = c.get("path")
    ldap = c.get("ldap")
    dummy = c.get("dummy", False)

    if ldap is not None:
        process_request = LDAPAuth(*ldap).check
    elif dummy:
        process_request = DummyAuth().check
    else:
        process_request = None

    if process_request is not None:
        process_request = basic_auth(
            realm="ELVA WebSocket Server",
            check_credentials=process_request,
        )

    server = WebsocketServer(
        host=host,
        port=port,
        persistent=persistent,
        path=path,
        process_request=process_request,
    )

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
