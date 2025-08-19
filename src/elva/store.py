"""
Module holding store components.
"""

import sqlite3

import sqlite_anyio as sqlite
from anyio import (
    CancelScope,
    Lock,
    Path,
    WouldBlock,
    create_memory_object_stream,
)
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from pycrdt import Doc, Subscription, TransactionEvent
from sqlite_anyio.sqlite import Connection, Cursor

from elva.component import Component, create_component_state
from elva.protocol import EMPTY_UPDATE

# TODO: check performance


def get_metadata(path: str | Path) -> dict:
    """
    Retrieve metadata from a given ELVA SQLite database.

    Arguments:
        path: path to the ELVA SQLite database.

    Raises:
        FileNotFoundError: if there is no file present.
        sqlite3.OperationalError: if there is no `metadata` table in the database.

    Returns:
        mapping of metadata keys to values.
    """
    if not path.exists():
        raise FileNotFoundError("no such file or directory")

    db = sqlite3.connect(path)
    cur = db.cursor()

    try:
        res = cur.execute("SELECT * FROM metadata")
    except sqlite3.OperationalError:
        # no existing `metadata` table, hence no ELVA SQLite database
        db.close()
        raise
    else:
        res = dict(res.fetchall())
    finally:
        db.close()

    return res


def set_metadata(path: str | Path, metadata: dict[str, str], replace: bool = False):
    """
    Set `metadata` in an ELVA SQLite database at `path`.

    Arguments:
        path: path to the ELVA SQLite database.
        metadata: mapping of metadata keys to values.
        replace: flag whether to just insert or update keys (`False`) or to delete absent keys as well (`True`).
    """
    db = sqlite3.connect(path)
    cur = db.cursor()

    try:
        if replace:
            cur.execute("DROP TABLE IF EXISTS metadata")

        # ensure `metadata` table with `key` being primary, i.e. unique
        cur.execute("CREATE TABLE IF NOT EXISTS metadata(key PRIMARY KEY, value)")

        for key, value in metadata.items():
            # check for each item separately
            try:
                # insert non-existing `key` with `value`
                cur.execute(
                    "INSERT INTO metadata VALUES (?, ?)",
                    (key, value),
                )
            except sqlite3.IntegrityError:  # `UNIQUE` constraint failed
                # update existing `key` with value
                cur.execute(
                    "UPDATE metadata SET value = ? WHERE key = ?",
                    (value, key),
                )

        # commit the changes
        db.commit()
    except sqlite3.OperationalError:
        # something went wrong, so we need to close the database cleanly
        db.close()

        # reraise for the application to handle this
        raise
    finally:
        db.close()


def get_updates(path):
    db = sqlite3.connect(path)
    cur = db.cursor()

    try:
        res = cur.execute("SELECT * FROM yupdates")
        updates = res.fetchall()
        return updates
    except sqlite3.OperationalError:
        db.close()
        raise
    finally:
        db.close()


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

    async def get_metadata(self) -> dict:
        """
        Retrieve metadata from a given ELVA SQLite database.

        Returns:
            mapping of metadata keys to values.
        """
        await self._cursor.execute("SELECT * FROM metadata")
        res = await self._cursor.fetchall()

        return dict(res)

    async def set_metadata(self, metadata: dict, replace: bool = False):
        """
        Set given metadata in a given ELVA SQLite database.

        Arguments:
            metadata: mapping of metadata keys to values.
            replace: flag whether to just insert or update keys (`False`) or to delete absent keys as well (`True`).
        """
        async with self._lock:
            if replace:
                await self._cursor.execute("DELETE FROM metadata")

            for key, value in metadata.items():
                # check for each item separately
                try:
                    await self._cursor.execute(
                        "INSERT INTO metadata VALUES (?, ?)", (key, value)
                    )
                except sqlite3.IntegrityError:
                    await self._cursor.execute(
                        "UPDATE metadata SET value = ? WHERE key = ?", (value, key)
                    )

            await self._db.commit()

        # ensure to update the identifier if given
        self.identifier = metadata.get("identifier", None) or self.identifier

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
        Hook called before the store sets its `RUNNING` state to ensure a table `metadata` exists.
        """
        async with self._lock:
            await self._cursor.execute(
                "CREATE TABLE IF NOT EXISTS metadata(key PRIMARY KEY, value)"
            )
            await self._db.commit()

        self.log.debug("ensured metadata table")

    async def _ensure_identifier(self):
        """
        Hook called before the store sets its `started` signal to ensure the UUID of the YDoc contents is saved.
        """
        # a specific identifier was not given; try to get it from metadata
        if self.identifier is None:
            metadata = await self.get_metadata()
            self.identifier = metadata.get("identifier", None)
            return

        # a specific identifier was given; update the metadata
        async with self._lock:
            try:
                # insert non-existing identifier
                await self._cursor.execute(
                    "INSERT INTO metadata VALUES (?, ?)",
                    ["identifier", self.identifier],
                )
            except sqlite3.IntegrityError:  # UNIQUE constraint failed
                # update existing identifier
                await self._cursor.execute(
                    "UPDATE metadata SET value = ? WHERE key = ?",
                    [self.identifier, "identifier"],
                )
            finally:
                await self._db.commit()

        self.log.debug("ensured identifier")

    async def _ensure_update_table(self):
        """
        Hook called before the store sets its `started` signal to ensure a table `yupdates` exists.
        """
        async with self._lock:
            await self._cursor.execute(
                "CREATE TABLE IF NOT EXISTS yupdates(yupdate BLOB)"
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
        self._db = await sqlite.connect(self.path)
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
