"""
Location manipulation.
"""

from .selection import Selection


def update_location(
    location: tuple, delete: Selection, insert: Selection, target: tuple
) -> tuple:
    """
    Move a given location with respect to deletion and insertion ranges of an edit.

    Arguments:
        location: tuple before the edit.
        delete: range which is deleted during the edit.
        insert: range which is inserted during the edit.
        target:
            returned location when `location` is within the deletion range,
            typically the start or the end of the insertion range.

    Returns:
        location after the edit.
    """
    # abbreviate for easier reading
    loc_ = location
    del_ = delete
    ins_ = insert

    if loc_ < del_:
        # `loc_` is not affected by the edit and thus does not change
        pass
    elif loc_ in del_:
        # `loc_` is within the deletion range and set to the `target`
        loc_ = target
    elif loc_ > del_:
        # `loc_` is shifted by the difference in length
        # between delete and insert operations
        shift = (ins_.end[0] - del_.end[0], ins_.end[1] - del_.end[1])

        # only shift columns when edit happened before the row `loc_` is also in
        if del_.end[0] < loc_[0]:
            shift = (shift[0], 0)

        loc_ = (loc_[0] + shift[0], loc_[1] + shift[1])

    return loc_
