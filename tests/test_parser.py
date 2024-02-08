import time

import anyio
from pycrdt import Doc, Text, Array, Map
from pycrdt.text import TextEvent
from pycrdt.array import ArrayEvent
from pycrdt.map import MapEvent

from elva.parser import EventParser, TextEventParser, ArrayEventParser, MapEventParser, AnyEventParser

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


async def test_dynamic_self_instantiation(anyio_backend):
    doc, text, holder = init_text()

    text += "test1"
    event1 = holder.event
    text += "test2"
    event2 = holder.event

    holder.start_timers = list()
    holder.finish_timers = list()
    holder.results = list()
    holder.start_event = anyio.Event()

    class DynamicTextEventParser(TextEventParser):
        def test_dynamic_self_instantiation(self):
            runner1 = self.__class__()
            runner1.event = event1
            runner2 = self.__class__()
            runner2.event = event2
            assert runner1 is not runner2
            assert runner1.event is event1 and runner1.event is not event2  # test for side effects

        def return_self_event(self):
            return self.event

        async def aparse(self, event):
            self.check_event(event)
            runner = self.__class__()
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
    doc, text, holder = init_text()
    text_event_parser = TextEventParser()

    text += "test"
    assert str(text) == "test"
    event = holder.event

    target, actions, path = text_event_parser.parse(event)
    assert actions == [
        ('insert', "test")
    ]

    text += "test"
    assert str(text) == "testtest"
    event = holder.event

    target, actions, path = text_event_parser.parse(event)
    assert actions == [
        ('retain', 4),
        ('insert', "test")
    ]

    del text[2:]
    assert str(text) == 'te'
    event = holder.event

    target, actions, path = text_event_parser.parse(event)
    assert actions == [
        ('retain', 2),
        ('delete', 6)
    ]
