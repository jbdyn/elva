"""
Module holding store components.
"""

import sqlite3
import uuid

import sqlite_anyio as sqlite
from anyio import Event, Lock, Path, create_memory_object_stream
from pycrdt import Doc, Subscription, TransactionEvent

from elva.component import Component

# TODO: check performance


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

    lock: Lock
    """Object for restricted resource management."""

    subscription: Subscription
    """Object holding subscription information to changes in [`ydoc`][elva.store.SQLiteStore.ydoc]."""

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
        self.initialized = None
        self.lock = Lock()

    @staticmethod
    def get_metadata(path: str) -> dict:
        """
        Retrieve metadata from a given ELVA SQLite database.

        Arguments:
            path: path to the ELVA SQLite database.

        Returns:
            mapping of metadata keys to values.
        """
        db = sqlite3.connect(path)
        cur = db.cursor()
        try:
            res = cur.execute("SELECT * FROM metadata")
        except Exception:
            res = dict()
        else:
            res = dict(res.fetchall())
        finally:
            db.close()

        return res

    @staticmethod
    def set_metadata(path: str, metadata: dict[str, str]):
        """
        Set given metadata in a given ELVA SQLite database.

        Arguments:
            path: path to the ELVA SQLite database.
            metadata: mapping of metadata keys to values.
        """
        db = sqlite3.connect(path)
        cur = db.cursor()
        try:
            try:
                cur.executemany(
                    "INSERT INTO metadata VALUES (?, ?)",
                    list(metadata.items()),
                )
            except Exception:  # IntegrityError, UNIQUE constraint failed
                cur.executemany(
                    "UPDATE metadata SET value = ? WHERE key = ?",
                    list(zip(metadata.values(), metadata.keys())),
                )
            db.commit()
        except Exception:
            db.close()
            raise
        else:
            db.close()

    def callback(self, event: TransactionEvent):
        """
        Hook called on changes in [`ydoc`][elva.store.SQLiteStore.ydoc].

        When called, the `event` data are written to the ELVA SQLite database.

        Arguments:
            event: object holding event information of changes in [`ydoc`][elva.store.SQLiteStore.ydoc].
        """
        self._task_group.start_soon(self.write, event.update)

    async def _provide_update_table(self):
        async with self.lock:
            await self.cursor.execute(
                "CREATE TABLE IF NOT EXISTS yupdates(yupdate BLOB)"
            )
            await self.db.commit()
            self.log.debug("ensured update table")

    async def _provide_metadata_table(self):
        async with self.lock:
            await self.cursor.execute(
                "CREATE TABLE IF NOT EXISTS metadata(key PRIMARY KEY, value)"
            )
            await self.db.commit()
            self.log.debug("ensured metadata table")

    async def _ensure_identifier(self):
        async with self.lock:
            try:
                # insert given or generated identifier
                if self.identifier is None:
                    self.identifier = str(uuid.uuid4())
                await self.cursor.execute(
                    "INSERT INTO metadata VALUES (?, ?)",
                    ["identifier", self.identifier],
                )
            except Exception as exc:
                self.log.error(exc)
                # update existing identifier
                if self.identifier is not None:
                    await self.cursor.execute(
                        "UPDATE metadata SET value = ? WHERE key = ?",
                        [self.identifier, "identifier"],
                    )
            finally:
                await self.db.commit()

    async def _init_db(self):
        self.log.debug("initializing database")
        self.initialized = Event()
        self.db = await sqlite.connect(self.path)
        self.cursor = await self.db.cursor()
        self.log.debug(f"connected to database {self.path}")
        await self._provide_metadata_table()
        await self._ensure_identifier()
        await self._provide_update_table()
        self.initialized.set()
        self.log.info("database initialized")

    async def before(self):
        """
        Hook executed before the component sets its [`started`][elva.component.Component.started] signal.

        The ELVA SQLite database is being initialized and read.
        Also, the component subscribes to changes in [`ydoc`][elva.store.SQLiteStore.ydoc].
        """
        await self._init_db()
        await self.read()
        self.subscription = self.ydoc.observe(self.callback)

    async def run(self):
        """
        Hook writing data to the ELVA SQLite database.
        """
        self.stream_send, self.stream_recv = create_memory_object_stream(
            max_buffer_size=65543
        )
        async with self.stream_send, self.stream_recv:
            async for data in self.stream_recv:
                await self._write(data)

    async def cleanup(self):
        """
        Hook cancelling subscription to changes and closing the database.
        """
        self.ydoc.unobserve(self.subscription)
        if self.initialized.is_set():
            await self.db.close()
            self.log.debug("closed database")

    async def _wait_running(self):
        if self.started is None:
            raise RuntimeError("{self} not started")
        await self.initialized.wait()

    async def read(self):
        """
        Hook to read in metadata and updates from the ELVA SQLite database and apply them.
        """
        await self._wait_running()

        async with self.lock:
            await self.cursor.execute("SELECT * FROM metadata")
            self.metadata = dict(await self.cursor.fetchall())
            self.log.debug("read metadata from file")

            await self.cursor.execute("SELECT yupdate FROM yupdates")
            self.log.debug("read updates from file")
            for update, *rest in await self.cursor.fetchall():
                self.ydoc.apply_update(update)
            self.log.debug("applied updates to YDoc")

    async def _write(self, data):
        await self._wait_running()

        async with self.lock:
            await self.cursor.execute(
                "INSERT INTO yupdates VALUES (?)",
                [data],
            )
            await self.db.commit()
            self.log.debug(f"wrote {data} to file {self.path}")

    async def write(self, data: bytes):
        """
        Queue `update` to be written to the ELVA SQLite database.

        Arguments:
            data: update to queue for writing to disk.
        """
        await self.stream_send.send(data)
