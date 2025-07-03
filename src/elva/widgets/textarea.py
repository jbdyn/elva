"""
[`Textual`](https://textual.textualize.io/) Widgets for realtime text-editing
"""

from typing import Self

from pycrdt import Doc, Text, TextEvent
from textual.widgets import TextArea
from textual.widgets.text_area import Location


class YTextArea(TextArea):
    """
    Widget for displaying and manipulating text synchronized in realtime.
    """

    def __init__(self, ytext: Text = None, *args: tuple, **kwargs: dict):
        """
        Arguments:
            ytext: Y text data type holding the text.
            language: syntax language the text is written in.
            args: positional arguments passed to [`TextArea`][textual.widgets.TextArea].
            kwargs: keyword arguments passed to [`TextArea`][textual.widgets.TextArea].
        """
        if ytext is None:
            doc = Doc()
            doc["text"] = ytext = Text()

        self.ytext = ytext
        super().__init__(str(self.ytext), *args, **kwargs)

    @classmethod
    def code_editor(cls, ytext: Text = None, *args: tuple, **kwargs: dict) -> Self:
        return cls(ytext, *args, **kwargs)

    def get_index_from_binary_index(self, index: int) -> int:
        """
        Convert the index in UTF-8 encoding to character index.

        Arguments:
            btext: UTF-8 encoded data.
            bindex: index in `btext`.

        Returns:
            index in the UTF-8 decoded form of `btext`.
        """
        return len(self.document.text.encode()[:index].decode())

    def get_binary_index_from_index(self, index: int) -> int:
        """
        Convert the character index to index in UTF-8 encoding.

        Arguments:
            text: string to convert the index on.
            index: index in `text`.

        Returns:
            index in the UTF-8 encoded form of `text`.
        """
        return len(self.document.text[:index].encode())

    def get_location_from_binary_index(self, index: int) -> Location:
        index = self.get_index_from_binary_index(index)
        return self.document.get_location_from_index(index)

    def get_binary_index_from_location(self, location: Location) -> int:
        index = self.document.get_index_from_location(location)
        return self.get_binary_index_from_index(index)

    def on_textevent(self, event: TextEvent):
        istart = 0
        length = 0
        insert = ""
        for delta in event.delta:
            for action, var in delta.items():
                if action == "retain":
                    istart = var
                elif action == "delete":
                    length = var
                elif action == "insert":
                    insert = var

        iend = istart + length

        start = self.get_location_from_binary_index(istart)
        end = self.get_location_from_binary_index(iend)

        maintain_selection_offset = True

        super().replace(
            insert, start, end, maintain_selection_offset=maintain_selection_offset
        )

    def on_mount(self):
        """
        Hook called on mounting.

        This starts a tasks waiting for edits and updating the widget's visual appearance.
        """
        self.subscription_textevent = self.ytext.observe(self.on_textevent)

    def on_umount(self):
        self.ytext.unobserve(self.subscription_textevent)

    def replace(
        self,
        insert: str,
        start: Location,
        end: Location,
        maintain_selection_offset=True,
    ):
        doc = self.ytext.doc

        ibstart = self.get_binary_index_from_location(start)
        ibend = self.get_binary_index_from_location(end)

        with doc.transaction(origin="local"):
            if not start == end:
                del self.ytext[ibstart:ibend]
            if insert:
                self.ytext.insert(ibstart, insert)

    def delete(self, start: Location, end: Location, maintain_selection_offset=True):
        start, end = sorted((start, end))
        self.replace("", start, end)

    def insert(
        self, text: str, location: Location = None, maintain_selection_offset=True
    ):
        if location is None:
            location = self.cursor_location

        self.replace(text, location, location)
