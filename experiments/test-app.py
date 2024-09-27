from textual.app import App
from textual.widget import Widget
from textual.widgets import Label

# This script tests the order of execution for composing, mounting and unmounting.
# The log output can be viewed via `textual console` in one terminal and `textual run --dev test-app.py` in another.
#
# The order of execution is:
# 1. compose
# 2. on_mount
# 3. on_unmount


class TestWidget(Widget):
    def on_mount(self):
        self.log("TestWidget.on_mount")

    def compose(self):
        self.log("TestWidget.compose")
        yield Label("TestWidget")

    def on_unmount(self):
        self.log("TestWidget.on_unmount")


class TestApp(App):
    async def on_mount(self):
        self.log("TestApp.on_mount")

    def compose(self):
        self.log("TestApp.compose")
        yield TestWidget()

    async def on_unmount(self):
        self.log("TestApp.on_unmount")


if __name__ == "__main__":
    app = TestApp()
    app.run()
