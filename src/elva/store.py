import sqlite3
import uuid

import sqlite_anyio as sqlite
from anyio import Event, Lock, Path, create_memory_object_stream

from elva.component import Component

# TODO: check performance


class SQLiteStore(Component):
    def __init__(self, ydoc, identifier, path):
        self.ydoc = ydoc
        self.identifier = identifier
        self.path = Path(path)
        self.initialized = None
        self.lock = Lock()

    @staticmethod
    def get_metadata(path):
        db = sqlite3.connect(path)
        cur = db.cursor()
        try:
            res = cur.execute("SELECT * FROM metadata")
        except Exception:
            return dict()
        else:
            return dict(res.fetchall())
        finally:
            db.close()

    @staticmethod
    def set_metadata(path, metadata):
        db = sqlite3.connect(path)
        cur = db.cursor()
        try:
            cur.execute(
                "INSERT INTO metadata VALUES (?, ?)",
                list(metadata.values()),
            )
            db.commit()
        except Exception:
            raise
        finally:
            db.close()

    def callback(self, event):
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
        await self._init_db()
        await self.read()
        self.ydoc.observe(self.callback)

    async def run(self):
        self.stream_send, self.stream_recv = create_memory_object_stream(
            max_buffer_size=65543
        )
        async with self.stream_send, self.stream_recv:
            async for data in self.stream_recv:
                await self._write(data)

    async def cleanup(self):
        if self.initialized.is_set():
            await self.db.close()
            self.log.debug("closed database")

    async def wait_running(self):
        if self.started is None:
            raise RuntimeError("{self} not started")
        await self.initialized.wait()

    async def read(self):
        await self.wait_running()

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
        await self.wait_running()

        async with self.lock:
            await self.cursor.execute(
                "INSERT INTO yupdates VALUES (?)",
                [data],
            )
            await self.db.commit()
            self.log.debug(f"wrote {data} to file {self.path}")

    async def write(self, data):
        await self.stream_send.send(data)
        # self.stream_send.send_nowait(data)
