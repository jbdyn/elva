import anyio
import pytest
from pycrdt import Doc, is_awareness_disconnect_message

from elva.awareness import Awareness
from elva.protocol import YMessage

# use the anyio pytest plugin
pytestmark = pytest.mark.anyio


@pytest.fixture
def awareness() -> Awareness:
    ydoc = Doc()
    return Awareness(ydoc)


async def test_start_stop_methods(awareness):
    """Make sure the Awareness class behaves indeed like a component when used with start and stop methods."""
    async with anyio.create_task_group() as tg:
        await tg.start(awareness.start)
        assert awareness.states.ACTIVE in awareness.state
        assert awareness.states.RUNNING in awareness.state
        await awareness.stop()

    # wait for the component to stop
    sub = awareness.subscribe()
    while awareness.states.ACTIVE in awareness.state:
        await sub.receive()
    awareness.unsubscribe(sub)

    assert awareness.state == awareness.states.NONE


async def test_start_stop_context_manager(awareness):
    """Make sure the Awareness class behaves indeed like a component when used as async context manager."""
    async with awareness:
        assert awareness.states.ACTIVE in awareness.state
        assert awareness.states.RUNNING in awareness.state

    # wait for the component to stop
    sub = awareness.subscribe()
    while awareness.states.ACTIVE in awareness.state:
        await sub.receive()
    awareness.unsubscribe(sub)

    assert awareness.state == awareness.states.NONE


async def test_observation(awareness):
    """Test observations and the disconnect message on cleanup."""
    events = list()

    def callback(topic, data):
        actions, origin = data
        assert topic in ("update", "change")
        assert isinstance(data, tuple)
        assert isinstance(actions, dict)
        assert origin == "local"

        events.append((topic, actions, origin))

    # test whether this method works as expected
    obs = awareness.observe(callback)
    assert isinstance(obs, str)

    # we update our local state by increasing its clock manually
    awareness.set_local_state(awareness.get_local_state())

    # we see the update of our local state here
    assert len(events) == 1
    _, data, _ = events[0]
    assert data["updated"] == [awareness.client_id]

    # go through one lifecycle of the Awareness component;
    # thereby, we trigger the disconnect message on cleanup
    async with awareness:
        pass

    # we get callback on both the `change` and the `update` topic
    assert len(events) == 3

    _, actions1, _ = events[1]
    _, actions2, _ = events[2]

    # the data are indeed the same
    assert actions1 == actions2
    actions = actions1

    # we removed the state of our own client ID
    assert actions["removed"] == [awareness.client_id]

    # add all clients up
    client_ids = actions["added"] + actions["updated"] + actions["removed"]

    # encode the awareness update
    payload = awareness.encode_awareness_update(client_ids)
    message, _ = YMessage.AWARENESS.encode(payload)

    # check whether we encoded a disconnect message
    assert is_awareness_disconnect_message(message[1:])

    # test whether this method works as expected
    awareness.unobserve(obs)
    assert awareness._subscriptions == dict()


async def test_outdated_timeout():
    """The local state gets update automatically after a given timeout."""
    ydoc = Doc()
    awareness = Awareness(ydoc, outdated_timeout=100)

    events = list()

    def callback(topic, data):
        actions, origin = data

        # only log `update` events
        if topic == "update":
            events.append((topic, actions, origin))

    obs = awareness.observe(callback)

    # trigger the disconnect message
    async with awareness:
        while len(events) < 10:
            await anyio.sleep(1e-6)

    awareness.unobserve(obs)

    # with remove message
    assert len(events) == 11

    # all topics are `update`
    assert all(topic == "update" for topic, _, _ in events)

    # all event actions except for the last one are "updated" the local client ID
    assert all(
        not actions["added"]
        and actions["updated"] == [awareness.client_id]
        and not actions["removed"]
        for _, actions, _ in events[:-1]
    )

    # the last event's actions "removed" the local client ID
    _, last_actions, _ = events[-1]
    assert (
        not last_actions["added"]
        and not last_actions["updated"]
        and last_actions["removed"] == [awareness.client_id]
    )

    # all updates came from `local`
    assert all(origin == "local" for _, _, origin in events)
