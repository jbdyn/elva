import pytest

# from textual.widgets.text_area import Document
from elva.document import YDocument as Document
from pycrdt import Doc, Text

TEXT = """I must not fear.
Fear is the mind-killer."""

TEXT_NEWLINE = TEXT + "\n"
TEXT_WINDOWS = TEXT.replace("\n", "\r\n")
TEXT_WINDOWS_NEWLINE = TEXT_NEWLINE.replace("\n", "\r\n")


def get_text(text):
    doc = Doc()
    doc["text"] = text = Text(text)
    return text


@pytest.mark.parametrize(
    "text", [TEXT, TEXT_NEWLINE, TEXT_WINDOWS, TEXT_WINDOWS_NEWLINE]
)
def test_text(text):
    """The text we put in is the text we get out."""
    ytext = get_text(text)
    document = Document(ytext)
    assert document.text == text


def test_lines_newline_eof():
    text = get_text(TEXT_NEWLINE)
    document = Document(text)
    assert document.lines == ["I must not fear.", "Fear is the mind-killer.", ""]


def test_lines_no_newline_eof():
    text = get_text(TEXT)
    document = Document(text)
    assert document.lines == [
        "I must not fear.",
        "Fear is the mind-killer.",
    ]


def test_lines_windows():
    text = get_text(TEXT_WINDOWS)
    document = Document(text)
    assert document.lines == ["I must not fear.", "Fear is the mind-killer."]


def test_lines_windows_newline():
    text = get_text(TEXT_WINDOWS_NEWLINE)
    document = Document(text)
    assert document.lines == ["I must not fear.", "Fear is the mind-killer.", ""]


def test_newline_unix():
    text = get_text(TEXT)
    document = Document(text)
    assert document.newline == "\n"


def test_newline_windows():
    text = get_text(TEXT_WINDOWS)
    document = Document(text)
    assert document.newline == "\r\n"


def test_get_selected_text_no_selection():
    text = get_text(TEXT)
    document = Document(text)
    selection = document.get_text_range((0, 0), (0, 0))
    assert selection == ""


def test_get_selected_text_single_line():
    text = get_text(TEXT_WINDOWS)
    document = Document(text)
    selection = document.get_text_range((0, 2), (0, 6))
    assert selection == "must"


def test_get_selected_text_multiple_lines_unix():
    text = get_text(TEXT)
    document = Document(text)
    selection = document.get_text_range((0, 2), (1, 2))
    assert selection == "must not fear.\nFe"


def test_get_selected_text_multiple_lines_windows():
    text = get_text(TEXT_WINDOWS)
    document = Document(text)
    selection = document.get_text_range((0, 2), (1, 2))
    assert selection == "must not fear.\r\nFe"


def test_get_selected_text_including_final_newline_unix():
    text = get_text(TEXT_NEWLINE)
    document = Document(text)
    selection = document.get_text_range((0, 0), (2, 0))
    assert selection == TEXT_NEWLINE


def test_get_selected_text_including_final_newline_windows():
    text = get_text(TEXT_WINDOWS_NEWLINE)
    document = Document(text)
    selection = document.get_text_range((0, 0), (2, 0))
    assert selection == TEXT_WINDOWS_NEWLINE


def test_get_selected_text_no_newline_at_end_of_file():
    text = get_text(TEXT)
    document = Document(text)
    selection = document.get_text_range((0, 0), (2, 0))
    assert selection == TEXT


def test_get_selected_text_no_newline_at_end_of_file_windows():
    text = get_text(TEXT_WINDOWS)
    document = Document(text)
    selection = document.get_text_range((0, 0), (2, 0))
    assert selection == TEXT_WINDOWS


@pytest.mark.parametrize(
    "text", [TEXT, TEXT_NEWLINE, TEXT_WINDOWS, TEXT_WINDOWS_NEWLINE]
)
def test_index_from_location(text):
    ytext = get_text(text)
    document = Document(ytext)
    lines = text.split(document.newline)
    assert document.get_index_from_location((0, 0)) == 0
    assert document.get_index_from_location((0, len(lines[0]))) == len(lines[0])
    assert document.get_index_from_location((1, 0)) == len(lines[0]) + len(
        document.newline
    )
    assert document.get_index_from_location((len(lines) - 1, len(lines[-1]))) == len(
        text
    )


@pytest.mark.parametrize(
    "text", [TEXT, TEXT_NEWLINE, TEXT_WINDOWS, TEXT_WINDOWS_NEWLINE]
)
def test_location_from_index(text):
    ytext = get_text(text)
    document = Document(ytext)
    lines = text.split(document.newline)
    assert document.get_location_from_index(0) == (0, 0)
    assert document.get_location_from_index(len(lines[0])) == (0, len(lines[0]))
    if len(document.newline) > 1:
        assert document.get_location_from_index(len(lines[0]) + 1) == (
            0,
            len(lines[0]) + 1,
        )
    assert document.get_location_from_index(len(lines[0]) + len(document.newline)) == (
        1,
        0,
    )
    assert document.get_location_from_index(len(text)) == (
        len(lines) - 1,
        len(lines[-1]),
    )


@pytest.mark.parametrize(
    "text", [TEXT, TEXT_NEWLINE, TEXT_WINDOWS, TEXT_WINDOWS_NEWLINE]
)
def test_document_end(text):
    """The location is always what we expect."""
    ytext = get_text(text)
    document = Document(ytext)
    expected_line_number = (
        len(text.splitlines()) if text.endswith("\n") else len(text.splitlines()) - 1
    )
    expected_pos = 0 if text.endswith("\n") else (len(text.splitlines()[-1]))
    assert document.end == (expected_line_number, expected_pos)
