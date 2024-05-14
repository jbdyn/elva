import time

from anyio import get_cancelled_exc_class, Event
import sqlite_anyio as sqlite
import logging

import elva.logging_config
from elva.base import Component

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


class SQLiteStore(Component):
    def __init__(self, ydoc, path):
        self.ydoc = ydoc
        self.path = path
        self.initialized = None
        self._table_name = "yupdates"

    def callback(self, event):
        self._task_group.start_soon(self.write, event.update)

    async def _provide_table(self):
        log.debug("providing table")
        await self.cursor.execute(
            "CREATE TABLE IF NOT EXISTS yupdates(yupdate BLOB)"
        )
        await self.db.commit()
        log.debug("provided table")
        
    async def _init_db(self):
        log.debug("initializing database")
        self.initialized = Event()
        self.db = await sqlite.connect(self.path)
        self.initialized.set()
        log.debug(f"connected to database {self.path}")
        self.cursor = await self.db.cursor()
        await self._provide_table()
        log.info("database initialized")

    async def run(self):
        await self._init_db()
        await self.read()
        self.ydoc.observe(self.callback)

    async def cleanup(self):
        if self.initialized.is_set():
            await self.db.close()

    async def running(self):
        if self.started is None:
            raise RuntimeError("{self} not started")
        await self.initialized.wait()

    async def read(self):
        await self.running()

        await self.cursor.execute(
            "SELECT yupdate FROM yupdates"
        )
        for update, *rest in await self.cursor.fetchall():
            self.ydoc.apply_update(update)

    async def write(self, data):
        await self.running()

        log.debug(f"writing {data}")
        await self.cursor.execute(
            "INSERT INTO yupdates VALUES (?)", [data],
        )
        await self.db.commit()
