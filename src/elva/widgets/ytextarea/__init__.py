"""
[`Textual`](https://textualize.textual.io)'s [`TextArea`][textual.widgets.TextArea] widget for Y Text manipulation.
"""

from .location import update_location
from .selection import Selection
from .widget import YTextArea

__all__ = [
    Selection,
    update_location,
    YTextArea,
]
