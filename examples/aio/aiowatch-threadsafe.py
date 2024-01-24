import asyncio
from pathlib import Path
from typing import Optional
import time
import sys
import os

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from y_py import YDoc
import json

class YTreeHandler():
    def __init__(self, path, ydoc):
        tree = {}
        for e in os.walk(path):
            tree.update(self.tree_entry(e[0], True))
            for f in e[2]:
                tree.update(self.tree_entry(os.path.join(e[0], f), False))

        self.ydoc = ydoc
        self.tree = ydoc.get_map("tree")
        with ydoc.begin_transaction() as txn:
            self.tree.update(txn, tree)

        self.print_tree()

    def print_tree(self):
        print(json.dumps(
            json.loads(self.tree.to_json()),
            indent=4,
            sort_keys=True
        ))

    def print_event(self, event):
        ftype = "directory" if event.is_directory else "file"
        msg = f"> {ftype} '{event.src_path}' {event.event_type}!"
        print(msg)

    def tree_entry(self, path, is_directory, status="synced"):
        return {
            path: {
                "is_directory": is_directory,
                "status": status
            }
        }

    def tree_entry_from_event(self, event, **kwargs):
        return self.tree_entry(event.src_path, event.is_directory, **kwargs)

    def dispatch(self, event):
        self.print_event(event)

        method = {
            "created": self.on_created,
            "deleted": self.on_deleted,
            "modified": self.on_modified,
            "moved": self.on_moved,
            "opened": self.on_opened,
            "closed": self.on_closed,
        }[event.event_type]

        with self.ydoc.begin_transaction() as txn:
            method(event, txn)

        self.print_tree()

    def on_created(self, event, txn):
        self.tree.update(
            txn,
            self.tree_entry_from_event(event)
        )

    def on_deleted(self, event, txn):
        self.tree.pop(
            txn, event.src_path, None
        )

    def on_opened(self, event, txn):
        self.tree.update(
            txn,
            self.tree_entry_from_event(
                event, status="open"
            )
        )

    def on_closed(self, event, txn):
        self.tree.update(
            txn,
            self.tree_entry_from_event(event)
        )

    def on_modified(self, event, txn):
        self.tree.update(
            txn,
            self.tree_entry_from_event(
                event, status="modified"
            )
        )

    def on_moved(self, event, txn):
        self.tree.pop(
            txn, event.src_path, None
        )
        self.tree.update(
            txn,
            self.tree_entry(
                event.dest_path, event.is_directory
            )
        )


class _EventHandler(FileSystemEventHandler):
    def __init__(self, queue: asyncio.Queue, loop: asyncio.BaseEventLoop,
                 *args, **kwargs):
        self._loop = loop
        self._queue = queue
        super(*args, **kwargs)

    def on_any_event(self, event: FileSystemEvent) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)


class EventIterator(object):
    def __init__(self, queue: asyncio.Queue,
                 loop: Optional[asyncio.BaseEventLoop] = None):
        self.queue = queue

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.queue.get()

        if item is None:
            raise StopAsyncIteration

        return item


def watch(path: Path, queue: asyncio.Queue, loop: asyncio.BaseEventLoop,
          recursive: bool = False) -> None:
    """Watch a directory for changes."""
    handler = _EventHandler(queue, loop)

    observer = Observer()
    observer.schedule(handler, str(path), recursive=recursive)
    observer.start()
    print("Observer started")
    try:
        while True:
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()
    loop.call_soon_threadsafe(queue.put_nowait, None)


async def consume(queue: asyncio.Queue, event_handler) -> None:
    async for event in EventIterator(queue):
        event_handler.dispatch(event)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    queue = asyncio.Queue()

    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    ydoc = YDoc()
    event_handler = YTreeHandler(path, ydoc)

    futures = [
        loop.run_in_executor(None, watch, Path(path), queue, loop, True),
        consume(queue, event_handler),
    ]

    loop.run_until_complete(asyncio.gather(*futures))
