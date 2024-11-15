from textual.containers import Grid
from textual.widgets import Button

from elva.component import Component


class StatusBar(Grid):
    pass


class FeatureStatus(Button):
    def __init__(self, params, *args, config=None, rename=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.params = params
        self.rename = rename
        self.config = self.trim(config)

    def trim(self, config):
        if config is not None:
            trimmed = dict((param, config.get(param)) for param in self.params)

            if self.rename is not None:
                for from_param, to_param in self.rename.items():
                    trimmed[to_param] = trimmed.pop(from_param)

            return trimmed

    def update(self, config):
        trimmed = self.trim(config)
        changed = trimmed != self.config

        self.config = trimmed

        if changed:
            self.apply()

    @property
    def is_ready(self): ...

    def apply(self): ...

    def on_mount(self):
        self.apply()


class ComponentStatus(FeatureStatus):
    component: Component

    def __init__(self, yobject, params, *args, **kwargs):
        self.yobject = yobject
        super().__init__(params, *args, **kwargs)

    def apply(self):
        if self.is_ready:
            component = self.component(self.yobject, **self.config)
            self.run_worker(
                component.start(), name="component", exclusive=True, exit_on_error=False
            )
            self.control = component
        else:
            self.workers.cancel_node(self)

    def on_button_pressed(self, message):
        if self.variant in ["success", "warning"]:
            self.workers.cancel_node(self)
        else:
            self.apply()
