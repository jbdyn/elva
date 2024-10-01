from asyncio import Queue

from pycrdt import Text
from textual._cells import cell_len
from textual.document._document import (
    VALID_NEWLINES,
    DocumentBase,
    Selection,
    _detect_newline_style,
)
from textual.document._document_navigator import DocumentNavigator
from textual.document._wrapped_document import WrappedDocument
from textual.geometry import Size
from textual.widgets import TextArea
from tree_sitter_languages import get_language, get_parser

NEWLINE_CHARS = "\n\r"


##
#
# utility functions
#
# TODO: Define these as methods of YTextArea when that is merged with YDocument


def ends_with_newline(text):
    return text.endswith(tuple(VALID_NEWLINES))


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

    out_of_bounds = index + 1 > len(text)
    ends_with_newline = text.endswith(tuple(VALID_NEWLINES))

    before_newline = not ends_with_newline
    on_newline = ends_with_newline and not out_of_bounds
    after_newline = ends_with_newline and out_of_bounds

    col_off = 0
    if on_newline:
        # only remove trailing newline characters in the last line
        text = text.removesuffix("\n").removesuffix("\r")
        col_off = 1
    elif after_newline or (before_newline and out_of_bounds):
        col_off = 1

    lines = get_lines(text, keepends=True)

    last_line = lines[-1]

    row = len(lines) - 1
    col = len(last_line) - 1 + col_off

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

    last_line = lines[-1].rstrip(NEWLINE_CHARS)

    col_off = 0
    if not last_line or col >= len(last_line):
        col_off = 1

    lines[-1] = last_line[: col + 1]
    index = len("".join(lines)) - 1 + col_off

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


def update_location(iloc, itop, ibot, iend_edit):
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


def get_binary_location_from_binary_index(btext, bindex):
    btext = btext[: bindex + 1]
    lines = btext.splitlines(keepends=True)
    if lines:
        if lines[-1]:
            row = len(lines) - 1
            col = len(lines[-1]) - 1
        else:
            row = len(lines)
            col = 0
    else:
        row = 0
        col = 0

    return row, col


# TODO: merge YDocument into YTextArea


class YDocument(DocumentBase):
    def __init__(self, ytext: Text, language):
        self.ytext = ytext
        self.ytext.observe(self.callback)
        self._newline = _detect_newline_style(str(ytext))
        self.edits = Queue()

        try:
            self.language = get_language(language)
            self.parser = get_parser(language)
            self.tree = self.parser.parse(self.get_btext_slice)
            self.syntax_enabled = True
        except AttributeError:
            self.syntax_enabled = False

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

    ##
    # tree-sitter
    #
    def update_tree(self, istart, iend_old, iend, start, end_old, end):
        if self.syntax_enabled:
            self.tree.edit(istart, iend_old, iend, start, end_old, end)
            self.tree = self.parser.parse(self.get_btext_slice, old_tree=self.tree)

    def get_btext_slice(self, byte_offset, point):
        lines = self.btext[byte_offset:].splitlines(keepends=True)
        if lines:
            return lines[0]
        else:
            return b""

    def query_syntax_tree(self, query, start=None, end=None):
        kwargs = {}
        if start is not None:
            kwargs["start_point"] = start
        if end is not None:
            kwargs["end_point"] = end
        captures = query.captures(self.tree.root_node, **kwargs)
        return captures

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
        btext = insert_value.encode()

        self.edits.put_nowait((bstart, bstart, btext))

        # syntax highlighting
        istart = bstart
        iend_old = bstart
        iend = bstart + len(btext)
        start = get_binary_location_from_binary_index(self.btext, istart)
        end_old = start
        end = get_binary_location_from_binary_index(self.btext, iend)
        self.update_tree(istart, iend_old, iend, start, end_old, end)

    def on_delete(self, range_offset, range_length):
        bstart = range_offset
        bend = range_offset + range_length

        self.edits.put_nowait((bstart, bend, b""))

        # syntax highlighting
        istart = bstart
        iend_old = bend
        iend = bstart
        start = get_binary_location_from_binary_index(self.btext, istart)
        end_old = get_binary_location_from_binary_index(self.btext, iend_old)
        end = start
        self.update_tree(istart, iend_old, iend, start, end_old, end)

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
        self.document = YDocument(ytext, kwargs.get("language"))
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
        # end location of the edit
        iend_edit = itop + len(btext)

        # binary indices for current selection
        # TODO: Save the selection as binary index range as well,
        #       so it does not need to be retrieved from the binary content.
        #       Then, there is no need for a YTextArea.btext attribute anymore;
        #       the history management is already implemented in YDoc
        start_sel, end_sel = self.selection
        start_sel, end_sel = sorted((start_sel, end_sel))  # important!
        istart, iend = [
            get_binary_index_from_location(self.btext, loc)
            for loc in (start_sel, end_sel)
        ]

        # calculate new start and end locations
        ilen = iend - istart

        new_istart = update_location(istart, itop, ibot, iend_edit)
        iend = new_istart + ilen

        if new_istart == istart:
            iend = update_location(iend, itop, ibot, iend_edit)

        istart = new_istart

        # turn binary indices into locations
        self.update_btext()

        start, end = [
            get_location_from_binary_index(self.btext, index)
            for index in (istart, iend)
        ]

        # UI updates
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
