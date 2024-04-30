import time
from typing import Union

import anyio
from pycrdt import Doc, Text, Array, Map, TextEvent, ArrayEvent, MapEvent

from elva.parser import (
    EventParser,
    TextEventParser,
    ArrayEventParser,
    MapEventParser,
    AnyEventParser,
)


class Holder:
    """An object to assign arbitrary attributes to."""

    pass


def init(data_type) -> tuple[Doc, Union[Text, Array, Map], Holder]:
    """
    Initializes a shared data type of kind 'kind' and integrates it into a YDocument.
    It returns the YDocument, the shared data type and an holder object holding the last event.
    """
    doc = Doc()
    doc["shared"] = data_type

    holder = Holder()

    def callback(event):
        holder.event = event

    data_type.observe(callback)

    return doc, data_type, holder


async def test_dynamic_self_instantiation(anyio_backend):
    doc, text, holder = init(Text())

    text += "test1"
    event1 = holder.event
    assert type(event1) == TextEvent

    text += "test2"
    event2 = holder.event
    assert type(event2) == TextEvent

    holder.start_timers = list()
    holder.finish_timers = list()
    holder.results = list()
    holder.start_event = anyio.Event()

    class DynamicTextEventParser(TextEventParser):
        def test_dynamic_self_instantiation(self):
            runner1 = type(self)()
            runner1.event = event1
            runner2 = type(self)()
            runner2.event = event2
            assert runner1 is not runner2
            assert (
                runner1.event is event1 and runner1.event is not event2
            )  # test for side effects

        def return_self_event(self):
            return self.event

        async def aparse(self, event):
            self.check_event(event)
            runner = type(self)()
            runner.event = event

            # simulate long running parsing
            holder.start_timers.append((runner, time.time()))

            # signal start of simulation
            holder.start_event.set()

            await anyio.sleep(0.2)
            holder.finish_timers.append((runner, time.time()))

            # save result
            holder.results.append((runner, runner.return_self_event()))

    event_parser = DynamicTextEventParser()
    event_parser.test_dynamic_self_instantiation()

    async with anyio.create_task_group() as tg:
        tg.start_soon(event_parser.aparse, event1)
        # wait for start of first simulation
        await holder.start_event.wait()
        await anyio.sleep(0.1)
        tg.start_soon(event_parser.aparse, event2)

    # confirm that artificial delay works
    start_timers = [item[1] for item in holder.start_timers]
    finish_timers = [item[1] for item in holder.finish_timers]
    assert start_timers[0] < start_timers[1] < finish_timers[0] < finish_timers[1]

    # confirm that we had two different runners
    # chronologically consistent with the timers above
    runners = [item[0] for item in holder.results]
    assert runners[0] is not runners[1]
    assert runners[0] is holder.start_timers[0][0]
    assert runners[1] is holder.start_timers[1][0]

    # confirm that there were no side effects during self.event assignment
    results = dict(holder.results)
    events = [results[runner] for runner in runners]
    assert events[0] is not events[1]
    assert events[0] is event1
    assert events[1] is event2


def test_text_event_parser():
    doc, text, holder = init(Text())
    text_event_parser = TextEventParser()

    # insert
    text += "test"
    assert str(text) == "test"
    event = holder.event
    assert type(event) == TextEvent

    actions = text_event_parser.parse(event)
    assert actions == [
        ("insert", "test")
    ]

    # retain and insert, order matters
    text += "test"
    assert str(text) == "testtest"
    event = holder.event
    assert type(event) == TextEvent

    actions = text_event_parser.parse(event)
    assert actions == [
        ("retain", 4),
        ("insert", "test")
    ]

    # retain and delete, order matters
    del text[2:]
    assert str(text) == "te"
    event = holder.event
    assert type(event) == TextEvent

    actions = text_event_parser.parse(event)
    assert actions == [
        ("retain", 2),
        ("delete", 6)
    ]


def test_array_event_parser():
    doc, array, holder = init(Array())
    array_event_parser = ArrayEventParser()

    # extend
    array.extend([1, 2, 3])
    assert array.to_py() == [1.0, 2.0, 3.0]
    event = holder.event
    assert type(event) == ArrayEvent

    actions = array_event_parser.parse(event)
    assert actions == [
        ("insert", [1.0, 2.0, 3.0])
    ]

    # retain and insert, order matters
    array.insert(2, 10)
    assert array.to_py() == [1.0, 2.0, 10.0, 3.0]
    event = holder.event
    assert type(event) == ArrayEvent

    actions = array_event_parser.parse(event)
    assert actions == [
        ("retain", 2),
        ("insert", [10.0])
    ]

    # retain and delete, order matters
    array.pop(1)
    assert array.to_py() == [1.0, 10.0, 3.0]
    event = holder.event
    assert type(event) == ArrayEvent

    actions = array_event_parser.parse(event)
    assert actions == [
        ("retain", 1),
        ("delete", 1)
    ]


def test_map_event_parser():
    doc, map, holder = init(Map())
    map_event_parser = MapEventParser()

    # add
    # order does not matter
    map.update({"foo": "bar", "baz": "faz"})
    assert map.to_py() == {"foo": "bar", "baz": "faz"}
    event = holder.event
    assert type(event) == MapEvent

    actions = map_event_parser.parse(event)
    assert set(actions) == set([
        ("add", "foo", "bar"),
        ("add", "baz", "faz")
    ])

    # delete
    # order does not matter
    map.pop("foo")
    assert map.to_py() == {"baz": "faz"}
    event = holder.event
    assert type(event) == MapEvent

    actions = map_event_parser.parse(event)
    assert set(actions) == set([
        ("delete", "foo", "bar")
    ])
