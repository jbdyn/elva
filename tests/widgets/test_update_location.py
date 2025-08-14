import pytest

import elva.widgets.ytextarea as _ytextarea


@pytest.mark.parametrize(
    ("location", "delete", "insert", "target", "expected"),
    (
        #
        # LOCATION BEFORE DELETE SELECTION
        #
        # `expected` is always equal to `location`
        (
            (0, 0),
            _ytextarea.Selection((0, 1), (0, 3)),
            _ytextarea.Selection((0, 0), (0, 0)),
            (0, 0),
            (0, 0),
        ),
        (
            (0, 0),
            _ytextarea.Selection((0, 1), (0, 3)),
            _ytextarea.Selection((0, 0), (0, 0)),
            (10, 0),
            (0, 0),
        ),
        (
            (0, 0),
            _ytextarea.Selection((0, 1), (0, 3)),
            _ytextarea.Selection((0, 1), (0, 2)),
            (0, 0),
            (0, 0),
        ),
        (
            (0, 0),
            _ytextarea.Selection((0, 1), (0, 3)),
            _ytextarea.Selection((0, 1), (0, 2)),
            (10, 0),
            (0, 0),
        ),
        #
        # LOCATION IN DELETE SELECTION
        #
        # `expected` is always equal to `target`
        (
            (0, 0),
            _ytextarea.Selection((0, 0), (0, 0)),
            _ytextarea.Selection((0, 0), (0, 0)),
            (0, 0),
            (0, 0),
        ),
        (
            (0, 0),
            _ytextarea.Selection((0, 0), (0, 0)),
            _ytextarea.Selection((0, 0), (0, 0)),
            (10, 0),
            (10, 0),
        ),
        (
            (0, 0),
            _ytextarea.Selection((0, 0), (0, 0)),
            _ytextarea.Selection((0, 0), (0, 5)),
            (0, 0),
            (0, 0),
        ),
        (
            (0, 0),
            _ytextarea.Selection((0, 0), (0, 0)),
            _ytextarea.Selection((0, 0), (0, 5)),
            (0, 5),
            (0, 5),
        ),
        (
            (0, 0),
            _ytextarea.Selection((0, 0), (0, 3)),
            _ytextarea.Selection((0, 0), (0, 5)),
            (0, 0),
            (0, 0),
        ),
        (
            (0, 0),
            _ytextarea.Selection((0, 0), (0, 3)),
            _ytextarea.Selection((0, 0), (0, 5)),
            (0, 5),
            (0, 5),
        ),
        #
        # LOCATION AFTER DELETE SELECTION
        #
        # location is shifted depending on the difference
        # in lengths of insert and delete selection
        #
        # edit in the same row solely
        (
            (0, 4),
            _ytextarea.Selection((0, 0), (0, 3)),
            _ytextarea.Selection((0, 0), (0, 5)),
            (0, 0),
            (0, 6),
        ),
        # changing target has no effect
        (
            (0, 4),
            _ytextarea.Selection((0, 0), (0, 3)),
            _ytextarea.Selection((0, 0), (0, 5)),
            (10, 0),
            (0, 6),
        ),
        # edit not reaching the current row,
        # only row is shifted, column not
        (
            (2, 8),
            _ytextarea.Selection((0, 0), (0, 3)),
            _ytextarea.Selection((0, 0), (1, 20)),
            (0, 0),
            (3, 8),
        ),
        # changing target has no effect
        (
            (2, 8),
            _ytextarea.Selection((0, 0), (0, 3)),
            _ytextarea.Selection((0, 0), (1, 20)),
            (10, 0),
            (3, 8),
        ),
        # edit surpassing the current row,
        # row and column are shifted
        (
            (0, 9),
            _ytextarea.Selection((0, 0), (0, 3)),
            _ytextarea.Selection((0, 0), (5, 1)),
            (0, 0),
            (5, 7),
        ),
        # changing target has no effect
        (
            (0, 9),
            _ytextarea.Selection((0, 0), (0, 3)),
            _ytextarea.Selection((0, 0), (5, 1)),
            (10, 0),
            (5, 7),
        ),
    ),
)
def test_update_location(location, delete, insert, target, expected):
    location = _ytextarea.update_location(location, delete, insert, target)

    assert location == expected
