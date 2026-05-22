"""
Module holding store components.
"""

from pathlib import Path
from sqlite3 import Connection

from anyio import (
    CancelScope,
    WouldBlock,
    create_memory_object_stream,
)
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from pycrdt import Doc, Subscription, TransactionEvent

from elva.component import Component, create_component_state
from elva.files import Data
from elva.protocol import EMPTY_UPDATE

SQLiteStoreState = create_component_state("SQLiteStoreState")
"""The states of the [`SQLiteStore`][elva.store.SQLiteStore] component."""


class SQLiteStore(Data, Component):
    """
    Store component saving Y updates in an ELVA SQLite database.
    """

    ydoc: Doc
    """
    Instance of the synchronized Y-document.
    """

    path: Path
    """
    The path to the SQLite database.
    """

    db: Connection
    """
    The SQLite database connection instance.
    """

    _subscription: Subscription
    """
    (while running)
    Object holding subscription information to changes
    in [`ydoc`][elva.store.SQLiteStore.ydoc].
    """

    _send: MemoryObjectSendStream
    """
    (while running)
    Stream to send Y Document updates or flow control objects to.
    """

    _receive: MemoryObjectReceiveStream
    """
    (while running)
    Stream to receive Y Document updates or flow control objects from.
    """

    def __init__(
        self,
        ydoc: Doc,
        path: str | Path,
        fail: bool = False,
    ) -> None:
        """
        Arguments:
            ydoc: instance of the synchronized Y Document.
            path: path to the SQLite database.
            fail: raise an error when the path does not exist.
        """
        self.ydoc = ydoc

        super().__init__(path, fail)

    @property
    def states(self) -> SQLiteStoreState:
        """
        The states this component can have.
        """
        return SQLiteStoreState

    @property
    def buffered(self) -> bool:
        """
        Check if there are buffered updates.

        Raises:
            RuntimeError: when the component is not running.

        Returns:
            `True` when there are buffered updates, else `False`.
        """
        if hasattr(self, "_receive"):
            return self._receive.statistics().current_buffer_used > 0
        else:
            raise RuntimeError("store is not running")

    def _on_transaction_event(self, event: TransactionEvent) -> None:
        """
        Hook called on changes in [`ydoc`][elva.store.SQLiteStore.ydoc].

        When called, the `event` data are written to the ELVA SQLite database.

        Arguments:
            event: object holding event information of changes in [`ydoc`][elva.store.SQLiteStore.ydoc].
        """
        self.log.debug("received transaction event")
        self._send.send_nowait(event.update)

    def _write(self, update: bytes) -> None:
        """
        Hook writing `update` to the `yupdates` ELVA SQLite database table.

        Arguments:
            update: the update to write to the ELVA SQLite database file.
        """
        self._execute("INSERT INTO yupdates VALUES (?)", [update])
        self._commit()

        self.log.debug(f"wrote update to file {self.path}")

    def _merge(self) -> None:
        """
        Hook to read in and apply updates from the ELVA SQLite database and
        write divergent history updates to file.
        """
        # get updates stored in file
        updates = self.get_updates()

        # the given ydoc might not be empty;
        # we append the resulting update to file as otherwise
        # histories would not be restored correctly and callbacks not triggered,
        # even when sequential updates from this history branch are applied
        temp = Doc()

        for update in updates:
            temp.apply_update(update)

        # get divergent update before we apply updates from file to `self.ydoc`
        divergent_update = self.ydoc.get_update(state=temp.get_state())

        # cleanup unused resources
        del temp

        # apply updates
        for update in updates:
            self.ydoc.apply_update(update)

        if updates:
            self.log.debug("applied updates from file")

        # append a non-empty update to a divergent history branch to file as well
        if divergent_update != EMPTY_UPDATE:
            # shield the write so content won't get lost
            with CancelScope(shield=True):
                self._write(divergent_update)

            self.log.debug("appended divergent history update to file")

    async def before(self):
        """
        Hook executed before the component sets its `RUNNING` state.

        The ELVA SQLite database is being initialized and read.
        Also, the component subscribes to changes in [`ydoc`][elva.store.SQLiteStore.ydoc].
        """
        # merge updates from file with the contents from the given YDoc
        self._merge()

        # initialize streams
        self._send, self._receive = create_memory_object_stream(max_buffer_size=65536)
        self.log.debug("instantiated buffer")

        # start watching for updates on the YDoc
        self._subscription = self.ydoc.observe(self._on_transaction_event)
        self.log.debug("subscribed to YDoc updates")

    async def run(self):
        """
        Hook writing updates from the internal buffer to file.
        """
        self.log.debug("listening for updates")

        async for update in self._receive:
            self.log.debug(f"received update {update}")

            with CancelScope(shield=True):
                # writing needs to be shielded from cancellation,
                # but is required to return quickly
                self._write(update)

    async def cleanup(self):
        """
        Hook cancelling subscription to changes and closing the database.
        """
        if hasattr(self, "_subscription"):
            # unsubscribe from YDoc updates, otherwise transactions will fail
            self.ydoc.unobserve(self._subscription)
            del self._subscription
            self.log.debug("unsubscribed from YDoc updates")

        if hasattr(self, "_receive"):
            # drain the buffer and write the remaining updates to file
            while True:
                try:
                    update = self._receive.receive_nowait()
                    self._write(update)
                except WouldBlock:
                    break

            self.log.debug("drained buffer")

            # remove buffer
            del self._send, self._receive
            self.log.debug("deleted buffer")
