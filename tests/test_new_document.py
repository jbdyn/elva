from elva.document import (
    get_binary_index_from_location,
    get_index_from_location,
    get_lines,
    get_location_from_binary_index,
    get_location_from_index,
)

TEXT = "foo\nbar\r\nbaz\r"
BTEXT = TEXT.encode()


def test_get_lines():
    lines = get_lines("")
    assert lines == [""]

    lines = get_lines(TEXT)
    assert lines == ["foo", "bar", "baz", ""]

    lines = get_lines(TEXT, keepends=True)
    assert lines == ["foo\n", "bar\r\n", "baz\r", ""]

    lines = get_lines(TEXT[:-1])
    assert lines == ["foo", "bar", "baz"]


def test_get_index_from_location():
    index = get_index_from_location("", (0, 0))
    assert index == 0

    index = get_index_from_location("\r\n\r\n", (1, 0))
    assert index == 2

    index = get_index_from_location("\r\n\r\n", (2, 0))
    assert index == 4

    index = get_index_from_location("", (0, 0))
    assert index == 0

    index = get_index_from_location(TEXT, (0, 0))
    assert index == 0

    index = get_index_from_location(TEXT, (0, 3))
    assert index == 3

    index = get_index_from_location(TEXT[:-1], (2, 3))
    assert index == 12

    index = get_index_from_location(TEXT, (1, 10))
    assert index in [7, 8]


def test_get_binary_index_from_location():
    index = get_binary_index_from_location(b"\n\n\n\n\n", (2, 0))
    assert index == 2


def test_get_location_from_index():
    location = get_location_from_index("", 0)
    assert location == (0, 0)

    location = get_location_from_index("", 10)
    assert location == (0, 0)

    location = get_location_from_index("\r\n\r\n", 2)
    assert location == (1, 0)

    location = get_location_from_index("\r\n\r\n", 3)
    assert location == (1, 0)

    location = get_location_from_index("\r\n\r\n", 4)
    assert location == (2, 0)

    location = get_location_from_index(TEXT, 0)
    assert location == (0, 0)

    location = get_location_from_index(TEXT, 1)
    assert location == (0, 1)

    location = get_location_from_index(TEXT, 3)
    assert location == (0, 3)

    location = get_location_from_index(TEXT, 4)
    assert location == (1, 0)

    location = get_location_from_index(TEXT, 7)
    assert location == (1, 3)

    location = get_location_from_index(TEXT, 8)
    assert location == (1, 3)

    location = get_location_from_index(TEXT[:-1], len(TEXT[:-1]))
    assert location == (2, 3)

    location = get_location_from_index(TEXT, len(TEXT))
    assert location == (3, 0)

    location = get_location_from_index(TEXT, 100)
    assert location == (3, 0)


def test_get_location_from_binary_index():
    location = get_location_from_binary_index(b"", 0)
    assert location == (0, 0)
