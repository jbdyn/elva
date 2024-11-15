import io
import sys
from pathlib import Path

import qrcode
from pyperclip import copy as copy_to_clipboard
from textual.containers import Container, Grid, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.suggester import Suggester
from textual.validation import Validator
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


class QRCodeLabel(Widget):
    value = reactive("")

    def __init__(self, content, *args, collapsed=True, **kwargs):
        super().__init__(*args, **kwargs)

        self.version = 1
        self.qr = qrcode.QRCode(
            version=self.version,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            border=0,
        )
        self.label = Static()
        self.collapsible = Collapsible(title="QR", collapsed=collapsed)

    def compose(self):
        with self.collapsible:
            yield self.label

    def generate_qrcode(self):
        qr = self.qr
        qr.clear()

        f = io.StringIO()

        qr.version = self.version
        qr.add_data(self.value)
        qr.print_ascii(out=f)
        self.label.update(f.getvalue())

    def watch_value(self):
        self.generate_qrcode()


class RadioSelect(Container):
    def __init__(self, options, *args, value=None, **kwargs):
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
    def from_values(cls, options, *args, value=None, **kwargs):
        options = [(str(option), option) for option in options]

        return cls(options, *args, value=value, **kwargs)

    def compose(self):
        with self.radio_set:
            for button in self.buttons.values():
                yield button

    @property
    def value(self):
        return self.options[self.radio_set.pressed_button.name]

    @value.setter
    def value(self, new):
        name = self.names[self.values.index(new)]
        self.buttons[name].value = True

    def on_click(self, message):
        self.radio_set.pressed_button.focus()


class ConfigPanel(Container):
    class Applied(Message):
        def __init__(self, last, config, changed):
            super().__init__()
            self.last = last
            self.config = config
            self.changed = changed

    def __init__(self, config, applied=False, label=None):
        super().__init__()
        self.config = config
        self.applied = applied
        self.label = label

    @property
    def state(self):
        return dict((c.name, c.value) for c in self.config)

    @property
    def last(self):
        return dict((c.name, c.last) for c in self.config)

    @property
    def changed(self):
        if self.applied:
            return set(c.name for c in self.config if c.changed)
        else:
            return set(c.name for c in self.config)

    def compose(self):
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
        for c in self.config:
            c.apply()
        self.applied = True

    def reset(self):
        for c in self.config:
            c.reset()

    def post_applied_config(self):
        self.post_message(self.Applied(self.last, self.state, self.changed))
        self.apply()

    def on_button_pressed(self, message):
        match message.button.id:
            case "apply":
                self.post_applied_config()
            case "reset":
                self.reset()

    def decode_content(self, content):
        try:
            config = tomllib.loads(content)
        # tomli exceptions may change in the future according to its docs
        except Exception:
            config = None
        return config

    def on_paste(self, message):
        config = self.decode_content(message.text)
        if config:
            for c in self.config:
                value = config.get(c.name)
                if value is not None:
                    c.value = value


class ConfigView(Container):
    hover = reactive(False)
    focus_within = reactive(False)

    class Changed(Message):
        def __init__(self, name, value):
            super().__init__()
            self.name = name
            self.value = value

    class Saved(Message):
        def __init__(self, name, value):
            super().__init__()
            self.name = name
            self.value = value

    def __init__(self, widget):
        super().__init__()
        self.widget = widget

    def compose(self):
        yield Label(self.name or "")
        yield self.widget

    def on_mount(self):
        self.apply()

    def apply(self):
        self.last = self.value

    def reset(self):
        self.value = self.last

    @property
    def changed(self):
        return self.last != self.value

    @property
    def name(self):
        return self.widget.name

    @property
    def value(self):
        return self.widget.value

    @value.setter
    def value(self, new):
        self.widget.value = new

    def toggle_button_visibility(self, state):
        if state:
            self.query(Button).remove_class("invisible")
        else:
            self.query(Button).add_class("invisible")

    def on_enter(self, message):
        self.hover = True

    def on_leave(self, message):
        if not self.is_mouse_over and not self.focus_within:
            self.hover = False

    def watch_hover(self, hover):
        self.toggle_button_visibility(hover)

    def on_descendant_focus(self, message):
        self.focus_within = True

    def on_descendant_blur(self, message):
        if not any(node.has_focus for node in self.query()):
            self.focus_within = False

    def watch_focus_within(self, focus):
        self.toggle_button_visibility(focus)


class ConfigInput(Input):
    def _on_paste(self, message):
        try:
            tomllib.loads(message.text)
        except Exception:
            pass
        else:
            # prevent Input._on_paste() being called,
            # so the Paste message can bubble up to ConfigPanel.on_paste()
            message.prevent_default()


class RadioSelectView(ConfigView):
    def __init__(self, *args, **kwargs):
        widget = RadioSelect(*args, **kwargs)
        super().__init__(widget)

    def compose(self):
        with Grid():
            yield Label(self.name or "")
            yield Button("S", id=f"save-{self.name}")
            yield self.widget

    def on_button_pressed(self, message):
        self.post_message(self.Saved(self.name, self.value))

    def on_click(self, message):
        self.widget.radio_set.focus()

    def on_radio_set_changed(self, message):
        self.post_message(self.Changed(self.name, self.value))


class TextInputView(ConfigView):
    def __init__(self, *args, **kwargs):
        widget = ConfigInput(*args, **kwargs)
        super().__init__(widget)

    def compose(self):
        with Grid():
            yield Label(self.name or "")
            with Grid():
                yield Button("X", id=f"cut-{self.name}")
                yield Button("C", id=f"copy-{self.name}")
                yield Button("S", id=f"save-{self.name}")
            yield self.widget

    def on_button_pressed(self, message):
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

    def on_input_changed(self, message):
        self.post_message(self.Changed(self.name, self.value))


class URLInputView(TextInputView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_valid = True

    def on_input_changed(self, message):
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
        entry = self.widget.value
        return entry if entry and self.is_valid else None

    @value.setter
    def value(self, new):
        self.widget.value = str(new) if new is not None else ""


class PathInputView(TextInputView):
    def __init__(self, value, *args, **kwargs):
        super().__init__()
        value = str(value) if value is not None else None
        self.widget = ConfigInput(value, *args, **kwargs)

    @property
    def value(self):
        entry = self.widget.value
        return Path(entry) if entry else None

    @value.setter
    def value(self, new):
        self.widget.value = str(new) if new is not None else ""


class SwitchView(ConfigView):
    def __init__(self, *args, **kwargs):
        widget = Switch(*args, **kwargs)
        super().__init__(widget)

    def compose(self):
        with Grid():
            yield Label(self.name or "")
            yield Button("S", id=f"save-{self.name}")
            with Container():
                yield self.widget

    def on_button_pressed(self, message):
        self.post_message(self.Saved(self.name, self.value))


class QRCodeView(ConfigView):
    def __init__(self, *args, **kwargs):
        widget = QRCodeLabel(*args, **kwargs)
        super().__init__(widget)

    def compose(self):
        with Grid():
            yield Label(self.name or "")
            yield Button("C", id=f"copy-{self.name or "qrcode"}")
            yield self.widget

    def on_button_pressed(self, message):
        copy_to_clipboard(self.value)

    def on_click(self, message):
        collapsible = self.query_one(Collapsible)
        collapsible.collapsed = not collapsible.collapsed


class WebsocketsURLValidator(Validator):
    def validate(self, value):
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
    async def get_suggestion(self, value):
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
