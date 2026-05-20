import uuid

import anyio
from pycrdt import Doc, Text, TransactionEvent
from pytest import fixture, mark

from elva.component import create_component_state
from elva.config import Config
from elva.protocol import STATE_ZERO
from elva.store import Data, Metadata, SQLiteStore

pytestmark = mark.anyio
parametrize = mark.parametrize


@fixture
def tmp_data_file(tmp_path):
    identifier = str(uuid.uuid4())
    return tmp_path / f"{identifier}.y"


@parametrize(
    "metadata",
    (
        {},
        {"foo": "bar"},
        {"baz": 42},
    ),
)
async def test_metadata(tmp_data_file, metadata):
    metadata = Config(metadata)

    # module functions for metadata retrieval without a running SQLiteStore component
    with Metadata(tmp_data_file) as m:
        m.set_config(metadata)
        metadata_read = m.get_config()
        assert metadata_read == metadata

    # read via a Y-store
    ydoc = Doc()
    identifier = None

    async with SQLiteStore(ydoc, identifier, tmp_data_file) as store:
        # the metadata we wrote previously to the database can be also retrieved from the component
        assert store.get_config() == metadata

        # the default API is equivalent to updating a dict
        metadata["quux"] = 3.14
        store.set_config(metadata)
        assert store.get_config() == metadata

        # still just updating existing or inserting new metadata without deletion
        metadata = Config({"a": "b"})
        store.set_config(metadata)
        assert store.get_config() != metadata

        # trimming database metadata to the passed keys
        store.set_config(metadata, replace=True)
        assert store.get_config() == metadata

    # reset exactly to the initial metadata
    with Metadata(tmp_data_file) as m:
        m.set_config(metadata_read, replace=True)
        assert m.get_config() == metadata_read


async def test_read_write(tmp_data_file):
    identifier = "identifier"

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

    # update capturing
    update = None

    def on_transaction_event(event: TransactionEvent):
        nonlocal update
        update = event.update

    doc_before.observe(on_transaction_event)

    # store initialization and CRDT manipulation
    store = SlowSQLiteStore(doc_before, identifier, tmp_data_file)

    # cancel *while* handling an incoming update
    async with anyio.create_task_group() as tg:
        await tg.start(store.start)
        text += "my-update"

        # waiting for `update` to be recognized
        while update is None:
            await anyio.sleep(1e-6)

        # the update is now in the store's buffer
        assert store.buffered

        # cancel the task scope, triggering the cleanup
        tg.cancel_scope.cancel()

        # the update is still in the buffer, but should be written to file nonetheless
        assert store.buffered

    # check if update has really been written to `tmp_data_file`
    with Data(tmp_data_file) as d:
        updates = d.get_updates()

    # there is only a singe update in the ELVA database, i.e. it has not been lost
    assert len(updates) == 1

    # the update is the one we were looking for
    assert update in updates[0]

    # instantiate a new store object
    doc_after = Doc()

    async with SQLiteStore(doc_after, identifier, tmp_data_file) as store:
        # the new doc state is equivalent to the previous one, i.e.
        # all Y Document content is properly restored
        assert doc_after.get_state() == doc_before.get_state()


async def test_non_empty_ydoc(tmp_data_file):
    """The updates of non-empty YDocs should be written to file, too."""
    identifier = "identifier"

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
    async with SQLiteStore(doc_1, identifier, tmp_data_file):
        content_1_added = "addition while store is running"
        ytext += content_1_added
        assert str(ytext) == content_1_before + content_1_added

    # get the list of updates from saved file
    with Data(tmp_data_file) as d:
        updates = d.get_updates()

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
    async with SQLiteStore(doc_2, identifier, tmp_data_file):
        assert content_1_before + content_1_added in str(ytext)
        assert content_2_before in str(ytext)

    # get the list of updates from saved file
    with Data(tmp_data_file) as d:
        updates = d.get_updates()

    # we see the updates from the first and the second run
    assert len(updates) == 3
