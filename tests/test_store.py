import uuid

import anyio
import pytest
from pycrdt import Doc, Text, TransactionEvent

from elva.component import create_component_state
from elva.protocol import STATE_ZERO
from elva.store import SQLiteStore, get_metadata, get_updates, set_metadata

pytestmark = pytest.mark.anyio


@pytest.fixture
def tmp_elva_file(tmp_path):
    identifier = str(uuid.uuid4())
    return tmp_path / f"{identifier}.y"


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
    updates = get_updates(tmp_elva_file)

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


async def test_non_empty_ydoc(tmp_elva_file):
    """The updates of non-empty YDocs should be written to file, too."""
    # setup
    identifier = "non-empty-ydoc"

    #
    # first run with empty file
    #

    # we have an empty YDoc
    doc_1 = Doc()
    assert doc_1.get_state() == STATE_ZERO

    # now we add some content, the store is not running yet
    content_1_before = "something already in here"
    doc_1["text"] = ytext = Text(content_1_before)
    assert doc_1.get_state() != STATE_ZERO

    # run the store, writing the updates to file
    async with SQLiteStore(doc_1, identifier, tmp_elva_file):
        content_1_added = "addition while store is running"
        ytext += content_1_added
        assert str(ytext) == content_1_before + content_1_added

    # get the list of updates from saved file
    updates = get_updates(tmp_elva_file)

    # we see two updates: the one before the store was started
    # and the one made during it was active
    assert len(updates) == 2

    #
    # second run with already present updates in file
    #

    # again, we have an empty YDoc
    doc_2 = Doc()
    assert doc_2.get_state() == STATE_ZERO

    # we apply some changes again before the store is started
    content_2_before = "again we did things before"
    doc_2["text"] = ytext = Text(content_2_before)
    assert doc_2.get_state() != STATE_ZERO

    # start the store, which restores all content
    async with SQLiteStore(doc_2, identifier, tmp_elva_file):
        assert content_1_before + content_1_added in str(ytext)
        assert content_2_before in str(ytext)

    # get the list of updates from saved file
    updates = get_updates(tmp_elva_file)

    # we see the updates from the first and the second run
    assert len(updates) == 3
