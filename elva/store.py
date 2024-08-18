import sqlite_anyio as sqlite
from anyio import Event, Lock, Path, create_memory_object_stream

from elva.component import Component


class SQLiteStore(Component):
    def __init__(self, ydoc, path):
        self.ydoc = ydoc
        self.path = Path(path)
        self.db_path = self.path.with_suffix(".y")
        self.initialized = None
        self.lock = Lock()

    def callback(self, event):
        self._task_group.start_soon(self.write, event.update)

    async def _provide_table(self):
        async with self.lock:
            self.log.debug("providing table")
            await self.cursor.execute(
                "CREATE TABLE IF NOT EXISTS yupdates(yupdate BLOB)"
            )
            await self.db.commit()
            self.log.debug("provided table")

    async def _init_db(self):
        self.log.debug("initializing database")
        self.initialized = Event()
        self.db = await sqlite.connect(self.db_path)
        self.cursor = await self.db.cursor()
        self.log.debug(f"connected to database {self.path}")
        await self._provide_table()
        self.log.info("database initialized")
        self.initialized.set()

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

    async def wait_running(self):
        if self.started is None:
            raise RuntimeError("{self} not started")
        await self.initialized.wait()

    async def read(self):
        await self.wait_running()

        async with self.lock:
            await self.cursor.execute("SELECT yupdate FROM yupdates")
            for update, *rest in await self.cursor.fetchall():
                self.ydoc.apply_update(update)

    async def _write(self, data):
        await self.wait_running()

        async with self.lock:
            self.log.debug(f"writing {data}")
            await self.cursor.execute(
                "INSERT INTO yupdates VALUES (?)",
                [data],
            )
            await self.db.commit()

    async def write(self, data):
        await self.stream_send.send(data)
        # self.stream_send.send_nowait(data)
