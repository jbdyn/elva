import pytest

from elva.widgets.ytextarea.selection import Selection


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    (
        ((0, 0), (0, 0), ((0, 0), (0, 0))),
        ((0, 0), (0, 1), ((0, 0), (0, 1))),
        ((0, 1), (0, 0), ((0, 1), (0, 0))),
    ),
)
def test_start_end(start, end, expected):
    selection = Selection(start, end)

    # we can retrieve values via named attributes
    expected_start, expected_end = expected
    assert selection.start == expected_start
    assert selection.end == expected_end

    # we can unpack a selection
    start, end = selection
    assert start == expected_start
    assert end == expected_end


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    (
        ((0, 0), (0, 0), ((0, 0), (0, 0))),
        ((0, 0), (0, 1), ((0, 0), (0, 1))),
        ((0, 1), (0, 0), ((0, 0), (0, 1))),
        ((0, 1), (1, 0), ((0, 1), (1, 0))),
        ((1, 0), (0, 1), ((0, 1), (1, 0))),
    ),
)
def test_top_bottom(start, end, expected):
    selection = Selection(start, end)

    # we can retrieve values via named attributes
    expected_top, expected_bottom = expected
    assert selection.top == expected_top
    assert selection.bottom == expected_bottom


@pytest.mark.parametrize(
    ("start", "end", "obj", "expected"),
    (
        ((0, 0), (0, 0), Selection((0, 0), (0, 1)), False),
        ((0, 0), (0, 0), Selection((0, 1), (0, 0)), False),
        ((0, 0), (0, 0), Selection((0, 1), (0, 1)), False),
        ((0, 2), (0, 3), Selection((0, 0), (0, 1)), True),
        ((0, 1), (0, 3), Selection((0, 0), (0, 1)), False),
        ((0, 2), (0, 3), Selection((0, 0), (0, 1)), True),
    ),
)
def test_selection_gt(start, end, obj, expected):
    selection = Selection(start, end)

    out = selection > obj
    assert out == expected


@pytest.mark.parametrize(
    ("start", "end", "obj", "expected"),
    (
        ((0, 0), (0, 0), Selection((0, 0), (0, 1)), False),
        ((0, 0), (0, 0), Selection((0, 1), (0, 0)), False),
        ((0, 0), (0, 0), Selection((0, 1), (0, 1)), False),
        ((0, 2), (0, 3), Selection((0, 0), (0, 1)), True),
        ((0, 1), (0, 3), Selection((0, 0), (0, 1)), True),
        ((0, 2), (0, 3), Selection((0, 0), (0, 1)), True),
    ),
)
def test_selection_ge(start, end, obj, expected):
    selection = Selection(start, end)

    out = selection >= obj
    assert out == expected


@pytest.mark.parametrize(
    ("start", "end", "obj", "expected"),
    (
        ((0, 0), (0, 0), Selection((0, 0), (0, 1)), False),
        ((0, 0), (0, 0), Selection((0, 1), (0, 0)), False),
        ((0, 0), (0, 0), Selection((0, 1), (0, 1)), True),
        ((0, 2), (0, 3), Selection((0, 0), (0, 1)), False),
        ((0, 1), (0, 3), Selection((0, 0), (0, 1)), False),
        ((0, 2), (0, 3), Selection((0, 0), (0, 1)), False),
    ),
)
def test_selection_lt(start, end, obj, expected):
    selection = Selection(start, end)

    out = selection < obj
    assert out == expected


@pytest.mark.parametrize(
    ("start", "end", "obj", "expected"),
    (
        ((0, 0), (0, 0), Selection((0, 0), (0, 1)), True),
        ((0, 0), (0, 0), Selection((0, 1), (0, 0)), True),
        ((0, 0), (0, 0), Selection((0, 1), (0, 1)), True),
        ((0, 2), (0, 3), Selection((0, 0), (0, 1)), False),
        ((0, 1), (0, 3), Selection((0, 0), (0, 1)), False),
        ((0, 2), (0, 3), Selection((0, 0), (0, 1)), False),
    ),
)
def test_selection_le(start, end, obj, expected):
    selection = Selection(start, end)

    out = selection <= obj
    assert out == expected


@pytest.mark.parametrize(
    ("start", "end", "obj", "expected"),
    (
        ((0, 1), (0, 0), (0, 1), False),
        ((0, 0), (0, 0), Selection((0, 0), (0, 0)), True),
        ((0, 0), (0, 0), Selection((0, 1), (0, 0)), False),
        ((0, 0), (0, 1), Selection((0, 0), (0, 1)), True),
        ((0, 0), (0, 1), Selection((0, 1), (0, 0)), False),
        ((0, 1), (0, 0), Selection((0, 0), (0, 1)), False),
        ((0, 1), (0, 0), Selection((0, 1), (0, 0)), True),
    ),
)
def test_selection_eq(start, end, obj, expected):
    selection = Selection(start, end)

    out = selection == obj
    assert out == expected


@pytest.mark.parametrize(
    ("start", "end", "obj", "expected"),
    (
        ((0, 1), (0, 0), (0, 1), True),
        ((0, 0), (0, 0), Selection((0, 0), (0, 0)), False),
        ((0, 0), (0, 0), Selection((0, 1), (0, 0)), True),
        ((0, 0), (0, 1), Selection((0, 0), (0, 1)), False),
        ((0, 0), (0, 1), Selection((0, 1), (0, 0)), True),
        ((0, 1), (0, 0), Selection((0, 0), (0, 1)), True),
        ((0, 1), (0, 0), Selection((0, 1), (0, 0)), False),
    ),
)
def test_selection_ne(start, end, obj, expected):
    selection = Selection(start, end)

    out = selection != obj
    assert out == expected


@pytest.mark.parametrize(
    ("start", "end", "obj", "expected"),
    (
        ((0, 0), (0, 0), (0, 0), True),
        ((0, 1), (0, 0), (0, 0), True),
        ((0, 0), (0, 1), (0, 0), True),
        ((0, 0), (0, 2), (0, 1), True),
        ((0, 0), (0, 2), (0, 2), True),
        ((0, 0), (0, 1), (0, 2), False),
        ((0, 1), (0, 2), (0, 0), False),
        ((0, 1), (0, 3), (0, 2), True),
        ((0, 1), (1, 0), (0, 2), True),
        ((1, 0), (0, 1), (0, 2), True),
        ((1, 0), (0, 2), (0, 1), False),
    ),
)
def test_selection_contains_tuple(start, end, obj, expected):
    selection = Selection(start, end)
    out = obj in selection
    assert out == expected


@pytest.mark.parametrize(
    ("start", "end", "obj", "expected"),
    (
        ((0, 0), (0, 0), Selection((0, 0), (0, 0)), True),
        ((0, 0), (0, 0), Selection((0, 0), (0, 1)), False),
        ((0, 1), (0, 0), Selection((0, 0), (0, 0)), True),
        ((0, 0), (0, 1), Selection((0, 0), (0, 0)), True),
        ((0, 1), (0, 0), Selection((0, 0), (0, 1)), True),
        ((0, 1), (0, 0), Selection((0, 1), (0, 0)), True),
        ((0, 0), (0, 1), Selection((0, 0), (0, 1)), True),
        ((0, 0), (0, 1), Selection((0, 1), (0, 0)), True),
        ((0, 1), (0, 0), Selection((0, 0), (0, 2)), False),
        ((0, 1), (0, 0), Selection((0, 2), (0, 0)), False),
        ((0, 0), (0, 1), Selection((0, 0), (0, 2)), False),
        ((0, 0), (0, 1), Selection((0, 2), (0, 0)), False),
        ((1, 0), (2, 0), Selection((1, 2), (1, 3)), True),
        ((1, 0), (2, 0), Selection((1, 2), (3, 0)), False),
        ((1, 0), (2, 0), Selection((0, 2), (1, 3)), False),
    ),
)
def test_selection_contains_selection(start, end, obj, expected):
    selection = Selection(start, end)
    out = obj in selection
    assert out == expected


@pytest.mark.parametrize(
    "unsupported",
    (
        int(),
        str(),
        bytes(),
        bytearray(),
        dict(),
    ),
)
def test_selection_raises_typeerror(unsupported):
    with pytest.raises(TypeError):
        selection = Selection()
        unsupported in selection
