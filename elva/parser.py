import anyio
from logging import getLogger

from pycrdt._base import BaseEvent
from pycrdt import TextEvent, ArrayEvent, MapEvent

from elva.base import Component

log = getLogger(__name__)

class EventParser(Component):
    def __init__(self, event_type):
        self.event_type = event_type

    async def run(self):
        self.send_stream, self.receive_stream = anyio.create_memory_object_stream()
        async with self.send_stream, self.receive_stream:
            async for event in self.receive_stream:
                await self._parse_event(event)

    def check(self, event):
        if not isinstance(event, self.event_type):
            raise TypeError(f"The event '{event}' is of type {type(event)}, but needs to be {self.event_type}")

    async def parse(self, event):
        self.check(event)
        await self.send_stream.send(event)

    async def _parse_event(self, event):
        ...


class TextEventParser(EventParser):
    def __init__(self):
        super().__init__(TextEvent)

    async def _parse_event(self, event):
        deltas = event.delta

        actions = []
        range_offset = 0
        for delta in deltas:
            for action, var in delta.items():
                actions.append((action, var))
                if action == 'retain':
                    range_offset = var
                    await self.on_retain(range_offset)
                elif action == 'insert':
                    insert_value = var
                    await self.on_insert(range_offset, insert_value)
                elif action == 'delete':
                    range_length = var
                    await self.on_delete(range_offset, range_length)

        return actions

    async def on_retain(self, range_offset):
        ...

    async def on_insert(self, range_offset, insert_value):
        ...

    async def on_delete(self, range_offset, range_length):
        ...


class ArrayEventParser(EventParser):
    def __init__(self):
        super().__init__(ArrayEvent)

    def _parse_event(self):
        deltas = self.event.delta

        actions = []
        range_offset = 0
        for delta in deltas:
            for action, var in delta.items():
                actions.append((action, var))
                if action == 'retain':
                    range_offset = var
                    self.on_retain(range_offset)
                elif action == 'insert':
                    insert_value = var
                    self.on_insert(range_offset, insert_value)
                elif action == 'delete':
                    range_length = var
                    self.on_delete(range_offset, range_length)

        return actions

    def on_retain(self, range_offset):
        ...

    def on_insert(self, range_offset, insert_value):
        ...

    def on_delete(self, range_offset, range_length):
        ...


class MapEventParser(EventParser):
    def __init__(self):
        super().__init__(MapEvent)

    def _parse_event(self):
        keys = self.event.keys

        actions = []
        for key, delta in keys.items():
            action = delta["action"]
            if action == 'add':
                new_value = delta["newValue"]
                actions.append((action, key, new_value))
                self.on_add(key, new_value)
            elif action == 'delete':
                old_value = delta["oldValue"]
                actions.append((action, key, old_value))
                self.on_delete(key, old_value)

        return actions

    def on_add(self, key, new_value):
        ...

    def on_delete(self, key, old_value):
        ...

