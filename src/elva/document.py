import logging
import sys
import time
from asyncio import Queue

import anyio
from pycrdt import Doc, Text
from rich.text import Text as RichText
from textual._cells import cell_len
from textual.app import App
from textual.document._document import (
    VALID_NEWLINES,
    DocumentBase,
    EditResult,
    Selection,
    _detect_newline_style,
)
from textual.document._document_navigator import DocumentNavigator
from textual.document._edit import Edit
from textual.document._wrapped_document import WrappedDocument
from textual.geometry import Size
from textual.widgets import TextArea

log = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
log.addHandler(handler)
log.setLevel(logging.DEBUG)

BVALID_NEWLINES = [newline.encode() for newline in VALID_NEWLINES]


def get_lines(text, keepends=False):
    lines = text.splitlines(keepends=keepends)
    if not lines or text.endswith(tuple(VALID_NEWLINES)):
        lines.append("")
    return lines


def get_index_from_binary_index(btext, bindex):
    return len(btext[:bindex].decode())


def get_binary_index_from_index(text, index):
    return len(text[:index].encode())


def get_location_from_index(text, index):
    text = text[: index + 1]
    lines = text.splitlines(keepends=True)
    if not lines or (text.endswith(tuple(VALID_NEWLINES)) and index >= len(text)):
        lines.append("")

    row = len(lines) - 1

    last_line = lines[-1]
    if last_line.endswith(tuple(VALID_NEWLINES)):
        last_line = last_line.rstrip("".join(VALID_NEWLINES))
        last_line += " "
    if not last_line or index >= len("".join(lines)):
        last_line += " "

    col = len(last_line) - 1

    return row, col


def get_location_from_binary_index(btext, bindex):
    text = btext.decode()
    return get_location_from_index(text, get_index_from_binary_index(btext, bindex))


def get_index_from_location(text, location):
    row, col = location

    # be ignorant about the type of newline characters
    lines = get_lines(text, keepends=True)

    # include given row and col indices
    lines = lines[: row + 1]
    last_line = lines[-1]
    if last_line.endswith(tuple(VALID_NEWLINES)):
        last_line = last_line.rstrip("".join(VALID_NEWLINES))
        last_line += " "

    if not last_line or col >= len(last_line):
        last_line += " "
    lines[-1] = last_line[: col + 1]
    index = len("".join(lines)) - 1

    return index


def get_binary_index_from_location(btext, location):
    text = btext.decode()
    index = get_index_from_location(text, location)
    return get_binary_index_from_index(text, index)


def get_text_range(text, start, end):
    start, end = sorted((start, end))
    istart, iend = [get_index_from_location(text, loc) for loc in (start, end)]

    return text[istart:iend]


def get_binary_text_range(btext, start, end):
    start, end = sorted((start, end))
    bistart, biend = [
        get_binary_index_from_location(btext, loc) for loc in (start, end)
    ]

    return btext[bistart:biend]


class YDocument(DocumentBase):
    def __init__(self, ytext: Text):
        self.ytext = ytext
        self.ytext.observe(self.callback)
        self._newline = _detect_newline_style(str(ytext))
        self.edits = Queue()

    ##
    # core
    #
    @property
    def text(self):
        return str(self.ytext)

    @property
    def btext(self):
        return self.text.encode()

    ##
    # lines
    #
    @property
    def newline(self):
        return self._newline

    @property
    def lines(self):
        return get_lines(self.text)

    def get_line(self, index):
        return self.lines[index]

    @property
    def line_count(self):
        return len(self.lines)

    def __getitem__(self, index):
        return self.lines[index]

    ##
    # index conversion
    #
    def get_binary_index_from_index(self, index):
        return get_binary_index_from_index(self.btext, index)

    def get_index_from_location(self, location):
        return get_index_from_location(self.text, location)

    def get_binary_index_from_location(self, location):
        return get_binary_index_from_location(self.btext, location)

    def get_index_from_binary_index(self, index):
        return get_index_from_binary_index(self.btext, index)

    def get_location_from_index(self, index):
        return get_location_from_index(self.text, index)

    def get_location_from_binary_index(self, index):
        return get_location_from_binary_index(self.btext, index)

    ##
    # info
    #
    def get_text_range(self, start, end):
        return get_text_range(self.text, start, end)

    def get_size(self, indent_width):
        lines = self.lines
        rows = len(lines)
        cell_lengths = [cell_len(line.expandtabs(indent_width)) for line in lines]
        cols = max(cell_lengths, default=0)
        return Size(cols, rows)

    @property
    def start(self):
        return (0, 0)

    @property
    def end(self):
        last_line = self.lines[-1]
        return (self.line_count - 1, len(last_line))

    ##
    # manipulation
    #
    def replace_range(self, start, end, text):
        start, end = sorted((start, end))
        bstart, bend = [
            self.get_binary_index_from_location(location) for location in (start, end)
        ]

        doc = self.ytext.doc

        # make transaction atomic and include an origin for the provider
        with doc.transaction(origin="ydocument"):
            if not start == end:
                del self.ytext[bstart:bend]
            if text:
                self.ytext.insert(bstart, text)

    def parse(self, event):
        deltas = event.delta

        range_offset = 0
        for delta in deltas:
            for action, var in delta.items():
                match action:
                    case "retain":
                        range_offset = var
                        self.on_retain(range_offset)
                    case "insert":
                        insert_value = var
                        self.on_insert(range_offset, insert_value)
                    case "delete":
                        range_length = var
                        self.on_delete(range_offset, range_length)

    def callback(self, event):
        self.parse(event)

    def on_retain(self, range_offset):
        pass

    def on_insert(self, range_offset, insert_value):
        bstart = range_offset

        self.edits.put_nowait((bstart, bstart, insert_value.encode()))

    def on_delete(self, range_offset, range_length):
        bstart = range_offset
        bend = range_offset + range_length

        self.edits.put_nowait((bstart, bend, b""))

    ##
    # iteration protocol
    #
    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.edits.get()


class YTextArea(TextArea):
    def __init__(self, ytext, *args, **kwargs):
        super().__init__(str(ytext), *args, **kwargs)
        self.document = YDocument(ytext)
        self.wrapped_document = WrappedDocument(self.document)
        self.navigator = DocumentNavigator(self.wrapped_document)
        self.update_btext()

    def on_mount(self):
        self.run_worker(self.perform_edits())

    def update_btext(self):
        self.btext = self.document.btext

    async def perform_edits(self):
        async for itop, ibot, btext in self.document:
            self.edit(itop, ibot, btext)

    def edit(self, itop, ibot, btext):
        def update_location(iloc):
            # location before top
            loc_top = iloc < itop

            # location between top and bottom
            top_loc_bot = itop <= iloc and iloc <= ibot

            if loc_top:
                pass
            elif top_loc_bot:
                iloc = iend_edit
            else:
                # location after bottom
                ioff = ibot - iloc
                iloc = iend_edit - ioff

            return iloc

        print("ITOP:IBOT", itop, ibot)

        iend_edit = itop + len(btext)
        print("IEND_EDIT", iend_edit)

        print("SELECTION", self.selection)
        start_sel, end_sel = self.selection
        start_sel, end_sel = sorted((start_sel, end_sel))
        istart, iend = [
            get_binary_index_from_location(self.btext, loc)
            for loc in (start_sel, end_sel)
        ]
        print("ISTART", istart, "IEND", iend)

        # calculate new start and end locations
        ilen = iend - istart
        print("ILEN", ilen)

        new_istart = update_location(istart)
        print("NEW_ISTART", new_istart)
        iend = new_istart + ilen
        if new_istart == istart:
            iend = update_location(iend)
        print("NEW_IEND", new_istart)

        istart = new_istart

        print("BTEXT BEFORE", self.btext)
        self.update_btext()
        print("BTEXT AFTER", self.btext)

        start = get_location_from_binary_index(self.btext, istart)
        end = get_location_from_binary_index(self.btext, iend)

        print("START:END", start, end)

        self.wrapped_document.wrap(self.wrap_width, self.indent_width)

        self._refresh_size()
        self.selection = Selection(start=start, end=end)
        self.record_cursor_width()

        self._build_highlight_map()

        self.post_message(self.Changed(self))

    def _replace_via_keyboard(self, insert, start, end):
        if self.read_only:
            return None
        return self.replace(start, end, insert)

    def _delete_via_keyboard(self, start, end):
        if self.read_only:
            return None
        return self.delete(start, end)

    def replace(self, start, end, text, /):
        self.document.replace_range(start, end, text)

    def delete(self, start, end, /):
        self.document.replace_range(start, end, "")

    def insert(self, text, location=None, /):
        if location is None:
            location = self.cursor_location()
        self.document.replace_range(location, location, text)

    def clear(self, /):
        self.delete(self.document.start, self.document.end)

    def render_line(self, y):
        # update the cache of wrapped lines
        #
        # TODO: Why is this not done automatically?
        #       Probably we need to update the wrapped lines cache elsewhere.
        self.wrapped_document.wrap(self.size.width)
        return super().render_line(y)


class YEdit(Edit):
    def __init__(self, text, start, end):
        super().__init__(text, start, end)
        self.btext = text.encode()

    def generate_edit_result(self, text_area, text):
        # calculate binary start and end index

        # replaced text
        replaced_text = text_area.btext[self.top : self.bottom].decode()

        # end location
        btext = text.encode()
        biend_location = self.top + len(btext)

        return EditResult(end_location=biend_location, replaced_text=replaced_text)

    def do(self, text_area, record_selection: bool = True) -> EditResult:
        """Perform the edit operation.

        Args:
            text_area: The `TextArea` to perform the edit on.
            record_selection: If True, record the current selection in the TextArea
                so that it may be restored if this Edit is undone in the future.

        Returns:
            An `EditResult` containing information about the replace operation.
        """
        if record_selection:
            self._original_selection = text_area.selection

        # This code is mostly handling how we adjust TextArea.selection
        # when an edit is made to the document programmatically.
        # We want a user who is typing away to maintain their relative
        # position in the document even if an insert happens before
        # their cursor position.

        def get_index(location):
            return text_area.document.get_index_from_location(location)

        def get_location(index):
            return text_area.document.get_location_from_index(index)

        # locations
        top = self.top
        bot = self.bottom
        start, end = text_area.selection
        start, end = sorted((start, end))
        end_location = edit_result.end_location

        edit_result = self.generate_edit_result(start, end, self.text)
        # - top, bottom, i.e. from_ and to_location
        # - text_area.selection, i.e. cursor
        # - end_location

        itop = get_index(top)
        ibot = get_index(bot)
        iend_loc = get_index(end_location)

        return edit_result

    def undo(self, text_area: TextArea) -> EditResult:
        """Undo the edit operation.

        Looks at the data stored in the edit, and performs the inverse operation of `Edit.do`.

        Args:
            text_area: The `TextArea` to undo the insert operation on.

        Returns:
            An `EditResult` containing information about the replace operation.
        """
        replaced_text = self._edit_result.replaced_text
        edit_end = self._edit_result.end_location

        # Replace the span of the edit with the text that was originally there.
        undo_edit_result = text_area.document.replace_range(
            self.top, edit_end, replaced_text
        )
        self._updated_selection = self._original_selection

        return undo_edit_result


class TestApp(App):
    def compose(self):
        doc = Doc()
        text = Text()
        doc["text"] = text
        yield YTextArea(text)


#
# test script
#
async def remote(ytext):
    global i
    while True:
        ytext += f"remote: line {i}\n"
        # yield to event loop
        await anyio.sleep(0)
        i += 1


async def local(ydocument):
    global j
    while True:
        text = f"local: line {j}\n"
        ydocument.replace_range((j, 0), (j, len(text)), text)
        await anyio.sleep(0)
        j += 1


async def get(ydocument):
    async for edit in ydocument:
        print(ydocument.get_line(edit.end_location[0]))


async def test_ydocument():
    global i
    global j

    i = 0
    j = 0

    ydoc = Doc()
    ydoc["text"] = ytext = Text("")

    ydocument = YDocument(ytext)

    async with anyio.create_task_group() as tg:
        tg.start_soon(remote, ytext)
        tg.start_soon(local, ydocument)
        tg.start_soon(get, ydocument)


async def main():
    app = TestApp()
    await app.run_async()


if __name__ == "__main__":
    try:
        anyio.run(main)
    except KeyboardInterrupt:
        print("stopped\n")
