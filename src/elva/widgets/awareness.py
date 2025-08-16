from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widgets import Static


class ClientView(Static):
    pass


class AwarenessView(VerticalScroll):
    BORDER_TITLE = "Clients"

    DEFAULT_CSS = """
        AwarenessView {
          * {
            padding: 0 0 1 0;
          }
        }
        """

    states = reactive(tuple, recompose=True)

    def compose(self):
        if self.states:
            state, *other_states = self.states
            yield self.get_client_view(state, local=True)

            for state in other_states:
                yield self.get_client_view(state)

    def get_client_view(self, state, local=False):
        client, data = state

        user = data.get("user")
        name = ""

        if isinstance(user, dict):
            name = user.get("name", name)

        if name:
            client = name

        add = " (me)" if local else ""
        return ClientView(f"∙ {client}{add}")
