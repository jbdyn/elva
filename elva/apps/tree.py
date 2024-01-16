import asyncio
import anyio
from pathlib import Path
from typing import Optional, Protocol
import logging
import time
import sys
import os

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from pycrdt import Doc, Map
from app import ElvaApp
from utils import print_tree, print_event
from pycrdt_websocket.ystore import FileYStore
from jupyter_ydoc import YBlob

# source: https://gist.github.com/mivade/f4cb26c282d421a62e8b9a341c7c65f6
class AsyncQueueEventHandler(FileSystemEventHandler):
    def __init__(self, queue: asyncio.Queue, loop: asyncio.BaseEventLoop, *args, **kwargs):
        self._loop = loop
        self._queue = queue
        super(*args, **kwargs)

    def on_any_event(self, event: FileSystemEvent) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)


class AsyncQueueIterator:
    def __init__(self, queue: asyncio.Queue, loop: Optional[asyncio.BaseEventLoop] = None):
        self.queue = queue

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.queue.get()

        if item is None:
            raise StopAsyncIteration

        return item


class ElvaTree(ElvaApp):
    def __init__(self, path=None, doc=None):
        super().__init__(doc)

        self.path = Path(path) if path is not None else Path('.')

        self.loop = asyncio.get_event_loop()
        self.doc_queue = asyncio.Queue()
        
        self.METHOD_EVENT_MAP = {
            "created": self.on_created,
            "deleted": self.on_deleted,
            "modified": self.on_modified,
            "moved": self.on_moved,
            "opened": self.on_opened,
            "closed": self.on_closed
        }

    def callback(self, event):
        print(event)

    async def read_tree(self):
        self.tree = Map()
        self.doc["tree"] = self.tree
        self.tree.observe(self.callback)
        for root, dirs, files in os.walk(self.path):
            for file in files:
                file_path = os.path.join(root, file)
                if file_path.endswith(".y"):
                    doc = Doc()
                    yfile = FileYStore(file_path)
                    await yfile.apply_updates(doc)
                    self.tree.update(self.tree_entry(file_path, doc))
                else:
                    if not os.path.exists(file_path + '.y'):
                        doc = Doc()
                        doc["source"] = Map()
                        with open(file_path, 'rb') as file_buffer:
                            doc["source"]["bytes"] = file_buffer.read()
                        self.tree.update(self.tree_entry(file_path, doc))
   
 
    async def start(self):
        async with anyio.create_task_group() as self.tg:
            self.tg.start_soon(self.read_tree)
            self.tg.start_soon(self._watch, self.path, self.doc_queue, self.loop)
            self.tg.start_soon(self._dispatch, self.doc_queue)

    def tree_entry(self, path, doc=None):
        return {path: doc}

    def dispatch(self, event):
        method = self.METHOD_EVENT_MAP[event.event_type]

        if not event.is_directory:
            method(event)

    def on_created(self, event):
        self.tree.update(self.tree_entry(event.src_path))

    def on_deleted(self, event):
        self.tree.pop(event.src_path)

    def on_opened(self, event):
        self.tree.update(self.tree_entry(event.src_path))

    def on_closed(self, event):
        self.tree.update(self.tree_entry(event.src_path))

    def on_modified(self, event):
        self.tree.update(self.tree_entry(event.src_path))

    def on_moved(self, event):
        self.tree.pop(event.src_path)
        self.tree.update(self.tree_entry(event.dest_path))

    async def _watch(self, path: Path, queue: asyncio.Queue, loop: asyncio.BaseEventLoop, recursive: bool = False) -> None:
        """Watch a directory for changes."""
        handler = AsyncQueueEventHandler(queue, loop)
    
        observer = Observer()
        observer.schedule(handler, str(path), recursive=recursive)
        observer.start()
        print("Observer started")
        try:
            await asyncio.Future()
        finally:
            observer.stop()
            observer.join()
        loop.call_soon_threadsafe(queue.put_nowait, None)

    async def _dispatch(self, queue: asyncio.Queue) -> None:
        async for event in AsyncQueueIterator(queue):
            self.dispatch(event)


async def main():
    tree_handler = ElvaTree()
    await tree_handler.start()

if __name__ == "__main__":
    anyio.run(main)
