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

    @staticmethod
    def _get_lines(text):
        if text:
            lines = text.splitlines(keepends=False)
            if text.endswith(tuple(VALID_NEWLINES)):
                lines.append("")
            return lines
        else:
            return [""]

    @property
    def lines(self):
        return self._get_lines(self.text)

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
    def get_binary_index_from_string_index(self, index):
        return len(self.text[:index].encode())

    def get_index_from_location(self, location):
        """Convert from UI location into UTF-8 indeces."""

        # we assume that UI location is equivalent to Python string indexing
        #
        # this does not hold anymore on custom UI indexing, e.g. when
        # implementing grapheme clusters, rich text blocks like images or
        # other block formatting indeces

        row, col = location

        # select all lines until row, including last one
        lines = self.lines[: row + 1]

        # trim last line to col, excluding last one
        lines[-1] = lines[-1][:col]

        return len(self.newline.join(lines))

    def get_binary_index_from_location(self, location):
        return self.get_binary_index_from_string_index(
            self.get_index_from_location(location)
        )

    def get_index_from_binary_index(self, index):
        return len(self.btext[:index].decode())

    def get_location_from_index(self, index):
        column_index = 0
        newline_length = len(self.newline)
        for line_index in range(self.line_count):
            next_column_index = (
                column_index + len(self.get_line(line_index)) + newline_length
            )
            if index < next_column_index:
                return (line_index, index - column_index)
            elif index == next_column_index:
                return (line_index + 1, 0)
            column_index = next_column_index

    def get_location_from_binary_index(self, index):
        return self.get_location_from_index(self.get_index_from_binary_index(index))

    ##
    # info
    #
    def get_text_range(self, start, end):
        if start == end:
            return ""

        top, bottom = sorted((start, end))
        top_row, top_column = top
        bottom_row, bottom_column = bottom
        lines = self.lines
        if top_row == bottom_row:
            line = lines[top_row]
            selected_text = line[top_column:bottom_column]
        else:
            start_line = lines[top_row]
            end_line = lines[bottom_row] if bottom_row <= self.line_count - 1 else ""
            selected_text = start_line[top_column:]
            for row in range(top_row + 1, bottom_row):
                selected_text += self._newline + lines[row]

            if bottom_row < self.line_count:
                selected_text += self._newline
                selected_text += end_line[:bottom_column]

        return selected_text

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

    def generate_edit_result(self, start, end, text):
        top, bottom = sorted((start, end))
        top_row, top_column = top
        bottom_row, bottom_column = bottom

        insert_lines = text.splitlines()
        if text.endswith(tuple(VALID_NEWLINES)):
            # Special case where a single newline character is inserted.
            insert_lines.append("")

        lines = self.lines

        replaced_text = self.get_text_range(top, bottom)
        if bottom_row >= len(lines):
            after_selection = ""
        else:
            after_selection = lines[bottom_row][bottom_column:]

        if top_row >= len(lines):
            before_selection = ""
        else:
            before_selection = lines[top_row][:top_column]

        if insert_lines:
            insert_lines[0] = before_selection + insert_lines[0]
            destination_column = len(insert_lines[-1])
            insert_lines[-1] = insert_lines[-1] + after_selection
        else:
            destination_column = len(before_selection)
            insert_lines = [before_selection + after_selection]

        lines[top_row : bottom_row + 1] = insert_lines
        destination_row = top_row + len(insert_lines) - 1

        end_location = (destination_row, destination_column)

        return EditResult(end_location, replaced_text)

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
        start = self.get_location_from_binary_index(bstart)

        # start == end
        result = self.generate_edit_result(start, start, insert_value)
        edit = YEdit(result, insert_value, start, start, maintain_selection_offset=True)
        self.edits.put_nowait(edit)

    def on_delete(self, range_offset, range_length):
        bstart = range_offset
        bend = range_offset + range_length

        start, end = [
            self.get_location_from_binary_index(index) for index in (bstart, bend)
        ]

        result = self.generate_edit_result(start, end, "")
        edit = YEdit(result, "", start, end, maintain_selection_offset=False)
        self.edits.put_nowait(edit)

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

    def on_mount(self):
        self.run_worker(self.perform_edits())

    async def perform_edits(self):
        async for edit in self.document:
            self.log("SELECTION:", self.selection)
            self.log("TEXT:")
            self.log(self.document.text)
            self.edit(edit)
            self.log("SELECTION:", self.selection)
            self.log(edit)

    def _replace_via_keyboard(self, insert, start, end):
        if self.read_only:
            return None
        return self.replace(insert, start, end)

    def _delete_via_keyboard(self, start, end):
        if self.read_only:
            return None
        return self.delete(start, end)

    def replace(self, insert, start, end, /):
        self.document.replace_range(start, end, insert)

    def delete(self, start, end, /):
        self.document.replace_range(start, end, "")

    def insert(self, text, location=None, /):
        if location is None:
            location = self.cursor_location()
        self.document.replace_range(location, location, text)

    def clear(self, /):
        self.delete((0, 0), self.document.end)

    def render_line(self, y):
        # update the cache of wrapped lines
        #
        # TODO: Why is this not done automatically?
        #       Probably we need to update the wrapped lines cache elsewhere.
        self.wrapped_document.wrap(self.size.width)
        return super().render_line(y)


class YEdit(Edit):
    def __init__(self, edit_result, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._edit_result = edit_result

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

        # OBSOLETE; not needed
        # text = self.text

        # This code is mostly handling how we adjust TextArea.selection
        # when an edit is made to the document programmatically.
        # We want a user who is typing away to maintain their relative
        # position in the document even if an insert happens before
        # their cursor position.

        edit_bottom_row, edit_bottom_column = self.bottom

        selection_start, selection_end = text_area.selection
        selection_start_row, selection_start_column = selection_start
        selection_end_row, selection_end_column = selection_end

        # OBSOLETE; already present
        # edit_result = text_area.document.replace_range(self.top, self.bottom, text)
        edit_result = self._edit_result

        new_edit_to_row, new_edit_to_column = edit_result.end_location

        column_offset = new_edit_to_column - edit_bottom_column
        target_selection_start_column = (
            selection_start_column + column_offset
            if edit_bottom_row == selection_start_row
            and edit_bottom_column <= selection_start_column
            else selection_start_column
        )
        target_selection_end_column = (
            selection_end_column + column_offset
            if edit_bottom_row == selection_end_row
            and edit_bottom_column <= selection_end_column
            else selection_end_column
        )

        row_offset = new_edit_to_row - edit_bottom_row
        target_selection_start_row = (
            selection_start_row + row_offset
            if edit_bottom_row <= selection_start_row
            else selection_start_row
        )
        target_selection_end_row = (
            selection_end_row + row_offset
            if edit_bottom_row <= selection_end_row
            else selection_end_row
        )

        if self.maintain_selection_offset:
            self._updated_selection = Selection(
                start=(target_selection_start_row, target_selection_start_column),
                end=(target_selection_end_row, target_selection_end_column),
            )
        else:
            self._updated_selection = Selection.cursor(edit_result.end_location)

        # OBSOLETE; already set
        # self._edit_result = edit_result
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
