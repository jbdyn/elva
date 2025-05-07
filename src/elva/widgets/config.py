"""
Configuration panel widgets for [`Textual`](https://textual.textualize.io/) apps.
"""

import io
import sys
from pathlib import Path
from typing import Any

import qrcode
from pyperclip import copy as copy_to_clipboard
from textual.containers import Container, Grid, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.suggester import Suggester
from textual.validation import ValidationResult, Validator
from textual.widget import Widget
from textual.widgets import (
    Button,
    Collapsible,
    Input,
    Label,
    RadioButton,
    RadioSet,
    Static,
    Switch,
)
from websockets import parse_uri

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class ConfigPanel(Container):
    """
    Container for [`ConfigView`][elva.widgets.config.ConfigView] widgets.
    """

    class Applied(Message):
        """
        Message object holding configuration change information.
        """

        last: dict
        """Previous configuration mapping."""

        config: dict
        """Current configuration mapping."""

        changed: dict
        """Mapping of changed configuration parameters."""

        def __init__(self, last: dict, config: dict, changed: dict):
            """
            Arguments:
                last: previous configuration mapping.
                config: current configuration mapping.
                changed: mapping of changed configuration parameters.
            """
            super().__init__()
            self.last = last
            self.config = config
            self.changed = changed

    def __init__(self, config: dict, applied: bool = False, label: str = None):
        """
        Arguments:
            config: configuration parameter mapping to apply to write to the panel.
            applied: if `False`, treat all config view values as changed.
            label: label string for the panel itself to be displayed at the top.
        """
        super().__init__()
        self.config = config
        self.applied = applied
        self.label = label

    @property
    def state(self):
        """
        Current configuration parameters.
        """
        return dict((c.name, c.value) for c in self.config)

    @property
    def last(self):
        """
        Previous configuration parameters.
        """
        return dict((c.name, c.last) for c in self.config)

    @property
    def changed(self):
        """
        Changed configuration parameters.
        """
        if self.applied:
            return set(c.name for c in self.config if c.changed)
        else:
            return set(c.name for c in self.config)

    def compose(self):
        """
        Hook arranging config view widgets.
        """
        if self.label:
            yield Label(self.label)
        with Grid():
            with VerticalScroll():
                for c in self.config:
                    yield c
            with Grid():
                yield Button("Apply", id="apply")
                yield Button("Reset", id="reset")

    def apply(self):
        """
        Store the current value also as last value.
        """
        for c in self.config:
            c.apply()
        self.applied = True

    def reset(self):
        """
        Reset the current value to the last value.
        """
        for c in self.config:
            c.reset()

    def post_applied_config(self):
        """Send an [`Applied`][elva.widgets.config.ConfigPanel.Applied] message."""
        self.post_message(self.Applied(self.last, self.state, self.changed))
        self.apply()

    def on_button_pressed(self, message: Message):
        """
        Hook called on a pressed button.

        Either posts an [`Applied`][elva.widgets.config.ConfigPanel.Applied] message or resets the config views.

        Arguments:
            message: message object from the pressed button event.
        """
        match message.button.id:
            case "apply":
                self.post_applied_config()
            case "reset":
                self.reset()

    def decode_content(self, content: str) -> dict:
        """
        Try to decode content according to TOML syntax.

        Arguments:
            content: TOML data string to be parsed.

        Returns:
            parsed configuration mapping.
        """
        try:
            config = tomllib.loads(content)
        # tomli exceptions may change in the future according to its docs
        except Exception:
            config = None
        return config

    def on_paste(self, message: Message):
        """
        Hook called on a paste event.

        The pasted content is assumed to be TOML syntax and tried to be parsed.
        On success, the config views get updated if the corresponding keys have been pasted.

        Arguments:
            message: message object from the paste event.
        """
        config = self.decode_content(message.text)
        if config:
            for c in self.config:
                value = config.get(c.name)
                if value is not None:
                    c.value = value


class ConfigView(Container):
    """
    Wrapper Container around user-facing input widgets.

    It allows consistent styling via TCSS classes.
    """

    last: Any
    """Previous value of the configuration parameter."""

    hover: bool = reactive(False)
    """Flag whether the mouse pointer is hovering over this container."""

    focus_within: bool = reactive(False)
    """Flag whether the child widgets have focus."""

    class Changed(Message):
        """
        Message object posted on change events.
        """

        name: str
        """Key of the configuration parameter."""

        value: Any
        """Value of the configuration parameter."""

        def __init__(self, name: str, value: Any):
            """
            Arguments:
                name: key of the configuration parameter.
                value: value of the configuration parameter.
            """
            super().__init__()
            self.name = name
            self.value = value

    class Saved(Message):
        """
        Message object posted on save events.
        """

        name: str
        """Key of the configuration parameter."""

        value: Any
        """Value of the configuration parameter."""

        def __init__(self, name: str, value: Any):
            """
            Arguments:
                name: key of the configuration parameter.
                value: value of the configuration parameter.
            """
            super().__init__()
            self.name = name
            self.value = value

    def __init__(self, widget: Widget):
        """
        Arguments:
            widget: internal user-facing input widget.
        """
        super().__init__()
        self.widget = widget

    def compose(self):
        """
        Hook arranging child widgets.
        """
        yield Label(self.name or "")
        yield self.widget

    def on_mount(self):
        """
        Hook applying the configuration parameters when mounted.
        """
        self.apply()

    def apply(self):
        """
        Set the last value to the current value.
        """
        self.last = self.value

    def reset(self):
        """
        Set the current value to the last value.
        """
        self.value = self.last

    @property
    def changed(self) -> bool:
        """
        Flag whether the configuration value has changed.
        """
        return self.last != self.value

    @property
    def name(self) -> str:
        """
        Key of the configuration parameter.
        """
        return self.widget.name

    @property
    def value(self) -> Any:
        """
        Value of the configuration parameter.
        """
        return self.widget.value

    @value.setter
    def value(self, new: Any):
        """
        Update the inner widget's value.

        Arguments:
            new: new value to set in the input widget.
        """
        self.widget.value = new

    def toggle_button_visibility(self, state: bool):
        """
        Manage the `invisible` TCSS class on [`Button`][textual.widgets.Button] widgets.

        Arguments:
            state: if `True`, remove the `invisible` TCSS class from button widgets, else add it to them.
        """
        if state:
            self.query(Button).remove_class("invisible")
        else:
            self.query(Button).add_class("invisible")

    def on_enter(self, message: Message):
        """
        Hook called on pressed `Enter` key.

        This sets the [`hover`][elva.widgets.config.ConfigView.hover] flag to `True`.

        Arguments:
            message: message object posted on the pressed `Enter` key event.
        """
        self.hover = True

    def on_leave(self, message: Message):
        """
        Hook called on the mouse pointer leaving the widget's bounds.

        This sets the [`hover`][elva.widgets.config.ConfigView.hover] flag to `False` only if the mouse has really left the own boundaries and the inner input widget is not focused.

        Arguments:
            message: message object posted on the pressed `Enter` key event.
        """
        if not self.is_mouse_over and not self.focus_within:
            self.hover = False

    def watch_hover(self, hover: bool):
        """
        Hook called on hover changed.

        This toggles the button visibility accordingly.

        Arguments:
            hover: current value of [`hover`][elva.widgets.config.ConfigView.hover].
        """
        self.toggle_button_visibility(hover)

    def on_descendant_focus(self, message: Message):
        """
        Hook called on child widgets gaining focus.

        This sets the [`focus_within`][elva.widgets.config.ConfigView.focus_within] flag to `True`.

        Arguments:
           message: message object posted on focus gain event in child widgets.
        """
        self.focus_within = True

    def on_descendant_blur(self, message: Message):
        """
        Hook called on child widgets loosing focus.

        This sets the [`focus_within`][elva.widgets.config.ConfigView.focus_within] flag to `False`.

        Arguments:
           message: message object posted on focus loss event in child widgets.
        """
        if not any(node.has_focus for node in self.query()):
            self.focus_within = False

    def watch_focus_within(self, focus: bool):
        """
        Hook called on focus changed in child widgets.

        This toggles the button visibility accordingly.

        Arguments:
            focus: current value of [`focus_within`][elva.widgets.config.ConfigView.focus_within].
        """
        self.toggle_button_visibility(focus)


class ConfigInput(Input):
    """
    Input widget being able to let paste event messages bubble.
    """

    def _on_paste(self, message: Message):
        """
        Hook called on a paste event.

        This allows the `message` object to bubble up if the pasted content is valid TOML syntax, but does nothing else with it.

        Arguments:
            message: message object posted in a paste event.
        """
        try:
            tomllib.loads(message.text)
        except Exception:
            pass
        else:
            # prevent Input._on_paste() being called,
            # so the Paste message can bubble up to ConfigPanel.on_paste()
            message.prevent_default()


class RadioSelect(Container):
    """
    List of options with radio buttons.
    """

    names: list[str]
    """List of names representing the values."""

    values: list[Any]
    """List of values at choice."""

    options: dict[str, Any]
    """Mapping of values to their corresponding name."""

    buttons: dict[str, RadioButton]
    """Mapping of [`RadioButton`][textual.widgets.RadioButton] instances to the values' names."""

    radio_set: RadioSet
    """Instance of the inner [`RadioSet`][textual.widgets.RadioSet] widget."""

    def __init__(
        self,
        options: list[tuple[str, Any]],
        *args: tuple,
        value: None | Any = None,
        **kwargs: dict,
    ):
        """
        Arguments:
            options: name-value-tuples holding values alongside their displayable names.
            value: current value to select upfront.
            args: positional arguments passed to the [`Container`][textual.containers.Container] class.
            kwargs: keyword arguments passed to the [`Container`][textual.containers.Container] class.
        """
        super().__init__(*args, **kwargs)
        self.names, self.values = list(zip(*options))
        if value is None:
            value = self.values[0]
        elif value not in self.values:
            raise AttributeError(f"value '{value}' is not in values {self.values}")

        self.buttons = dict(
            (n, RadioButton(n, value=(v == value), name=n)) for n, v in options
        )
        self.options = dict(options)

        self.radio_set = RadioSet()

    @classmethod
    def from_values(
        cls, options: list[Any], *args: tuple, value: None | Any = None, **kwargs: dict
    ):
        """
        Create a new instance from a list of options.

        Arguments:
            options: list of values at choice with their string representation as displayed names.
            value: current value to select upfront.
            args: positional arguments passed to the [`Container`][textual.containers.Container] class.
            kwargs: keyword arguments passed to the [`Container`][textual.containers.Container] class.
        """
        options = [(str(option), option) for option in options]

        return cls(options, *args, value=value, **kwargs)

    def compose(self):
        """
        Hook arranging child widgets.
        """
        with self.radio_set:
            for button in self.buttons.values():
                yield button

    @property
    def value(self) -> Any:
        """
        Value of currently active, i.e. selected, radio button.
        """
        return self.options[self.radio_set.pressed_button.name]

    @value.setter
    def value(self, new: Any):
        """
        Update the currently active, i.e. selected, radio button.

        Arguments:
            new: value to be currently active.
        """
        name = self.names[self.values.index(new)]
        self.buttons[name].value = True

    def on_click(self, message: Message):
        """
        Hook called on mouse click event.

        This sets the focus to the currently active radio button.

        Arguments:
            message: message object posted in a mouse click event.
        """
        self.radio_set.pressed_button.focus()


class RadioSelectView(ConfigView):
    """
    Configuration view wrapper around a [`RadioSelect`][elva.widgets.config.RadioSelect] widget.
    """

    def __init__(self, *args: tuple, **kwargs: dict):
        """
        Arguments:
            args: positional arguments passed to [`RadioSelect`][elva.widgets.config.RadioSelect].
            kwargs: keyword arguments passed to [`RadioSelect`][elva.widgets.config.RadioSelect].

        """
        widget = RadioSelect(*args, **kwargs)
        super().__init__(widget)

    def compose(self):
        """
        Hook arranging child widgets.
        """
        with Grid():
            yield Label(self.name or "")
            yield Button("S", id=f"save-{self.name}")
            yield self.widget

    def on_button_pressed(self, message: Message):
        """
        Hook called on a button pressed event from the child widgets.

        This posts then a [`Saved`][elva.widgets.config.ConfigView.Saved] message.

        Arguments:
            message: message object posted on a button pressed event.
        """
        self.post_message(self.Saved(self.name, self.value))

    def on_click(self, message: Message):
        """
        Hook called on a mouse click event.

        This sets the focus to the inner radio set widget.

        Arguments:
            message: message object posted on a mouse click event.
        """
        self.widget.radio_set.focus()

    def on_radio_set_changed(self, message: Message):
        """
        Hook called when the radio set changes.

        This posts then a [`Changed`][elva.widgets.config.ConfigView.Changed] message itself.

        Arguments:
            message: message object posted on a radio set changed event.
        """
        self.post_message(self.Changed(self.name, self.value))


class TextInputView(ConfigView):
    """
    Configuration view wrapper around a [`ConfigInput`][elva.widgets.config.ConfigInput] widget for generic text input.
    """

    def __init__(self, *args: tuple, **kwargs: dict):
        """
        Arguments:
            args: positional arguments passed to [`ConfigInput`][elva.widgets.config.ConfigInput].
            kwargs: keyword arguments passed to [`ConfigInput`][elva.widgets.config.ConfigInput].
        """
        widget = ConfigInput(*args, **kwargs)
        super().__init__(widget)

    def compose(self):
        """
        Hook arranging child widgets.
        """
        with Grid():
            yield Label(self.name or "")
            with Grid():
                yield Button("X", id=f"cut-{self.name}")
                yield Button("C", id=f"copy-{self.name}")
                yield Button("S", id=f"save-{self.name}")
            yield self.widget

    def on_button_pressed(self, message: Message):
        """
        Hook called on a button pressed event from the child widgets.

        This either copies the current value to clipboard or posts a [`Changed`][elva.widgets.config.ConfigView.Saved] message.

        Arguments:
            message: message object posted on a button pressed event.
        """
        button_id = message.button.id
        cut_id = f"cut-{self.name}"
        copy_id = f"copy-{self.name}"
        save_id = f"save-{self.name}"

        if button_id == cut_id:
            copy_to_clipboard(self.value)
            self.widget.clear()
        elif button_id == copy_id:
            copy_to_clipboard(self.value)
        elif button_id == save_id:
            self.post_message(self.Saved(self.name, self.value))

    def on_input_changed(self, message: Message):
        """
        Hook called on an input change event.

        This posts then a [`Changed`][elva.widgets.config.ConfigView.Saved] message.

        Arguments:
            message: message object posted on an input change event.
        """
        self.post_message(self.Changed(self.name, self.value))


class URLInputView(TextInputView):
    """
    Configuration view wrapper around a [`ConfigInput`][elva.widgets.config.ConfigInput] widget for URLs.
    """

    def __init__(self, *args: tuple, **kwargs: dict):
        """
        Arguments:
            args: positional arguments passed to [`ConfigInput`][elva.widgets.config.ConfigInput].
            kwargs: keyword arguments passed to [`ConfigInput`][elva.widgets.config.ConfigInput].
        """
        super().__init__(*args, **kwargs)
        self.is_valid = True

    def on_input_changed(self, message: Message):
        """
        Hook called on an input change event.

        This posts then a [`Changed`][elva.widgets.config.ConfigView.Saved] message if no validation result is present, i.e. no [`Validator`][textual.validation.Validator] has been passed to the constructor, or the validation succeeded.
        Additionally, the TCSS class `invalid` is added or removed to the input widget depending on the validation result.

        Arguments:
            message: message object posted on an input change event.
        """
        validation_result = message.validation_result
        if validation_result is not None:
            if validation_result.is_valid:
                self.is_valid = True
                self.widget.remove_class("invalid")
                self.post_message(self.Changed(self.name, self.value))
            else:
                self.is_valid = False
                self.widget.add_class("invalid")
        else:
            self.post_message(self.Changed(self.name, self.value))

    @property
    def value(self):
        """
        Value of the input field if being a valid URL.
        """
        entry = self.widget.value
        return entry if entry and self.is_valid else None

    @value.setter
    def value(self, new: Any):
        """
        Update the currently displayed value in the input field.

        Arguments:
            new: new value to be shown.
        """
        self.widget.value = str(new) if new is not None else ""


class PathInputView(TextInputView):
    """
    Configuration view wrapper around a [`ConfigInput`][elva.widgets.config.ConfigInput] widget for paths.
    """

    def __init__(self, value: Any, *args: tuple, **kwargs: dict):
        """
        Arguments:
            value: currently set value in the input field.
            args: positional arguments passed to [`ConfigInput`][elva.widgets.config.ConfigInput].
            kwargs: keyword arguments passed to [`ConfigInput`][elva.widgets.config.ConfigInput].
        """
        super().__init__()
        value = str(value) if value is not None else None
        self.widget = ConfigInput(value, *args, **kwargs)

    @property
    def value(self):
        """
        Path object of the current value in the input field.
        """
        entry = self.widget.value
        return Path(entry) if entry else None

    @value.setter
    def value(self, new: Any):
        """
        Update the currently displayed value in the input field.

        Arguments:
            new: new value to be shown.
        """
        self.widget.value = str(new) if new is not None else ""


class SwitchView(ConfigView):
    """
    Configuration view wrapper around a [`Switch`][textual.widgets.Switch] widget.
    """

    def __init__(self, *args: tuple, **kwargs: dict):
        """
        Arguments:
            args: positional arguments passed to [`Switch`][textual.widgets.Switch].
            kwargs: keyword arguments passed to [`Switch`][textual.widgets.Switch].
        """
        widget = Switch(*args, **kwargs)
        super().__init__(widget)

    def compose(self):
        """
        Hook arranging child widgets.
        """
        with Grid():
            yield Label(self.name or "")
            yield Button("S", id=f"save-{self.name}")
            with Container():
                yield self.widget

    def on_button_pressed(self, message: Message):
        """
        Hook called on a button pressed event from the child widgets.

        This posts then a [`Saved`][elva.widgets.config.ConfigView.Saved] message.

        Arguments:
            message: message object posted on a button pressed event.
        """
        self.post_message(self.Saved(self.name, self.value))


class QRCode(Widget):
    """
    Collapsible QR code displaying widget.
    """

    value = reactive("")
    """QR code encoded data."""

    qr: qrcode.QRCode
    """Instance of the QR code encoding object."""

    code: Static
    """Widget instance holding the string representation of the QR code."""

    def __init__(
        self, content: str, *args: tuple, collapsed: bool = True, **kwargs: dict
    ):
        """
        Arguments:
            content: the content to encode in the QR code.
            collapsed: flag whether the view is collapsed on mount.
            args: positional arguments passed to the [`Widget`][textual.widget.Widget] class.
            kwargs: keyword arguments passed to the [`Widget`][textual.widget.Widget] class.
        """
        super().__init__(*args, **kwargs)

        self.version = 1
        self.qr = qrcode.QRCode(
            version=self.version,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            border=0,
        )
        self.code = Static()
        self.collapsible = Collapsible(title="QR", collapsed=collapsed)
        self.value = content

    def compose(self):
        """
        Hook arrange the child widgets.
        """

        with self.collapsible:
            yield self.code

    def update_qrcode(self):
        """
        Update the displayed QR code.
        """
        qr = self.qr
        qr.clear()

        f = io.StringIO()

        qr.version = self.version
        qr.add_data(self.value)
        qr.print_ascii(out=f)
        self.code.update(f.getvalue())

    def watch_value(self):
        """
        Hook called on changed value.

        This updates the displayed QR code from the new value.
        """
        self.update_qrcode()


class QRCodeView(ConfigView):
    """
    Configuration view wrapper around a [`QRCode`][elva.widgets.config.QRCode] widget.
    """

    def __init__(self, *args: tuple, **kwargs: dict):
        """
        Arguments:
            args: positional arguments passed to [`QRCode`][elva.widgets.config.QRCode].
            kwargs: keyword arguments passed to [`QRCode`][elva.widgets.config.QRCode].
        """
        widget = QRCode(*args, **kwargs)
        super().__init__(widget)

    def compose(self):
        """
        Hook arranging child widgets.
        """
        with Grid():
            yield Label(self.name or "")
            yield Button("C", id=f"copy-{self.name or "qrcode"}")
            yield self.widget

    def on_button_pressed(self, message: Message):
        """
        Hook called on a button pressed event from the child widgets.

        This copies the current QR encoded value to clipboard.

        Arguments:
            message: message object posted on a button pressed event.
        """
        copy_to_clipboard(self.value)

    def on_click(self, message: Message):
        """
        Hook called on a mouse click event.

        This toggles the collapsed state.

        Arguments:
            message: message object posted on a mouse click event.
        """
        collapsible = self.query_one(Collapsible)
        collapsible.collapsed = not collapsible.collapsed


class WebsocketsURLValidator(Validator):
    """
    Websocket URL validator.

    This class is designed for use in the [`URLInputView`][elva.widgets.config.URLInputView].
    """

    def validate(self, value: str) -> ValidationResult:
        """
        Hook called when validation is requested.

        Arguments:
            value: current input field value to be validated.

        Returns:
            a result object holding information about the validation outcome.
        """
        if value:
            try:
                parse_uri(value)
            except Exception as exc:
                return self.failure(description=str(exc))
            else:
                return self.success()
        else:
            return self.success()


class PathSuggester(Suggester):
    """
    Suggester for paths.

    This class is designed for use in the [`PathInputView`][elva.widgets.config.PathInputView] widget.
    """

    async def get_suggestion(self, value: str) -> str:
        """
        Hook called when a suggestion is requested.

        Arguments:
            value: current input widget value on which to base suggestions on.

        Returns:
            suggested extended or completed path.
        """
        path = Path(value)

        if path.is_dir():
            dir = path
        else:
            dir = path.parent

        try:
            _, dirs, files = next(dir.walk())
        except StopIteration:
            return value

        names = sorted(dirs) + sorted(files)
        try:
            name = next(filter(lambda n: n.startswith(path.name), names))
        except StopIteration:
            if path.is_dir():
                name = names[0] if names else ""
            else:
                name = path.name

        if value.startswith("."):
            prefix = "./"
        else:
            prefix = ""

        return prefix + str(dir / name)
