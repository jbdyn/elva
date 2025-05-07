"""
[`Textual`](https://textual.textualize.io/) widgets for building a status bar.
"""

from typing import Any

from pycrdt import Array, Doc, Map, Text
from textual.containers import Grid
from textual.message import Message
from textual.widgets import Button

from elva.component import Component


class StatusBar(Grid):
    """
    Main container of status widgets.
    """

    pass


class FeatureStatus(Button):
    """
    Button indicating the status of a feature.
    """

    params: list[str]
    """List of configuration parameters associated with this feature."""

    rename: None | dict[str, str]
    """Mapping of old parameter names to new parameter names."""

    config: None | dict[str, Any]
    """Mapping of configuration parameters to their values."""

    def __init__(
        self,
        params: list[str],
        *args: tuple,
        config: None | dict[str, Any] = None,
        rename: None | dict[str, str] = None,
        **kwargs: dict,
    ):
        """
        Arguments:
            params: list of configuration parameters associated with this feature.
            config: mapping of configuration parameters to their values.
            rename: mapping of old parameter names to new parameter names.
            args: positional arguments passed to [`Button`][textual.widgets.Button].
            kwargs: keyword arguments passed to [`Button`][textual.widgets.Button].
        """
        super().__init__(*args, **kwargs)
        self.params = params
        self.rename = rename
        self.config = self.trim(config)

    def trim(self, config: dict[str, Any]) -> dict[str, Any]:
        """
        Trim and rename a given config with respect to the feature's configuration parameters.

        Arguments:
            config: mapping of configuration parameters to their values.

        Returns:
            trimmed and renamed configuration parameter mapping.
        """
        if config is not None:
            trimmed = dict((param, config.get(param)) for param in self.params)

            if self.rename is not None:
                for from_param, to_param in self.rename.items():
                    trimmed[to_param] = trimmed.pop(from_param)

            return trimmed

    def update(self, config: dict[str, Any]):
        """
        Update the internal configuration parameter mapping.

        The given configuration gets trimmed, renamed and replaces the currently stored configuration if different.

        Arguments:
            config: mapping of configuration parameters to their values.
        """
        trimmed = self.trim(config)
        changed = trimmed != self.config

        self.config = trimmed

        if changed:
            self.apply()

    @property
    def is_ready(self) -> bool:
        """
        Flag whether the feature is ready or not.

        It is supposed to hold the logic for determining the current status of the feature.

        This property is defined as a no-op and supposed to be implemented in the inheriting class.

        Returns:
            `True` if the feature is ready, else `False`.
        """
        ...

    def apply(self):
        """
        Hook called on mounting the widget and on configuration update.

        It is supposed to hold the logic for a change in configuration parameters.

        This method is defined as a no-op and supposed to be implemented in the inheriting class.
        """
        ...

    def on_mount(self):
        """
        Hook called on mounting the widget.

        This method calls [`apply`][elva.widgets.status.FeatureStatus.apply].
        """
        self.apply()


class ComponentStatus(FeatureStatus):
    """
    Button indicating the status of a component.
    """

    component: Component
    """Instance of the component represented by this widget."""

    control: Component
    """Alias for [`component`][elva.widgets.status.ComponentStatus.component]."""

    yobject: Doc | Text | Array | Map
    """Instance of the Y object being used by the internal component."""

    def __init__(
        self,
        yobject: Doc | Text | Array | Map,
        params: list[str],
        *args: tuple,
        **kwargs: dict,
    ):
        """
        Arguments:
            yobject: instance of the Y object being used by the internal component.
            params: list of configuration parameters associated with this component.
            args: positional arguments passed to [`FeatureStatus`][elva.widgets.status.FeatureStatus].
            kwargs: keyword arguments passed to [`FeatureStatus`][elva.widgets.status.FeatureStatus].
        """
        self.yobject = yobject
        super().__init__(params, *args, **kwargs)

    def apply(self):
        """
        Hook called on mounting the widget and on configuration update.

        This method starts the component if ready, else the component gets cancelled.
        """
        if self.is_ready:
            component = self.component(self.yobject, **self.config)
            self.run_worker(
                component.start(), name="component", exclusive=True, exit_on_error=False
            )
            self.control = component
        else:
            self.workers.cancel_node(self)

    def on_button_pressed(self, message: Message):
        """
        Hook called on a pressed button event.

        Basically, it toggles to component's running state.

        Arguments:
            message: the message holding information about the pressed button event.
        """
        if self.variant in ["success", "warning"]:
            self.workers.cancel_node(self)
        else:
            self.apply()
