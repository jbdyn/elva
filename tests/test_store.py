import sqlite3
import uuid

import anyio
import pytest
from pycrdt import Doc, Text, TransactionEvent

from elva.component import create_component_state
from elva.store import SQLiteStore, get_metadata, set_metadata

pytestmark = pytest.mark.anyio


@pytest.fixture
def tmp_elva_file(tmpdir):
    identifier = str(uuid.uuid4())
    return tmpdir / f"{identifier}.y"


@pytest.mark.parametrize(
    "metadata",
    (
        {},
        {"foo": "bar"},
        {"baz": 42},
    ),
)
async def test_metadata(tmp_elva_file, metadata):
    # module functions for metadata retrieval without a running SQLiteStore component
    set_metadata(tmp_elva_file, metadata)
    metadata_read = get_metadata(tmp_elva_file)
    assert metadata_read == metadata

    # running with a
    ydoc = Doc()
    identifier = None
    async with SQLiteStore(ydoc, identifier, tmp_elva_file) as store:
        # the metadata we wrote previously to the database can be also retrieved from the component
        assert await store.get_metadata() == metadata

        # the default API is equivalent to updating a dict
        metadata.update({"quux": 3.14})
        await store.set_metadata(metadata)
        assert await store.get_metadata() == metadata

        # still just updating existing or inserting new metadata without deletion
        metadata = {"a": "b"}
        await store.set_metadata(metadata)
        assert await store.get_metadata() != metadata

        # trimming database metadata to the passed keys
        await store.set_metadata(metadata, replace=True)
        assert await store.get_metadata() == metadata

    # reset exactly to the initial metadata
    set_metadata(tmp_elva_file, metadata_read, replace=True)
    assert get_metadata(tmp_elva_file) == metadata_read


async def test_metadata_with_identifier(tmp_elva_file):
    ydoc = Doc()
    identifier = "something-unique"
    async with SQLiteStore(ydoc, identifier, tmp_elva_file) as store:
        # the identifier is present as class attribute
        assert store.identifier == identifier

        # when specifying an identifier, it gets directly written to file
        metadata = await store.get_metadata()
        assert "identifier" in metadata
        assert metadata["identifier"] == identifier

        # the class attribute gets updated alongside with the metadata key in the file
        identifier = "something-new"
        new = {"identifier": identifier}
        await store.set_metadata(new)
        assert store.identifier == identifier


async def test_read_write(tmp_elva_file):
    SlowSQLiteStoreState = create_component_state("SlowSQLiteStoreState")

    class SlowSQLiteStore(SQLiteStore):
        @property
        def states(self) -> SlowSQLiteStoreState:
            return SlowSQLiteStoreState

        async def run(self):
            self.log.info("simulating slow run")
            await anyio.sleep(1)
            await super().run()

    # CRDT setup
    doc_before = Doc()
    doc_before["text"] = text = Text()
    identifier = "foo"

    # update capturing
    update = None

    def on_transaction_event(event: TransactionEvent):
        nonlocal update
        update = event.update

    doc_before.observe(on_transaction_event)

    # store initialization and CRDT manipulation
    store = SlowSQLiteStore(doc_before, identifier, tmp_elva_file)

    # cancel *while* handling an incoming update
    async with anyio.create_task_group() as tg:
        await tg.start(store.start)
        text += "my-update"

        # waiting for `update` to be recognized
        while update is None:
            await anyio.sleep(1e-6)

        # the update is now in the store's buffer
        assert store._stream_recv.statistics().current_buffer_used > 0

        # cancel the task scope, triggering the cleanup
        tg.cancel_scope.cancel()

        # the update is still in the buffer, but should be written to file nonetheless
        assert store._stream_recv.statistics().current_buffer_used > 0

    # check if update has really been written to `tmp_elva_file`
    db = sqlite3.connect(tmp_elva_file)
    cur = db.cursor()
    res = cur.execute("SELECT * FROM yupdates")
    updates = [yupdate for yupdate, *rest in res.fetchall()]

    # there is only a singe update in the ELVA database, i.e. it has not been lost
    assert len(updates) == 1

    # the update is the one we were looking for
    assert update in updates[0]

    # instantiate a new store object
    doc_after = Doc()

    async with SQLiteStore(doc_after, identifier, tmp_elva_file) as store:
        # the new doc state is equivalent to the previous one, i.e.
        # all Y Document content is properly restored
        assert doc_after.get_state() == doc_before.get_state()
