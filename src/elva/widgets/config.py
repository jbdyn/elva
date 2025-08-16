from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widgets import Static


class Key(Static):
    pass


class Value(Static):
    pass


class ConfigView(VerticalScroll):
    BORDER_TITLE = "Configuration"

    DEFAULT_CSS = """
        ConfigView {
          layout: grid;
          grid-size: 2;
          grid-columns: auto 1fr;
          grid-gutter: 0 1;
          height: auto;
        }
        """

    config = reactive(tuple, recompose=True)

    def compose(self):
        for key, value in self.config:
            yield Key(str(key))

            if isinstance(value, list):
                value = "\n".join(str(v) for v in value)

            yield Value(str(value))
