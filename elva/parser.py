import anyio
from logging import getLogger

from pycrdt._base import BaseEvent
from pycrdt import TextEvent, ArrayEvent, MapEvent

from elva.base import Component

log = getLogger(__name__)

class EventParser(Component):
    event_type = BaseEvent

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
    event_type = TextEvent

    async def _parse_event(self, event):
        deltas = event.delta

        range_offset = 0
        for delta in deltas:
            for action, var in delta.items():
                if action == 'retain':
                    range_offset = var
                    await self.on_retain(range_offset)
                elif action == 'insert':
                    insert_value = var
                    await self.on_insert(range_offset, insert_value)
                elif action == 'delete':
                    range_length = var
                    await self.on_delete(range_offset, range_length)

    async def on_retain(self, range_offset):
        ...

    async def on_insert(self, range_offset, insert_value):
        ...

    async def on_delete(self, range_offset, range_length):
        ...


class ArrayEventParser(EventParser):
    event_type = ArrayEvent

    async def _parse_event(self, event):
        deltas = event.delta

        range_offset = 0
        for delta in deltas:
            for action, var in delta.items():
                if action == 'retain':
                    range_offset = var
                    await self.on_retain(range_offset)
                elif action == 'insert':
                    insert_value = var
                    await self.on_insert(range_offset, insert_value)
                elif action == 'delete':
                    range_length = var
                    await self.on_delete(range_offset, range_length)

    async def on_retain(self, range_offset):
        ...

    async def on_insert(self, range_offset, insert_value):
        ...

    async def on_delete(self, range_offset, range_length):
        ...


class MapEventParser(EventParser):
    event_type = MapEvent

    async def _parse_event(self, event):
        keys = event.keys

        for key, delta in keys.items():
            action = delta["action"]
            if action == 'add':
                new_value = delta["newValue"]
                await self.on_add(key, new_value)
            elif action == 'delete':
                old_value = delta["oldValue"]
                await self.on_delete(key, old_value)

    async def on_add(self, key, new_value):
        ...

    async def on_delete(self, key, old_value):
        ...

