import click
from textual.app import App
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


class ConfigScreen(ModalScreen):
    def __init__(self, config, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config
        self.inputs = dict()

    def compose(self):
        with Grid(classes="form"):
            for k, v in self.config.items():
                label = Label(k)
                input = Input(v)
                self.inputs[k] = input
                yield label
                yield input

        yield Button("Confirm")

    def get_inputs(self):
        inputs = dict()
        for k, i in self.inputs.items():
            inputs[k] = i.value
        return inputs

    def on_input_submitted(self):
        self.update_config_and_close()

    def on_button_pressed(self):
        self.update_config_and_close()

    def update_config_and_close(self):
        self.config.update(self.get_inputs())
        self.dismiss(self.config)


class TestApp(App):
    CSS = """
    #configcreen {
      width: 50%;
      height: 50%;
    }
    .form {
      grid-gutter: 1;
      grid-size: 2;
      height: auto;
    }
    Input {
      background: #000000;
      border: none;
      padding: 0;
      height: auto;
    }
    Button {
      align: center middle;
    }
    """

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.config_screen = ConfigScreen(config, id="configcreen")
        self.install_screen(self.config_screen, "config_screen")

    def on_mount(self):
        self.run_worker(self.test_screen())

    async def test_screen(self):
        await self.push_screen(
            "config_screen", self.update_config, wait_for_dismiss=True
        )

    def update_config(self, config):
        self.config = config
        self.config_screen.config = config
        self.mount(Label(str(config)))


if __name__ == "__main__":
    config = dict(foo="1", bar="2", baz="3")
    app = TestApp(config)
    app.run()
