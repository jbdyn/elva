"""
Module holding store components.
"""

import sqlite3

import sqlite_anyio as sqlite
from anyio import (
    TASK_STATUS_IGNORED,
    CancelScope,
    Event,
    Lock,
    Path,
    create_memory_object_stream,
)
from anyio.abc import TaskStatus
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from pycrdt import Doc, Subscription, TransactionEvent
from sqlite_anyio.sqlite import Connection, Cursor

from elva.component import Component

# TODO: check performance


def get_metadata(path: str | Path) -> dict:
    """
    Retrieve metadata from a given ELVA SQLite database.

    Arguments:
        path: path to the ELVA SQLite database.

    Raises:
        sqlite3.OperationalError: if there is no `metadata` table in the database.

    Returns:
        mapping of metadata keys to values.
    """
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

    initialized: Event
    """Event being set when the SQLite database is ready to be read."""

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

    def __init__(self, ydoc: Doc, identifier: str, path: str):
        """
        Arguments:
            ydoc: instance of the synchronized Y Document.
            identifier: identifier of the synchronized Y Document.
            path: path where to store the SQLite database.
        """
        self.ydoc = ydoc
        self.identifier = identifier
        self.path = Path(path)
        self.initialized = Event()
        self._lock = Lock()

    async def get_metadata(self) -> dict:
        """
        Retrieve metadata from a given ELVA SQLite database.

        Returns:
            mapping of metadata keys to values.
        """
        await self._wait_initialized()

        async with self._lock:
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
        await self._wait_initialized()

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

    def _on_transaction_event(self, event: TransactionEvent):
        """
        Hook called on changes in [`ydoc`][elva.store.SQLiteStore.ydoc].

        When called, the `event` data are written to the ELVA SQLite database.

        Arguments:
            event: object holding event information of changes in [`ydoc`][elva.store.SQLiteStore.ydoc].
        """
        self.log.debug(f"transaction event triggered with update {event.update}")
        self._stream_send.send_nowait(event.update)

    async def _wait_initialized(self):
        """
        Hook called by `_read` and `_write` hooks to ensure the `initialized` event is set.
        """
        if self.started is None:
            raise RuntimeError(f"{self} not started")

        await self.initialized.wait()

    async def _ensure_metadata_table(self):
        """
        Hook called before the store sets its `started` signal to ensure a table `metadata` exists.
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
        if self.identifier is None:
            return

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

    async def _initialize_database(self):
        """
        Hook initializing the database, i.e. ensuring the presence of connection and the ELVA SQL database scheme.
        """
        # connect
        self._db = await sqlite.connect(self.path)
        self._cursor = await self._db.cursor()
        self.log.debug(f"connected to database {self.path}")

        # ensure tables and identifier
        await self._ensure_metadata_table()
        await self._ensure_identifier()
        await self._ensure_update_table()

        # set the initialized event
        self.initialized.set()
        self.log.info("database initialized")

    async def _disconnect_database(self):
        """
        Hook closing the database connection if initialized.
        """
        if self.initialized.is_set():
            await self._db.close()
            self.log.debug("closed database")

            # cleanup closed resources
            del self._db
            del self._cursor

    async def _listen(self, task_status: TaskStatus[None] = TASK_STATUS_IGNORED):
        """
        Hook listening for updates on [`ydoc`][elva.store.SQLiteStore.ydoc] and
        calling the [`_write`][elva.store.SQLiteStore._write] hook writing it to the database.

        Arguments:
            task_status: object signalling whether this task has been started.
        """
        # initialize streams
        self._stream_send, self._stream_recv = create_memory_object_stream(
            max_buffer_size=65543
        )

        # writing to file must not be interrupted by cancellation
        with CancelScope(shield=True):
            # start streams
            async with self._stream_send, self._stream_recv:
                self.log.debug("listening for updates")
                task_status.started()

                # take actions on updates
                async for update in self._stream_recv:
                    self.log.debug(f"received {update}")

                    if update is None:
                        # the scope of this store's task group has been cancelled
                        self.log.debug("stop listening for updates")
                        await self._disconnect_database()
                        break

                    # write update to file
                    await self._write(update)

            # cleanup closed resources
            del self._stream_send
            del self._stream_recv

    async def _write(self, update: bytes):
        """
        Hook writing `update` to the `yupdates` ELVA SQLite database table.

        Arguments:
            update: the update to write to the ELVA SQLite database file.
        """
        await self._wait_initialized()

        async with self._lock:
            await self._cursor.execute(
                "INSERT INTO yupdates VALUES (?)",
                [update],
            )
            await self._db.commit()
            self.log.debug(f"wrote {update} to file {self.path}")

    async def _read(self):
        """
        Hook to read in metadata and updates from the ELVA SQLite database and apply them.
        """
        await self._wait_initialized()

        async with self._lock:
            # read updates
            await self._cursor.execute("SELECT yupdate FROM yupdates")
            updates = await self._cursor.fetchall()
            self.log.debug("read updates from file")

            # apply updates
            for update, *rest in updates:
                self.ydoc.apply_update(update)
            self.log.debug("applied updates to YDoc")

    async def before(self):
        """
        Hook executed before the component sets its [`started`][elva.component.Component.started] signal.

        The ELVA SQLite database is being initialized and read.
        Also, the component subscribes to changes in [`ydoc`][elva.store.SQLiteStore.ydoc].
        """
        # init tables and table content
        await self._initialize_database()

        # read data from file if present
        await self._read()

        # start watching for updates on the YDoc
        self._subscription = self.ydoc.observe(self._on_transaction_event)

        # start listening on the update stream
        await self._task_group.start(self._listen)

    async def cleanup(self):
        """
        Hook cancelling subscription to changes and closing the database.
        """
        # unsubscribe from YDoc updates, otherwise transactions will fail
        self.ydoc.unobserve(self._subscription)
        del self._subscription

        # send signal to stop listening on the update stream and
        # closing the database connection
        await self._stream_send.send(None)
