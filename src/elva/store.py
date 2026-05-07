"""
Module holding store components.
"""

from contextlib import closing
from sqlite3 import connect
from tomllib import loads
from typing import Any, Callable

from anyio import (
    CancelScope,
    Lock,
    Path,
    WouldBlock,
    create_memory_object_stream,
)
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from deepmerge import always_merger
from pycrdt import Doc, Subscription, TransactionEvent
from sqlite_anyio import connect as aconnect
from sqlite_anyio.sqlite import Connection, Cursor
from tomli_w import dumps

from elva.component import Component, create_component_state
from elva.protocol import EMPTY_UPDATE

# TODO: check performance


deepmerge = always_merger.merge
"""
Deepmerge two dictionaries.
"""


def operate(path: Path, fn: Callable, *args: Any, **kwargs: Any) -> Any:
    """
    Open an SQLite database for performing an operation on it.

    The operation `fn` gets the database connection passed as
    first positional argument.

    Arguments:
        path: the file path to the SQLite database.
        fn: the operation to perform.
        args: positional arguments for the operation.
        kwargs: keyword arguments for the operation.

    Returns:
        the return value of the operation.
    """
    with closing(connect(path)) as db:
        return fn(db, *args, **kwargs)


def _get_metadata(db: Connection, key: str) -> dict:
    """
    Retrieve metadata of a given key from an ELVA SQLite database.

    Arguments:
        db: the database connection.
        key: the key to fetch the value of.

    Returns:
        the metadata associated with the given key.
    """
    cur = db.cursor()

    cur.execute("SELECT value FROM metadata WHERE key = ?", [key])
    res = cur.fetchall()

    if res:
        # there is just one value, i.e. a single row with a single column
        res = loads(res[0][0].decode())
    else:
        res = dict()

    return res


def get_metadata(path: Path, key: str) -> dict:
    """
    Retrieve metadata of a given key from a given ELVA SQLite database.

    Arguments:
        path: path to the ELVA SQLite database.
        key: the key to fetch the value of.

    Raises:
        FileNotFoundError: if there is no file present.

    Returns:
        the metadata associated with the given key.
    """
    if not path.exists():
        raise FileNotFoundError("no such file or directory")

    return operate(path, _get_metadata, key)


def _set_metadata(
    db: Connection,
    key: str,
    data: dict,
    *,
    replace: bool = False,
) -> None:
    """
    Insert or replace mapped metadata at the given key.

    Arguments:
        db: the database connection.
        key: the key associated with the metadata.
        data: mapping to update or replace with.
        replace: flag whether to just insert or update keys (`False`) or
          to delete absent keys as well (`True`).
    """
    cur = db.cursor()

    res = _get_metadata(db, key)

    # the presence of `key` determines how to insert the new data
    update = key in res

    if replace:
        res.pop(key, None)

    # merge data and save serialized to TOML
    res = deepmerge(res, data)

    # convert object to bytes
    value = dumps(res).encode()

    if update:
        cur.execute("UPDATE metadata SET value = ? WHERE key = ?", [value, key])
    else:
        cur.execute("INSERT INTO metadata VALUES (?, ?)", [key, value])

    # commit the changes
    db.commit()


def set_metadata(
    path: Path,
    key: str,
    data: dict,
    *,
    replace: bool,
) -> None:
    """
    Insert or replace mapped metadata at the given key.

    Arguments:
        path: path to the ELVA SQLite database.
        key: the key associated with the metadata.
        data: mapping to update or replace with.
        replace: flag whether to just insert or update keys (`False`) or
          to delete absent keys as well (`True`).
    """
    return operate(path, _set_metadata, key, data, replace=replace)


def _get_updates(db: Connection) -> list[tuple]:
    """
    Retrieve all Y updates from an ELVA data file.

    Arguments:
        db: the database connection.

    Returns:
        a list of single-length tuples with a Y update each.
    """
    cur = db.cursor()

    cur.execute("SELECT * FROM yupdates")

    return cur.fetchall()


def get_updates(path: Path) -> list[tuple]:
    """
    Retrieve all Y updates from an ELVA data file.

    Arguments:
        path: the file path to an ELVA data file.

    Returns:
        a list of single-length tuples with a Y update each.
    """
    return operate(path, _get_updates)


SQLiteStoreState = create_component_state("SQLiteStoreState")
"""The states of the [`SQLiteStore`][elva.store.SQLiteStore] component."""


class SQLiteStore(Component):
    """
    Store component saving Y updates in an ELVA SQLite database.
    """

    ydoc: Doc
    """Instance of the synchronized Y Document."""

    identifier: str
    """Identifier of the synchronized Y Document."""

    path: Path
    """Path where to store the SQLite database."""

    _lock: Lock
    """Object for restricted resource management."""

    _subscription: Subscription
    """(while running) Object holding subscription information to changes in [`ydoc`][elva.store.SQLiteStore.ydoc]."""

    _stream_send: MemoryObjectSendStream
    """(while running) Stream to send Y Document updates or flow control objects to."""

    _stream_recv: MemoryObjectReceiveStream
    """(while running) Stream to receive Y Document updates or flow control objects from."""

    _db: Connection
    """(while running) SQLite connection to the database file at [`path`][elva.store.SQLiteStore.path]."""

    _cursor: Cursor
    """(while running) SQLite cursor operating on the [`_db`][elva.store.SQLiteStore._db] connection."""

    def __init__(self, ydoc: Doc, identifier: str | None, path: str):
        """
        Arguments:
            ydoc: instance of the synchronized Y Document.
            identifier: identifier of the synchronized Y Document. If `None`, it is tried to be retrieved from the `metadata` table in the SQLite database.
            path: path where to store the SQLite database.
        """
        self.ydoc = ydoc
        self.identifier = identifier
        self.path = Path(path)
        self._lock = Lock()

    @property
    def states(self) -> SQLiteStoreState:
        """The states this component can have."""
        return SQLiteStoreState

    async def get_metadata(self, key: str) -> dict:
        """
        Retrieve metadata from a given ELVA SQLite database.

        Arguments:
            key: the key to retrieve values for.

        Returns:
            mapping of metadata values.
        """
        await self._cursor.execute("SELECT value FROM metadata where key = ?", [key])
        res = await self._cursor.fetchall()

        if res:
            return loads(res[0][0].decode())
        else:
            return {}

    async def set_metadata(self, key: str, data: dict, *, replace: bool = False):
        """
        Set given config in a given ELVA SQLite database.

        Arguments:
            key: the metadata key to update or replace.
            data: mapping of value to update or replace with.
            replace: flag whether to just insert or update keys (`False`) or to delete absent keys as well (`True`).
        """
        async with self._lock:
            cur = self._cursor

            # ensure `metadata` table
            await cur.execute(
                "CREATE TABLE IF NOT EXISTS metadata (key PRIMARY KEY, value BLOB)"
            )

            # read TOML serialized value
            res = await self.get_metadata(key)

            empty = len(res) == 0

            if replace:
                res.pop(key, None)

            # merge config and save serialized to TOML
            res = deepmerge(res, data)

            value = dumps(res).encode()

            if empty:
                await cur.execute(
                    "INSERT INTO metadata (key, value) VALUES (?, ?)", [key, value]
                )
            else:
                await cur.execute(
                    "UPDATE metadata SET value = ? WHERE key = ?", [value, key]
                )

            await self._db.commit()

        # ensure to update the identifier if given
        self.identifier = res.get("connect", {}).get("identifier") or self.identifier

    async def get_updates(self) -> list:
        """
        Read out the updates saved in the file.

        Returns:
            a list of updates in the order they were applied to the YDoc.
        """
        await self._cursor.execute("SELECT yupdate FROM yupdates")
        updates = await self._cursor.fetchall()

        if updates:
            self.log.debug("read updates from file")
        else:
            self.log.debug("found no updates in file")

        return updates

    def _on_transaction_event(self, event: TransactionEvent):
        """
        Hook called on changes in [`ydoc`][elva.store.SQLiteStore.ydoc].

        When called, the `event` data are written to the ELVA SQLite database.

        Arguments:
            event: object holding event information of changes in [`ydoc`][elva.store.SQLiteStore.ydoc].
        """
        self.log.debug(f"transaction event triggered with update {event.update}")
        self._stream_send.send_nowait(event.update)

    async def _ensure_metadata_table(self):
        """
        Hook called before the store sets its `RUNNING` state to ensure a table `config` exists.
        """
        async with self._lock:
            await self._cursor.execute(
                "CREATE TABLE IF NOT EXISTS metadata (key PRIMARY KEY, value BLOB)"
            )

            await self._db.commit()

        self.log.debug("ensured metadata table")

    async def _ensure_identifier(self):
        """
        Hook called before the store sets its `started` signal to ensure the UUID of the YDoc contents is saved.
        """
        key = "config"

        async with self._lock:
            res = await self.get_metadata(key)
            self.identifier = self.identifier or res.get("connect", {}).get(
                "identifier"
            )

            if self.identifier is not None:
                empty = len(res) == 0

                res.setdefault("connect", {})
                res["connect"]["identifier"] = self.identifier

                value = dumps(res).encode()

                if empty:
                    await self._cursor.execute(
                        "INSERT INTO metadata VALUES (?, ?)", [key, value]
                    )
                else:
                    await self._cursor.execute(
                        "UPDATE metadata SET value = ? WHERE key = ?", [value, key]
                    )

                await self._db.commit()

        self.log.debug("ensured identifier")

    async def _ensure_update_table(self):
        """
        Hook called before the store sets its `started` signal to ensure a table `yupdates` exists.
        """
        async with self._lock:
            await self._cursor.execute(
                "CREATE TABLE IF NOT EXISTS yupdates (yupdate BLOB)"
            )

            await self._db.commit()

        self.log.debug("ensured update table")

    async def _merge(self):
        """
        Hook to read in and apply updates from the ELVA SQLite database and             write divergent history updates to file.
        """
        # get updates stored in file
        updates = await self.get_updates()

        # the given ydoc might not be empty;
        # we append the resulting update to file as otherwise
        # histories would not be restored correctly and callbacks not triggered,
        # even when sequential updates from this history branch are applied
        temp = Doc()

        for update, *_ in updates:
            temp.apply_update(update)

        # get divergent update before we apply updates from file to `self.ydoc`
        divergent_update = self.ydoc.get_update(state=temp.get_state())

        # cleanup unused resources
        del temp

        # apply updates
        for update, *_ in updates:
            self.ydoc.apply_update(update)

        if updates:
            self.log.debug("applied updates from file")

        # append a non-empty update to a divergent history branch to file as well
        if divergent_update != EMPTY_UPDATE:
            # shield the write so content won't get lost
            with CancelScope(shield=True):
                await self._write(divergent_update)

            self.log.debug("appended divergent history update to file")

    async def _initialize(self):
        """
        Hook initializing the database, i.e. ensuring the presence of connection and the ELVA SQL database scheme.
        """
        # connect
        await self._connect_database()

        # ensure tables and identifier
        await self._ensure_metadata_table()
        await self._ensure_identifier()
        await self._ensure_update_table()

        # merge updates from file with the contents from the given YDoc
        await self._merge()

        self.log.info("initialized database")

    async def _connect_database(self):
        """
        Hook connecting to the data base path.
        """
        self._db = await aconnect(self.path)
        self._cursor = await self._db.cursor()

        self.log.debug(f"connected to database {self.path}")

    async def _disconnect_database(self):
        """
        Hook closing the database connection if initialized.
        """
        if hasattr(self, "_db"):
            await self._db.close()
            self.log.debug("closed database")

            # cleanup closed resources
            del self._db

        if hasattr(self, "_cursor"):
            # cleanup closed resources
            del self._cursor

    async def _write(self, update: bytes):
        """
        Hook writing `update` to the `yupdates` ELVA SQLite database table.

        Arguments:
            update: the update to write to the ELVA SQLite database file.
        """
        async with self._lock:
            await self._cursor.execute(
                "INSERT INTO yupdates VALUES (?)",
                [update],
            )
            await self._db.commit()

        self.log.debug(f"wrote update {update} to file {self.path}")

    async def before(self):
        """
        Hook executed before the component sets its `RUNNING` state.

        The ELVA SQLite database is being initialized and read.
        Also, the component subscribes to changes in [`ydoc`][elva.store.SQLiteStore.ydoc].
        """
        # initialize tables and table content
        await self._initialize()

        # initialize streams
        self._stream_send, self._stream_recv = create_memory_object_stream(
            max_buffer_size=65536
        )
        self.log.debug("instantiated buffer")

        # start watching for updates on the YDoc
        self._subscription = self.ydoc.observe(self._on_transaction_event)
        self.log.debug("subscribed to YDoc updates")

    async def run(self):
        """
        Hook writing updates from the internal buffer to file.
        """
        self.log.debug("listening for updates")

        async for update in self._stream_recv:
            self.log.debug(f"received update {update}")

            with CancelScope(shield=True):
                # writing needs to be shielded from cancellation,
                # but is required to return quickly
                await self._write(update)

    async def cleanup(self):
        """
        Hook cancelling subscription to changes and closing the database.
        """
        if hasattr(self, "_subscription"):
            # unsubscribe from YDoc updates, otherwise transactions will fail
            self.ydoc.unobserve(self._subscription)
            del self._subscription
            self.log.debug("unsubscribed from YDoc updates")

        if hasattr(self, "_stream_recv"):
            # drain the buffer and write the remaining updates to file
            while True:
                try:
                    update = self._stream_recv.receive_nowait()
                    await self._write(update)
                except WouldBlock:
                    break

            self.log.debug("drained buffer")

            # remove buffer
            del self._stream_send, self._stream_recv
            self.log.debug("deleted buffer")

        # now we can close the file
        await self._disconnect_database()
