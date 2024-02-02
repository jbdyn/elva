from pycrdt import Doc, Text, Array, Map
from pycrdt.text import TextEvent
from pycrdt.array import ArrayEvent
from pycrdt.map import MapEvent

from elva.parser import TextEventParser, ArrayEventParser, MapEventParser, AnyEventParser

def init_text():
    class Holder():
        pass

    doc = Doc()
    text = Text()
    doc["text"] = text

    holder = Holder()

    def text_callback(event):
        holder.event = event

    text.observe(text_callback)

    return doc, text, holder


def test_runner():
    class MyTextEventParser(TextEventParser):
        def check_saved_events(self):
            assert self.outer_event == self.event

        def on_retain(self, *args):
            self.check_saved_events()

        def on_insert(self, *args):
            self.check_saved_events()

        def on_delete(self, *args):
            self.check_saved_events()

    doc, text, holder = init_text()

    text += "test1"
    event1 = holder.event
    text += "test2"
    event2 = holder.event


    my_text_event_parser = MyTextEventParser()
    my_text_event_parser.outer_event = event1
    my_text_event_parser.parse(event1)

def test_text_event_parser():
    doc, text, holder = init_text()
    text_event_parser = TextEventParser()

    text += "test"
    event = holder.event

    target, actions, path = text_event_parser.parse(event)
    assert target == event.target
    assert actions == [
        ('insert', "test")
    ]
    assert path == event.path
