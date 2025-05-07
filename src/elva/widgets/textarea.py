"""
[`Textual`](https://textual.textualize.io/) Widgets for realtime text-editing
"""

from asyncio import Queue

from pycrdt import Text, TextEvent
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
from textual.strip import Strip
from textual.widgets import TextArea
from tree_sitter import Language, Node, Parser, Point, Query, Tree
from tree_sitter_language_pack import get_language, get_parser

# TODO: Define these as methods of YTextArea when that is merged with YDocument
# TODO: Use an Array[Text] Y data type to represent document contents
#       to be agnostic to newlines.
# TODO: merge YDocument into YTextArea


NEWLINE_CHARS = "\n\r"
"""String of newline characters."""


##
#
# utility functions
#


def ends_with_newline(text: str) -> bool:
    """
    Check whether a given text ends with a newline character, i.e. `\\n` or `\\r`.

    Arguments:
        text: the text to check.

    Returns:
        If `True`, the given text ends with a newline character.
    """
    return text.endswith(tuple(VALID_NEWLINES))


def get_lines(text: str, keepends: bool = False) -> list[str]:
    """
    Split a text into its lines.

    If `text` is empty or ends with a newline character, an empty line is appended to the list of lines.

    Arguments:
        text: the text to split into lines.
        keepends: flag whether to keep the newline characters in the line strings.

    Returns:
        a list of lines.
    """
    lines = text.splitlines(keepends=keepends)
    if not lines or ends_with_newline(text):
        lines.append("")
    return lines


def get_index_from_binary_index(btext: bytes, bindex: int) -> int:
    """
    Convert the index in UTF-8 encoding to character index.

    Arguments:
        btext: UTF-8 encoded data.
        bindex: index in `btext`.

    Returns:
        index in the UTF-8 decoded form of `btext`.
    """
    return len(btext[:bindex].decode())


def get_binary_index_from_index(text: str, index: int) -> int:
    """
    Convert the character index to index in UTF-8 encoding.

    Arguments:
        text: string to convert the index on.
        index: index in `text`.

    Returns:
        index in the UTF-8 encoded form of `text`.
    """
    return len(text[:index].encode())


def get_location_from_index(text: str, index: int) -> tuple[int, int]:
    """
    Return the 2D row and column coordinates in `text` at position `index`.

    Arguments:
        text: string where to find the coordinates in.
        index: position in `text` to convert to coordinates.

    Returns:
        a tuple `(row, col)` of row and column position.
    """
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


def get_location_from_binary_index(btext: bytes, bindex: int) -> tuple[int, int]:
    """
    Return the 2D row and column coordinates in the UTF-8 decoded form of `btext` at position `bindex`.

    Arguments:
        btext: UTF-8 encoded string where to find the coordinates in.
        bindex: position in `btext` to convert to coordinates.

    Returns:
        a tuple `(row, col)` of row and column position in the UTF-8 decoded form of `btext`.
    """
    text = btext.decode()
    return get_location_from_index(text, get_index_from_binary_index(btext, bindex))


def get_index_from_location(text: str, location: tuple[int, int]) -> int:
    """
    Convert 2D row and column coordinates to the index position in `text`.

    Arguments:
        text: the text in which to find the index.
        location: a tuple of row and column coordinates.

    Returns:
        the index position in `text` at the given `location`.
    """
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


def get_binary_index_from_location(btext: bytes, location: tuple[int, int]) -> int:
    """
    Convert 2D row and column coordinates to the binary index position in `btext`.

    Arguments:
        btext: the UTF-8 encoded text in which to find the binary index.
        location: a tuple of row and column coordinates.

    Returns:
        the binary index position in `btext` at the given `location`.
    """
    text = btext.decode()
    index = get_index_from_location(text, location)
    return get_binary_index_from_index(text, index)


def get_text_range(text: str, start: tuple[int, int], end: tuple[int, int]) -> str:
    """
    Get the slice in `text` between a `start` and an `end` location.

    Arguments:
        text: the text to slice.
        start: a tuple of row and column coordinates to start the slice at.
        end: a tuple of row and column coordinates the end the slice at.

    Returns:
        the slice in `text` between `start` and `end` location.
    """
    start, end = sorted((start, end))
    istart, iend = [get_index_from_location(text, loc) for loc in (start, end)]

    return text[istart:iend]


def get_binary_text_range(
    btext: bytes, start: tuple[int, int], end: tuple[int, int]
) -> bytes:
    """
    Get the slice in the UTF-8 encoded `btext` between a `start` and an `end` location.

    Arguments:
        btext: the UTF-8 encoded text to slice.
        start: a tuple of row and column coordinates to start the slice at.
        end: a tuple of row and column coordinates the end the slice at.

    Returns:
        the UTF-8 encoded slice in `btext` between `start` and `end` location.
    """
    start, end = sorted((start, end))
    bistart, biend = [
        get_binary_index_from_location(btext, loc) for loc in (start, end)
    ]

    return btext[bistart:biend]


def update_location(iloc: int, itop: int, ibot: int, iend_edit: int) -> int:
    """
    Update a location index with respect to edit metrics.

    Arguments:
        iloc: index of the location to be updated.
        itop: index of the start of the edited range.
        ibot: index of the end of the edited range.
        iend_edit: index of the end of the edit's content.

    Returns:
        updated location index.
    """

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


def get_binary_location_from_binary_index(btext: bytes, bindex: int) -> tuple[int, int]:
    """
    Get the 2D row and column coordinates in UTF-8 encoded text at a given position.

    Arguments:
        btext: UTF-8 encoded text to find the location in.
        bindex: index position to convert to a location.

    Returns:
        a tuple (row, column) of row and column coordinates.
    """
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


class YDocument(DocumentBase):
    """
    The inner document holding the realtime synchronized content.

    It supports indexing and implements the asynchronous iterator protocol.

    This class is intended for use in [`YTextArea`][elva.widgets.textarea.YTextArea].

    Examples:
        Indexing:

        ```
        text = r"Hello,\\nWorld!"
        ytext = Text(text)
        doc = YDocument(ytext, "python")
        assert doc[0] == "Hello,"
        ```

        Asynchronous iterator protocol:
        ```
        async for edit in doc:
            do_something(edit)
        ```
    """

    ytext: Text
    """Y text data type holding the document content."""

    edits: Queue
    """Queue of applied edits."""

    language: Language
    """Instance of the tree-sitter language used for queries."""

    parser: Parser
    """Instance of the tree-sitter parser."""

    tree: Tree
    """Instance of the tree-sitter tree the parser updates incrementally."""

    syntax_enabled: bool
    """Flag whether to apply tree-sitter queries."""

    def __init__(self, ytext: Text, language: str):
        """
        Arguments:
            ytext: Y text data type holding the document content.
            language: the language the document content is written in.

        """
        self.ytext = ytext
        self.ytext.observe(self.callback)
        self._newline = _detect_newline_style(str(ytext))
        self.edits = Queue()

        try:
            self.language = get_language(language)
            self.parser = get_parser(language)
            self.tree = self.parser.parse(self.get_btext_slice)
            self.syntax_enabled = True
        except LookupError:
            self.syntax_enabled = False

    ##
    # core
    #
    @property
    def text(self) -> str:
        """
        Text representation of the Y text data type content.
        """
        return str(self.ytext)

    @property
    def btext(self) -> bytes:
        """
        UTF-8 encoded text representation of the Y text data type content.
        """
        return self.text.encode()

    ##
    # lines
    #
    @property
    def newline(self) -> str:
        """
        The newline character used in this document.
        """
        return self._newline

    @property
    def lines(self) -> list[str]:
        """
        The document's content formatted as a list of lines.
        """
        return get_lines(self.text)

    def get_line(self, row: int) -> str:
        """
        Get the line's content at a specified row.

        Arguments:
            row: the row index.

        Returns:
            the document content in the specified row.
        """
        return self.lines[row]

    @property
    def line_count(self) -> int:
        """
        The number of lines.
        """
        return len(self.lines)

    def __getitem__(self, row: int) -> str:
        """
        Get the line's content at a specified row.

        Arguments:
            row: the row index.

        Returns:
            the document content in the specified row.
        """
        return self.lines[row]

    ##
    # index conversion
    #
    def get_binary_index_from_index(self, index: int) -> int:
        """
        Convert the character index to index in UTF-8 encoding.

        Arguments:
            index: index in the document's text.

        Returns:
            index in the document's UTF-8 encoded text.
        """
        return get_binary_index_from_index(self.btext, index)

    def get_index_from_location(self, location: tuple[int, int]) -> int:
        """
        Convert 2D row and column coordinates to index position.

        Arguments:
            location: a tuple of row and column coordinates.

        Returns:
            the index in the document's text.
        """
        return get_index_from_location(self.text, location)

    def get_binary_index_from_location(self, location: tuple[int, int]) -> int:
        """
        Convert location to binary index.

        Arguments:
            location: a tuple of row and column coordinates.

        Returns:
            the index in the document's UTF-8 encoded text.
        """
        return get_binary_index_from_location(self.btext, location)

    def get_index_from_binary_index(self, index: int) -> int:
        """
        Convert binary index to index.

        Arguments:
            index: index in the document's UTF-8 encoded text.

        Returns:
            the index in the document's text.
        """
        return get_index_from_binary_index(self.btext, index)

    def get_location_from_index(self, index: int) -> tuple[int, int]:
        """
        Convert index to location.

        Arguments:
            index: index in the document's text.

        Returns:
            the location in the document's text.
        """
        return get_location_from_index(self.text, index)

    def get_location_from_binary_index(self, index: int) -> tuple[int, int]:
        """
        Convert binary index to location.

        Arguments:
            index: index in the document's UTF-8 encoded text.

        Returns:
            the location in the document's text.
        """
        return get_location_from_binary_index(self.btext, index)

    ##
    # info
    #
    def get_text_range(self, start: tuple[int, int], end: tuple[int, int]) -> str:
        """
        Get the text within a certain range.

        Arguments:
            start: location where the text range starts.
            end: location where the text range ends.

        Returns:
            the slice of text within `start` and `end` location.
        """
        return get_text_range(self.text, start, end)

    def get_size(self, indent_width: int) -> Size:
        """
        Get the size of the document's text.

        Arguments:
            indent_width: number of spaces to replace with tabs.

        Returns:
            object holding the number of columns and rows.
        """
        lines = self.lines
        rows = len(lines)
        cell_lengths = [cell_len(line.expandtabs(indent_width)) for line in lines]
        cols = max(cell_lengths, default=0)
        return Size(cols, rows)

    @property
    def start(self) -> tuple[int, int]:
        """
        Start location of the document's text.
        """
        return (0, 0)

    @property
    def end(self) -> tuple[int, int]:
        """
        End location of the document's text.
        """
        last_line = self.lines[-1]
        return (self.line_count - 1, len(last_line))

    ##
    # manipulation
    #
    def replace_range(self, start: tuple[int, int], end: tuple[int, int], text: str):
        """
        Apply an edit.

        First, the range from `start` to `end` gets deleted, then the given `text` gets inserted at `start`.

        This covers all kinds of text manipulation:
        - inserting: `start == end`, `text` is not empty
        - deleting: `start != end`, `text` is empty
        - replacing: `start != end`, `text` is not empty

        Arguments:
            start: location where the edit begins
            end: location where the edit ends
            text: the text to insert at `start`
        """
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
    def update_tree(
        self,
        istart: int,
        iend_old: int,
        iend: int,
        start: tuple[int, int],
        end_old: tuple[int, int],
        end: tuple[int, int],
    ):
        """
        Update the the syntax tree if syntax is enabled.

        This method is called by the class internally.

        Arguments:
            istart: binary start index
            iend_old: binary end index before the edit
            iend: binary end index after the edit
            start: binary start location
            end_old: binary end location before the edit.
            end: binary end location after the edit.
        """
        if self.syntax_enabled:
            self.tree.edit(istart, iend_old, iend, start, end_old, end)
            self.tree = self.parser.parse(self.get_btext_slice, old_tree=self.tree)

    def get_btext_slice(self, byte_offset: int, position: Point) -> bytes:
        """
        Get a slice of the document's UTF-8 encoded text.

        This method is called by the class internally.

        Arguments:
            byte_offset: binary start index of the slice.
            position: binary start location of the slice.

        Returns:
            line chunk starting at `byte_offset` or an empty bytes literal if at the end of document's UTF-8 encoded text.
        """
        lines = self.btext[byte_offset:].splitlines(keepends=True)
        if lines:
            return lines[0]
        else:
            return b""

    def query_syntax_tree(
        self, query: Query, start: Point = None, end: Point = None
    ) -> dict[str, list[Node]]:
        """
        Get captures for a query on the syntax tree.

        Arguments:
            query: instance of a tree-sitter query
            start: start point of the query
            end: end point of the query

        Returns:
            a dict where the keys are the names of the captures and the values are lists of the captured nodes.
        """
        kwargs = {}
        if start is not None:
            kwargs["start_point"] = start
        if end is not None:
            kwargs["end_point"] = end
        captures = query.captures(self.tree.root_node, **kwargs)
        return captures

    def parse(self, event: TextEvent):
        """
        Parse the contents of a document's Y text data type event.

        This method is called by the class internally.

        Arguments:
            event: event emitted by a change in the document's Y text data type.
        """
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

    def callback(self, event: TextEvent):
        """
        Hook called on a document's Y text data type event.

        Arguments:
            event: event emitted by a change in the document's Y text data type.
        """
        self.parse(event)

    def on_retain(self, range_offset: int):
        """
        Hook called on a retain actio in a document's Y text data type event.

        No further actions are taken.

        Arguments:
            range_offset: start index of the retain action.
        """
        pass

    def on_insert(self, range_offset: int, insert_value: str):
        """
        Hook called on an insert action in a document's Y text data type event.

        It puts edit metrics as tuples into the internal edits queue and updates the syntax tree.

        Arguments:
            range_offset: start index of insertion.
            insert_value: string to insert.
        """
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

    def on_delete(self, range_offset: int, range_length: int):
        """
        Hook called on an insert action in a document's Y text data type event.

        It puts edit metrics as tuples into the internal edits queue and updates the syntax tree.

        Arguments:
            range_offset: start index of deletion.
            range_length: length of the text slice to delete.
        """
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
        """
        Implement the asynchronous iterator protocol.
        """
        return self

    async def __anext__(self) -> tuple[int, int, bytes]:
        """
        Return an edit on the next asynchronous iterator step.

        Returns:
            a tuple (itop, ibot, btext) holding the start `itop` and end `ibot` indices as well as the UTF-8 encoded text to be inserted at `itop`.
        """
        return await self.edits.get()


class YTextArea(TextArea):
    """
    Widget for displaying and manipulating text synchronized in realtime.
    """

    document: YDocument
    """Instance of the document object."""

    wrapped_document: WrappedDocument
    """Instance of a wrapper class providing wrapping functionality."""

    navigator: DocumentNavigator
    """Instance of a navigator object responsible for proper cursor placement."""

    btext: bytes
    """UTF-8 encoded text."""

    def __init__(
        self, ytext: Text, *args: tuple, language: None | str = None, **kwargs: dict
    ):
        """
        Arguments:
            ytext: Y text data type holding the text.
            language: syntax language the text is written in.
            args: positional arguments passed to [`TextArea`][textual.widgets.TextArea].
            kwargs: keyword arguments passed to [`TextArea`][textual.widgets.TextArea].
        """
        super().__init__(str(ytext), *args, **kwargs)
        self.document = YDocument(ytext, language)
        self.wrapped_document = WrappedDocument(self.document)
        self.navigator = DocumentNavigator(self.wrapped_document)
        self.update_btext()

    def on_mount(self):
        """
        Hook called on mounting.

        This starts a tasks waiting for edits and updating the widget's visual appearance.
        """
        self.run_worker(self.perform_edits())

    def update_btext(self):
        """
        Reference the UTF-8 encoded text in an own class attribute.

        This makes it possible to calculate metrics before and after a new edit.
        """
        self.btext = self.document.btext

    async def perform_edits(self):
        """
        Task waiting for edits and perform further steps.
        """
        async for itop, ibot, btext in self.document:
            self.edit(itop, ibot, btext)

    def edit(self, itop: int, ibot: int, btext: bytes):
        """
        Update the widget's visual appearance from an edit's metrics.

        Arguments:
            itop: start index of the edit.
            ibot: end index of the edit.
            btext: inserted UTF-8 encoded text.
        """
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

    def _replace_via_keyboard(
        self, insert: str, start: tuple[int, int], end: tuple[int, int]
    ):
        """
        Perform a replacement only when the text area is not read-only.

        Arguments:
            insert: the text to be inserted at `start`.
            start: a tuple of row and column coordinates where the replaced text starts.
            end: a tuple of row and column coordinates where the replaced text ends.
        """
        if self.read_only:
            return None
        return self.replace(start, end, insert)

    def _delete_via_keyboard(self, start: tuple[int, int], end: tuple[int, int]):
        """
        Perform a deletion when the text area is not read-only.

        Arguments:
            start: a tuple of row and column coordinates where the deleted text starts.
            end: a tuple of row and column coordinates where the deleted text ends.
        """
        if self.read_only:
            return None
        return self.delete(start, end)

    def replace(self, start: tuple[int, int], end: tuple[int, int], text: str):
        """
        Replace a specified range in the text with another text.

        Arguments:
            start: a tuple of row and column coordinates where the replaced text starts.
            end: a tuple of row and column coordinates where the replaced text ends.
            text: the text to be inserted at `start`.
        """
        self.document.replace_range(start, end, text)

    def delete(self, start: tuple[int, int], end: tuple[int, int]):
        """
        Delete a specified range in the text.

        Arguments:
            start: a tuple of row and column coordinates where the to be deleted text starts.
            end: a tuple of row and column coordinates where the to be deleted text ends.
        """
        self.document.replace_range(start, end, "")

    def insert(self, text: str, location: tuple[int, int] = None):
        """
        Insert text at a specified location.

        Arguments:
            text: the text to be inserted.
            location: a tuple of row and column coordinates where the insertion starts.
        """
        if location is None:
            location = self.cursor_location()
        self.document.replace_range(location, location, text)

    def clear(self):
        """
        Clear the document, i.e. delete all text.
        """
        self.delete(self.document.start, self.document.end)

    def render_line(self, y: int) -> Strip:
        """
        Render a line of content after updating the wrapped text.

        Arguments:
            y: row index of the line to be rendered.

        Returns:
            the rendered line.
        """
        # update the cache of wrapped lines
        #
        # TODO: Why is this not done automatically?
        #       Probably we need to update the wrapped lines cache elsewhere.
        self.wrapped_document.wrap(self.size.width)
        return super().render_line(y)
