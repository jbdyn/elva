"""
[`Textual`](https://textualize.textual.io) widgets for displaying a configuration parameter mapping.
"""

from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widgets import Static


class Key(Static):
    """
    Widget holding a configuration parameter's key.
    """

    pass


class Value(Static):
    """
    Widget holding a configuration parameter's value.
    """

    pass


class ConfigView(VerticalScroll):
    """
    Containers representing all configuration parameter key-value pairs.
    """

    BORDER_TITLE = "Configuration"
    """Default border title."""

    DEFAULT_CSS = """
        ConfigView {
          layout: grid;
          grid-size: 2;
          grid-columns: auto 1fr;
          grid-gutter: 0 1;
          height: auto;
        }
        """
    """Default CSS."""

    config = reactive(tuple, recompose=True)
    """
    Configuration parameters alongside their respective values.

    This attribute causes a recompose of this widget on being changed.
    """

    def compose(self):
        """
        Hook adding child widgets.
        """
        for key, value in self.config:
            yield Key(str(key))

            # don't rely on the string representation of list items,
            # get the string conversion individually instead
            if isinstance(value, list):
                value = "\n".join(str(v) for v in value)

            yield Value(str(value))
