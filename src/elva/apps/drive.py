"""
ELVA drive app.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

import anyio
from base import BaseApp
from pycrdt import Doc, Map, MapEvent
from pycrdt_websocket.ystore import FileYStore
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


def pprint_json(json_str: str):
    """
    Pretty-print JSON strings.

    Arguments:
        json_str: the JSON to print.
    """
    print(json.dumps(json.loads(json_str), indent=4, sort_keys=True))


def print_tree(tree: Map):
    """
    Pretty-print a file tree.

    Arguments:
        tree: the Y map holding the directory tree.
    """
    pprint_json(tree.to_json())


# source: https://gist.github.com/mivade/f4cb26c282d421a62e8b9a341c7c65f6
class AsyncQueueEventHandler(FileSystemEventHandler):
    """
    Asynchronous file system event handler.
    """

    def __init__(
        self,
        queue: asyncio.Queue,
        loop: asyncio.BaseEventLoop,
        *args: tuple,
        **kwargs: dict,
    ):
        """
        Arguments:
            queue: the asynchronous queue to put file system event objects in.
            loop: the asynchronous event loop.
            args: positional arguments passed to `watchdog.events.FileSystemEventHandler`.
            kwargs: keyword arguments passed to `watchdog.events.FileSystemEventHandler`.
        """
        self._loop = loop
        self._queue = queue
        super(*args, **kwargs)

    def on_any_event(self, event: FileSystemEvent) -> None:
        """
        Hook called on any file system event detected.

        This method puts the file system event object in the asynchronous queue.

        Arguments:
            event: an object holding information about the observed file system event.
        """
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)


class AsyncQueueIterator:
    """
    Asynchronous file system event iterator.
    """

    def __init__(
        self, queue: asyncio.Queue, loop: Optional[asyncio.BaseEventLoop] = None
    ):
        """
        Arguments:
            queue: the asynchronous queue to read file sytem event objects from.
            loop: the asynchronous event loop.
        """
        self.queue = queue

    def __aiter__(self):
        """
        Implement the asynchronous iterator protocol.
        """
        return self

    async def __anext__(self) -> FileSystemEvent:
        """
        Define the next asynchronous iterator step:

        Returns:
            the next file system event object in the asynchronous event queue.

        Raises:
            StopAsyncIteration: if there is no file system event object.
        """
        item = await self.queue.get()

        if item is None:
            raise StopAsyncIteration

        return item


class Drive(BaseApp):
    """
    Drive object.
    """

    def __init__(self, path: None | str = None, doc: None | Doc = None):
        """
        Arguments:
            path: the path to watch on recursively.
            doc: the Y document to store the contents in.
        """
        super().__init__(doc)

        self.path = Path(path) if path is not None else Path(".")

        self.loop = asyncio.get_event_loop()
        self.doc_queue = asyncio.Queue()

        self.METHOD_EVENT_MAP = {
            "created": self.on_created,
            "deleted": self.on_deleted,
            "modified": self.on_modified,
            "moved": self.on_moved,
            "opened": self.on_opened,
            "closed": self.on_closed,
        }

    def callback(self, event: MapEvent):
        """
        Hook called on a change in the Y map directory tree.

        Prints the event object for debugging purposes.

        Arguments:
            event: an object holding information about the change in the Y map directory tree.
        """
        print(event)

    async def read_tree(self):
        """
        Read the directory tree.
        """
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
                    if not os.path.exists(file_path + ".y"):
                        doc = Doc()
                        doc["source"] = Map()
                        with open(file_path, "rb") as file_buffer:
                            doc["source"]["bytes"] = file_buffer.read()
                        self.tree.update(self.tree_entry(file_path, doc))

    async def start(self):
        """
        Start the drive app.

        This reads the directory tree under the given path and starts the watcher as well as the dispatcher routine for incoming file system events.
        """
        async with anyio.create_task_group() as self.tg:
            self.tg.start_soon(self.read_tree)
            self.tg.start_soon(self._watch, self.path, self.doc_queue, self.loop)
            self.tg.start_soon(self._dispatch, self.doc_queue)

    def tree_entry(self, path: str, doc: None | Doc = None) -> dict[str, None | Doc]:
        """
        Generate a tree entry:

        Arguments:
            path: a path within the directory tree
            doc: the associated Y document with the given path.

        Returns:
            a mapping of the path to its correspinding Y document, if present.
        """
        return {path: doc}

    def dispatch(self, event: FileSystemEvent):
        """
        Dispatch to event methods based on the given file system event.

        Arguments:
            event: file system event to dispatch.
        """
        method = self.METHOD_EVENT_MAP[event.event_type]

        if not event.is_directory:
            method(event)

    def on_created(self, event: FileSystemEvent):
        """
        Hook called on a created source.

        Arguments:
            event: file system event to read the source path from.
        """
        self.tree.update(self.tree_entry(event.src_path))

    def on_deleted(self, event: FileSystemEvent):
        """
        Hook called on a deleted source.

        Arguments:
            event: file system event to read the source path from.
        """
        self.tree.pop(event.src_path)

    def on_opened(self, event: FileSystemEvent):
        """
        Hook called on an opened source.

        Arguments:
            event: file system event to read the source path from.
        """
        self.tree.update(self.tree_entry(event.src_path))

    def on_closed(self, event: FileSystemEvent):
        """
        Hook called on a closed source.

        Arguments:
            event: file system event to read the source path from.
        """
        self.tree.update(self.tree_entry(event.src_path))

    def on_modified(self, event: FileSystemEvent):
        """
        Hook called on a modified source.

        Arguments:
            event: file system event to read the source path from.
        """
        self.tree.update(self.tree_entry(event.src_path))

    def on_moved(self, event: FileSystemEvent):
        """
        Hook called on a moved source.

        Arguments:
            event: file system event to read the source path from.
        """
        self.tree.pop(event.src_path)
        self.tree.update(self.tree_entry(event.dest_path))

    async def _watch(
        self,
        path: Path,
        queue: asyncio.Queue,
        loop: asyncio.BaseEventLoop,
        recursive: bool = False,
    ) -> None:
        """
        Watch a directory for changes.

        Arguments:
            path: the path where watch for file system events.
            queue: the asynchronous queue to put file system events in.
            loop: the asynchronous event loop.
            recursive: flag whether to also watch for file system events in subdirectories.
        """
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
        """
        Dispatch file system events read from the asynchronous event queue.

        Arguments:
            queue: the asynchronous queue to get file system event objects from.
        """
        async for event in AsyncQueueIterator(queue):
            self.dispatch(event)


async def main():
    """
    Main routine starting the drive app.
    """
    drive_handler = Drive()
    await drive_handler.start()


if __name__ == "__main__":
    anyio.run(main)
