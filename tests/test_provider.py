import logging
import uuid

import anyio
import pytest
from pycrdt import Doc, Text

from elva.log import LOGGER_NAME
from elva.provider import WebsocketProvider
from elva.server import WebsocketServer

LOGGER_NAME.set(__name__)
log = logging.getLogger(__name__)

pytestmark = pytest.mark.anyio


# `websockets` runs only on `asyncio`, thus the `trio` backend of `anyio` fails
@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


LOCALHOST = "127.0.0.1"


def get_identifier():
    return str(uuid.uuid4())


def get_websocket_uri(port):
    return f"ws://{LOCALHOST}:{port}"


async def test_connect(free_tcp_port, tmpdir):
    """A provider connects to a server and the server spawns a room."""
    # setup local YDoc
    ydoc = Doc()

    # setup connection details
    identifier = get_identifier()
    uri = get_websocket_uri(free_tcp_port)

    # run the server
    async with WebsocketServer(
        LOCALHOST, free_tcp_port, persistent=True, path=tmpdir
    ) as server:
        # run the provider
        async with WebsocketProvider(ydoc, identifier, uri) as provider:
            # wait for the provider to be connected
            sub_provider = provider.subscribe()
            while provider.states.CONNECTED not in provider.state:
                await sub_provider.receive()
            provider.unsubscribe(sub_provider)

            # the server spawned a room
            assert identifier in server.rooms
            room = server.rooms[identifier]
            assert room.states.ACTIVE in room.state

            # wait for the room to run
            sub_room = room.subscribe()
            while room.states.RUNNING not in room.state:
                await sub_room.receive()
            room.unsubscribe(sub_room)

            # the room has started a file store
            assert hasattr(room, "store")
            store = room.store
            assert store.states.ACTIVE in store.state
            assert store.states.RUNNING in store.state


async def test_multiple_connect_no_history(free_tcp_port):
    """Two providers sync with each other on some changes after being connected."""
    # setup local YDocs
    ydoc_a = Doc()
    ydoc_a["text"] = text_a = Text()

    ydoc_b = Doc()
    ydoc_b["text"] = Text()

    # setup connection details
    identifier = get_identifier()
    uri = get_websocket_uri(free_tcp_port)

    # run the server
    async with WebsocketServer(LOCALHOST, free_tcp_port, persistent=False) as server:
        # run the providers
        async with (
            WebsocketProvider(ydoc_a, identifier, uri) as provider_a,
            WebsocketProvider(ydoc_b, identifier, uri) as provider_b,
        ):
            # the YDocs contain both nothing
            assert ydoc_a.get_state() == ydoc_b.get_state() == b"\x00"

            # wait for each provider to be connected to the server
            for provider in (provider_a, provider_b):
                sub = provider.subscribe()
                while provider.states.CONNECTED not in provider.state:
                    await sub.receive()
                provider.unsubscribe(sub)

            # check that we serve indeed our clients
            assert len(server.rooms) == 1
            assert identifier in server.rooms
            room = server.rooms[identifier]
            assert len(room.clients) == 2

            # still nothing in the YDocs
            assert ydoc_a.get_state() == ydoc_b.get_state() == b"\x00"

            # now change something in `provider_a`
            text_a += "this is going from `provider_a` to `provider_b`"

            # both YDocs have different contents
            assert ydoc_a.get_state() != ydoc_b.get_state()
            assert ydoc_a.get_state() != b"\x00"

            # wait for the YDocs to be in sync again
            while ydoc_a.get_state() != ydoc_b.get_state():
                await anyio.sleep(1e-2)

            # both YDocs hold the same content now
            assert ydoc_a.get_state() == ydoc_b.get_state()
            assert ydoc_b.get_state() != b"\x00"
            assert str(ydoc_a["text"]) == str(ydoc_b["text"])


async def test_multiple_connect_divergent_history(free_tcp_port):
    """Two providers sync their divergent histories with each other on connect."""

    # setup local YDocs
    content_a = r"a few words by `a`\n"
    ydoc_a = Doc()
    ydoc_a["text"] = Text(content_a)

    content_b = r"some more from `b`\n"
    ydoc_b = Doc()
    ydoc_b["text"] = Text(content_b)

    # setup connection details
    identifier = get_identifier()
    uri = get_websocket_uri(free_tcp_port)

    # run the server
    async with WebsocketServer(LOCALHOST, free_tcp_port, persistent=False) as server:
        # run the providers
        async with (
            WebsocketProvider(ydoc_a, identifier, uri) as provider_a,
            WebsocketProvider(ydoc_b, identifier, uri) as provider_b,
        ):
            # the YDocs hold some differing content
            assert ydoc_a.get_state() != ydoc_b.get_state()
            assert ydoc_a.get_state() != b"\x00"
            assert ydoc_b.get_state() != b"\x00"

            # wait for each provider to be connected to the server
            for provider in (provider_a, provider_b):
                sub = provider.subscribe()
                while provider.states.CONNECTED not in provider.state:
                    await sub.receive()
                provider.unsubscribe(sub)

            # check that we serve indeed our clients
            assert len(server.rooms) == 1
            assert identifier in server.rooms
            room = server.rooms[identifier]
            assert len(room.clients) == 2

            # wait for the YDocs to sync
            while ydoc_a.get_state() != ydoc_b.get_state():
                await anyio.sleep(1e-2)

            # we now have both YDocs synced with each other
            assert ydoc_a.get_state() == ydoc_b.get_state()

            # we have identical content as the union of our divergent histories
            assert str(ydoc_a["text"]) == str(ydoc_b["text"])
            assert content_a in str(ydoc_a["text"])
            assert content_a in str(ydoc_b["text"])
            assert content_b in str(ydoc_b["text"])
            assert content_b in str(ydoc_a["text"])


async def test_manual_reconnect(free_tcp_port):
    """A provider can be stopped and started in sequence."""
    # setup local YDoc
    ydoc = Doc()
    ydoc["text"] = Text("foo bar baz")

    # setup connection details
    identifier = get_identifier()
    uri = get_websocket_uri(free_tcp_port)

    async with WebsocketServer(LOCALHOST, free_tcp_port, persistent=True) as server:
        provider = WebsocketProvider(ydoc, identifier, uri)
        sub = provider.subscribe()
        async with anyio.create_task_group() as tg:
            # connect a couple of times
            for _ in range(2):
                # start the provider as task
                await tg.start(provider.start)

                # the provider is now running
                assert provider.states.RUNNING in provider.state

                # wait for it to be connected
                while provider.states.CONNECTED not in provider.state:
                    await sub.receive()

                # we are now connected
                assert provider.states.CONNECTED in provider.state
                assert len(server.rooms) == 1
                assert identifier in server.rooms
                room = server.rooms[identifier]

                # wait for the ydoc states to get synced
                while ydoc.get_state() != room.ydoc.get_state():
                    await anyio.sleep(1e-2)

                # stop the provider
                await provider.stop()

                # wait for the connection to end
                while provider.states.CONNECTED in provider.state:
                    await sub.receive()

                # the provider is neither `ACTIVE` nor `RUNNING` nor `CONNECTED` anymore
                assert provider.state == provider.states.NONE


async def test_auto_reconnect(free_tcp_port):
    """A provider retries to connect automatically when the connection was closed remotely."""
    # setup local YDoc
    ydoc = Doc()
    identifier = get_identifier()
    uri = get_websocket_uri(free_tcp_port)

    # subscribe to both provider and server state changes
    provider = WebsocketProvider(ydoc, identifier, uri)
    sub_provider = provider.subscribe()

    server = WebsocketServer(LOCALHOST, free_tcp_port, persistent=True)
    sub_server = server.subscribe()

    # run the provider
    async with provider:
        async with anyio.create_task_group() as tg:
            # run a connect and disconnect cycle a couple if times
            for _ in range(2):
                # start the server as task
                await tg.start(server.start)

                # the server is really `RUNNING`
                assert server.states.RUNNING in server.state

                # wait for the provider to retry and connect;
                while provider.states.CONNECTED not in provider.state:
                    await sub_provider.receive()

                # our connection causes a room to be present
                assert len(server.rooms) == 1
                assert identifier in server.rooms
                room = server.rooms[identifier]

                # the room we connected to is `RUNNING`
                assert room.states.RUNNING in room.state

                # stop the server, simulate connection loss
                await server.stop()

                # wait for the server to stop
                while server.state != server.states.NONE:
                    await sub_server.receive()

                assert server.states.ACTIVE not in server.state

                # wait for the provider to recognize the closed connection
                while provider.states.CONNECTED in provider.state:
                    await sub_provider.receive()

                # provider is still `RUNNING`, but not `CONNECTED` anymore,
                # so it handled the closed connection gracefully and retries now again
                assert provider.states.CONNECTED not in provider.state
                assert provider.states.RUNNING in provider.state


async def test_synchronization_from_provider_to_server(free_tcp_port):
    """The server recreates the YDoc state remotely after the provider connected."""
    # setup local YDoc
    ydoc = Doc()
    ydoc["text"] = Text("some local content")

    # we have some history stored in our local YDoc
    assert ydoc.get_state() != b"\x00"

    # setup connection details
    identifier = get_identifier()
    uri = get_websocket_uri(free_tcp_port)

    # run both the server and the provider
    async with (
        WebsocketServer(LOCALHOST, free_tcp_port, persistent=True) as server,
        WebsocketProvider(ydoc, identifier, uri) as provider,
    ):
        # wait for the provider to be connected
        sub = provider.subscribe()
        while provider.states.CONNECTED not in provider.state:
            await sub.receive()

        # the server creates a room for us
        assert len(server.rooms) == 1
        assert identifier in server.rooms
        room = server.rooms[identifier]

        # the room is running
        assert room.states.RUNNING in room.state

        # the remote YDoc is not synced yet
        assert room.ydoc.get_state() == b"\x00"

        # wait for the YDocs to get synced
        while ydoc.get_state() != room.ydoc.get_state():
            await anyio.sleep(1e-2)

        # now both local and remote YDoc are in the same state
        assert ydoc.get_state() == room.ydoc.get_state()
        assert room.ydoc != b"\x00"


async def test_synchronization_from_server_to_provider(free_tcp_port):
    """The provider recreates the remote YDoc state locally on connection."""
    # setup local YDoc
    ydoc = Doc()
    assert ydoc.get_state() == b"\x00"

    # setup connection details
    identifier = get_identifier()
    uri = get_websocket_uri(free_tcp_port)

    # run the server
    async with WebsocketServer(LOCALHOST, free_tcp_port, persistent=True) as server:
        # simulate present remote content
        room = await server.get_room(identifier)

        # there is no remote content
        assert room.ydoc.get_state() == b"\x00"

        # now there is remote content
        room.ydoc["text"] = Text("a bit of remote content already present")
        assert room.ydoc.get_state() != b"\x00"

        # run the provider
        async with WebsocketProvider(ydoc, identifier, uri) as provider:
            # wait for the provider to be connected
            sub = provider.subscribe()
            while provider.states.CONNECTED not in provider.state:
                await sub.receive()

            # the provider is connected now
            assert provider.states.CONNECTED in provider.state

            # wait for the YDocs to sync state
            while ydoc.get_state() != room.ydoc.get_state():
                await anyio.sleep(1e-2)

            # both local and remote YDocs are in the same state
            assert ydoc.get_state() == room.ydoc.get_state()


async def test_bidirectional_synchronization(free_tcp_port):
    """The provider and the server sync their divergent hostories."""
    # setup local YDoc
    content_local = "my important document locally"
    ydoc = Doc()
    ydoc["text"] = Text(content_local)

    # setup connection details
    identifier = get_identifier()
    uri = get_websocket_uri(free_tcp_port)

    # run the server
    async with WebsocketServer(LOCALHOST, free_tcp_port, persistent=True) as server:
        # simulate present remote content
        room = await server.get_room(identifier)

        # there is nothing in the remote YDoc
        assert room.ydoc.get_state() == b"\x00"

        # now there is some remote content
        content_remote = "also important stuff on server"
        room.ydoc["text"] = Text(content_remote)
        assert room.ydoc.get_state() != b"\x00"

        # run the provider
        async with WebsocketProvider(ydoc, identifier, uri) as provider:
            # wait for the provider to be connected
            sub = provider.subscribe()
            while provider.states.CONNECTED not in provider.state:
                await sub.receive()

            # the provider is connected now
            assert provider.states.CONNECTED in provider.state

            # wait for the YDoc states to get synced
            while ydoc.get_state() != room.ydoc.get_state():
                await anyio.sleep(1e-2)

            # both local and remote YDocs are in the same state
            assert ydoc.get_state() == room.ydoc.get_state()

            # both local and remote YTexts show identical content
            assert str(ydoc["text"]) == str(room.ydoc["text"])

            # local and remote content is present in both local and remote YTexts
            assert content_local in str(ydoc["text"])
            assert content_local in str(room.ydoc["text"])
            assert content_remote in str(ydoc["text"])
            assert content_remote in str(room.ydoc["text"])
