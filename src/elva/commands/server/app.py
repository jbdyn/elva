"""
App definition.
"""

import anyio
from websockets.asyncio.server import basic_auth

from elva.auth import DummyAuth, LDAPAuth
from elva.server import WebsocketServer, free_tcp_port


async def main(config: dict):
    """
    Main app routine.

    Starts a server component and handles process signals.

    Arguments:
        config: configuration parameter mapping.
    """
    connect = config.get("connect", {})

    host = connect.get("host", "0.0.0.0")
    port = connect.get("port") or free_tcp_port()

    server = config.get("server", {})
    persistent = server.get("persistent", False)
    directory = server.get("directory")
    ldap = server.get("ldap")
    dummy = server.get("dummy", False)

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
        path=directory,
        process_request=process_request,
    )

    async with anyio.create_task_group() as tg:
        await tg.start(server.start)
