import time
from typing import Union
import pytest

import anyio
from pycrdt import Doc, Text, Array, Map, TextEvent, ArrayEvent, MapEvent

from elva.parser import (
    EventParser,
    TextEventParser,
    ArrayEventParser,
    MapEventParser,
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


async def test_text_event_parser(anyio_backend):
    doc, text, holder = init(Text())
    holder.actions = list()

    class Test(TextEventParser):
        async def on_retain(self, retain):
            holder.actions.append(("retain", retain))

        async def on_insert(self, retain, value):
            holder.actions.append(("insert", retain, value))

        async def on_delete(self, retain, length):
            holder.actions.append(("delete", retain, length))

    text_event_parser = Test()
    anyio.run(text_event_parser.start)


    # insert
    text += "test"
    assert str(text) == "test"
    event = holder.event
    assert type(event) == TextEvent

    await text_event_parser.parse(event)
    assert holder.actions == [
        ("insert", "test")
    ]


    holder.actions.clear()


    # retain and insert, order matters
    text += "test"
    assert str(text) == "testtest"
    event = holder.event
    assert type(event) == TextEvent

    await text_event_parser.parse(event)
    assert holder.actions == [
        ("retain", 4),
        ("insert", "test")
    ]


    holder.actions.clear()


    # retain and delete, order matters
    del text[2:]
    assert str(text) == "te"
    event = holder.event
    assert type(event) == TextEvent

    await text_event_parser.parse(event)
    assert holder.actions == [
        ("retain", 2),
        ("delete", 6)
    ]


async def test_array_event_parser(anyio_backend):
    doc, array, holder = init(Array())
    holder.actions = list()
 
    class Test(ArrayEventParser):
        async def on_retain(self, retain):
            holder.actions.append(("retain", retain))

        async def on_insert(self, retain, values):
            holder.actions.append(("insert", retain, values))

        async def on_delete(self, retain, length):
            holder.actions.append(("delete", retain, length))

    array_event_parser = Test()
    anyio.run(array_event_parser.start)

   # extend
    array.extend([1, 2, 3])
    assert array.to_py() == [1.0, 2.0, 3.0]
    event = holder.event
    assert type(event) == ArrayEvent

    await array_event_parser.parse(event)
    assert holder.actions == [
        ("insert", [1.0, 2.0, 3.0])
    ]


    holder.actions.clear()


    # retain and insert, order matters
    array.insert(2, 10)
    assert array.to_py() == [1.0, 2.0, 10.0, 3.0]
    event = holder.event
    assert type(event) == ArrayEvent

    await array_event_parser.parse(event)
    assert holder.actions == [
        ("retain", 2),
        ("insert", [10.0])
    ]


    holder.actions.clear()


    # retain and delete, order matters
    array.pop(1)
    assert array.to_py() == [1.0, 10.0, 3.0]
    event = holder.event
    assert type(event) == ArrayEvent

    await array_event_parser.parse(event)
    assert holder.actions == [
        ("retain", 1),
        ("delete", 1)
    ]


async def test_map_event_parser(anyio_backend):
    doc, map, holder = init(Map())
    holder.actions = set()
 
    class Test(MapEventParser):
        async def on_add(self, key, new_value):
            holder.actions.append(("add", key, new_value))

        async def on_delete(self, key, old_value):
            holder.actions.append(("delete", key, old_value))

    map_event_parser = Test()
    anyio.run(map_event_parser.start)


    # add
    # order does not matter
    map.update({"foo": "bar", "baz": "faz"})
    assert map.to_py() == {"foo": "bar", "baz": "faz"}
    event = holder.event
    assert type(event) == MapEvent

    await map_event_parser.parse(event)
    assert holder.actions == set([
        ("add", "foo", "bar"),
        ("add", "baz", "faz")
    ])


    holder.actions.clear()


    # delete
    # order does not matter
    map.pop("foo")
    assert map.to_py() == {"baz": "faz"}
    event = holder.event
    assert type(event) == MapEvent

    await map_event_parser.parse(event)
    assert holder.actions == set([
        ("delete", "foo", "bar")
    ])
