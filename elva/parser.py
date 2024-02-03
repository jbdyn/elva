import abc

from pycrdt.base import BaseEvent
from pycrdt.text import TextEvent
from pycrdt.array import ArrayEvent
from pycrdt.map import MapEvent


class EventParser(abc.ABC):
    def __init__(self, event_type):
        self.event_type = event_type

    def check_event(self, event):
        if not isinstance(event, self.event_type):
            raise TypeError(f"The event '{event}' is of type {type(event)}, but needs to be {self.event_type}")

    def parse(self, event):
        self.check_event(event)
        runner = self.__class__()
        runner.event = event
        return runner.parse_event(event)

    @abc.abstractmethod
    def parse_event(self, event):
        ...


class TextEventParser(EventParser):
    def __init__(self):
        super().__init__(TextEvent)

    def parse_event(self, event):
        target = event.target
        deltas = event.delta
        path = event.path

        actions = []
        for delta in deltas:
            range_offset = 0
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

        return target, actions, path

    def on_retain(self, range_offset):
        ...

    def on_insert(self, range_offset, insert_value):
        ...

    def on_delete(self, range_offset, range_length):
        ...


class ArrayEventParser(EventParser):
    def __init__(self):
        super().__init__(ArrayEvent)

    def parse_event(self, event):
        target = event.target
        deltas = event.deltas
        path = event.path

        actions = []
        for delta in deltas:
            range_offset = 0
            for action, var in delta.items():
                actions.append((action, var))
                if action == 'retain':
                    range_offset = var
                    self.on_retain(range_offset)
                elif action == 'insert':
                    insert_values = var
                    self.on_insert(range_offset, insert_values)
                elif action == 'delete':
                    range_length = var
                    self.on_delete(range_offset, range_length)

        return target, actions, path

    def on_retain(self, range_offset):
        ...

    def on_insert(self, range_offset, insert_values):
        ...

    def on_delete(self, range_offset, range_length):
        ...


class MapEventParser(EventParser):
    def __init__(self):
        super().__init__(MapEvent)

    def parse_event(self, event):
        target = event.target
        keys = event.keys
        path = event.path

        actions = []
        for key, delta in keys.items():
            action = delta["action"]
            if action == 'add':
                new_value = change["newValue"]
                actions.append((action, key, new_value))
                self.on_add(key, new_value)
            elif action == 'delete':
                old_value = change["oldValue"]
                actions.append((action, key, old_value))
                self.on_delete(key, old_value)

        return target, actions, path

    def on_add(self, key, new_value):
        ...

    def on_delete(self, key, old_value):
        ...

class AnyEventParser():
    def __init__(self, text_event_parser=None, array_event_parser=None, map_event_parser=None):
        self.text_event_parser = TextEventParser() if text_event_parser is None else text_event_parser
        self.array_event_parser = ArrayEventParser() if array_event_parser is None else array_event_parser
        self.map_event_parser = MapEventParser() if map_event_parser is None else map_event_parser

    def parse(self, event):
        if isinstance(event, TextEvent):
            return self.text_event_parser.parse(event)
        elif isinstance(event, ArrayEvent):
            return self.array_event_parser.parse(event)
        elif isinstance(event, MapEvent):
            return self.map_event_parser.parse(event)
        elif isinstance(event, BaseEvent):
            raise NotImplementedError(f"The event '{event}' seems to be of an unknown pycrdt data type event {type(event)}")
        else:
            raise TypeError(f"The event '{event}' is of type {type(event)}, but needs to base {BaseEvent}")
