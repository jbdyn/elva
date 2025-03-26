import asyncio
import re
from collections import deque

from rich.segment import Segment
from rich.style import Style
from textual.app import App
from textual.binding import Binding
from textual.strip import Strip
from textual.widget import Widget


class Cursor:
    x = 0
    y = 0

    def __add__(self, other):
        self.x += other[0]
        self.y += other[1]


class REPL(Widget, can_focus=True):
    BINDINGS = [
        Binding("backspace", "delete_left"),
        Binding("delete", "delete_right"),
        Binding("left", "move_left"),
        Binding("right", "move_right"),
        Binding("ctrl+a", "jump_to_start"),
        Binding("ctrl+e", "jump_to_end"),
        Binding("ctrl+k", "delete_after"),
        Binding("ctrl+left", "jump_left"),
        Binding("ctrl+right", "jump_right"),
        Binding("ctrl+backspace", "delete_word"),
    ]

    def __init__(self, *args, prompt="repl> ", **kwargs):
        super().__init__(*args, **kwargs)
        self.stdin = asyncio.Queue()
        self.stdout = asyncio.Queue()
        self.prompt = prompt
        self.line = deque([" "])  # cursor whitespace
        self.lines = deque([self.line])
        self.cursor = Cursor()

    def render_line(self, y):
        if y < 0:
            y += len(self.lines)

        if y >= len(self.lines):
            return Strip.blank(self.size.width)

        segments = []

        is_stdin_line = False
        if y == len(self.lines) - 1:
            is_stdin_line = True
            segments.append(Segment(self.prompt))

        for s, segment in enumerate(self.lines[y]):
            if s == self.cursor.x and is_stdin_line:
                segment = Segment(
                    segment,
                    style=Style(
                        bgcolor="white",
                        color="black",
                    ),
                )
            else:
                segment = Segment(segment)
            segments.append(segment)

        return Strip(segments)

    async def read(self):
        while True:
            line = await self.stdin.get()
            line = line.strip()
            line = re.sub(r"\s{2,}", " ", line)
            cmd, *params = line.split(" ")
            if cmd:
                func = getattr(self, f"do_{cmd}", None)
                if func is not None:
                    await func(*params)
                else:
                    await self.default(cmd)
            else:
                self.print("\n")

    async def default(self, cmd):
        await self.print(f"Unknown command {cmd}")

    async def do_help(self):
        await self.print("HELP!\nME!\nNOW!")

    async def print(self, output):
        lines = output.splitlines()
        lines.append("")
        await self.stdout.put(lines)

    async def render_stdout(self):
        while True:
            lines = await self.stdout.get()
            y = len(self.lines) - 2
            for r, line in enumerate(lines):
                self.lines.insert(-1, line)
                self.render_line(y + r)
            self.refresh()

    def action_jump_to_start(self):
        self.cursor.x = 0

    def action_jump_to_end(self):
        self.cursor.x = len(self.line) - 1

    def action_delete_after(self):
        chars = list(self.line)[: self.cursor.x]
        self.line.clear()
        self.line.extend(chars + [" "])

    def action_jump(self, direction):
        line = "".join(self.line)
        words = line.split(" ")
        if direction == "left":
            indices = [0]
            indices += [
                line.index(word) for word in words if line.index(word) < self.cursor.x
            ]
        elif direction == "right":
            indices = [
                line.index(word) for word in words if line.index(word) > self.cursor.x
            ]
            indices.append(len(line) - 1)

        if indices:
            idx = min(indices, key=lambda i: abs(i - self.cursor.x))
            self.cursor.x = idx

    def action_jump_left(self):
        self.action_jump("left")

    def action_jump_right(self):
        self.action_jump("right")

    def action_delete_word(self):
        x_end = self.cursor.x
        self.action_jump_left()
        x_start = self.cursor.x

        chars = list(self.line)
        chars = chars[:x_start] + chars[x_end:]
        self.line.clear()
        self.line.extend(chars)

    def action_delete_left(self):
        if self.cursor.x > 0:
            del self.line[self.cursor.x - 1]
            self.cursor.x -= 1

    def action_delete_right(self):
        if self.cursor.x < len(self.line) - 1:
            del self.line[self.cursor.x]

    def action_move_left(self):
        if self.cursor.x > 0:
            self.cursor.x -= 1

    def action_move_right(self):
        if self.cursor.x < len(self.line) - 1:
            self.cursor.x += 1

    async def on_key(self, event):
        key = event.key
        char = event.character

        if key == "enter":
            self.cursor.x = 0
            self.cursor.y += 1
            line = "".join(self.line)
            await self.stdin.put(line)
            self.line.clear()
            self.line.append(" ")  # cursor whitespace
            self.lines.insert(-1, f"{self.prompt}{line}")
        else:
            if event.is_printable:
                self.line.insert(self.cursor.x, char)
                self.cursor.x += 1

        self.render_line(-1)
        self.refresh()

        print(self.line)
        print(self.lines)

    def on_paste(self, event):
        text = event.text
        text = text.strip()
        text = re.sub(r"\s{2,}", " ", text)
        for char in text:
            self.line.insert(self.cursor.x, char)
            self.cursor.x += 1
        self.render_line(-1)
        self.refresh()

    def on_mount(self):
        self.render_line(-1)
        self.run_worker(self.read())
        self.run_worker(self.render_stdout())


class REPLApp(App):
    def compose(self):
        yield REPL()

    def on_mount(self):
        self.query_one(REPL).focus()


if __name__ == "__main__":
    app = REPLApp()
    app.run()
