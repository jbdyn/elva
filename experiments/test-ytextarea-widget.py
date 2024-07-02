from pycrdt import Doc, Text
from textual.app import App
from textual.widgets import Markdown, TabbedContent

from elva.apps.editor import YTextArea, YTextAreaParser


class UI(App):
    def __init__(self):
        super().__init__()
        ydoc = Doc()
        text = Text()
        ydoc["text"] = text

        self.text_area = YTextArea(text)
        self.parser = YTextAreaParser(text, self.text_area)

    def on_mount(self):
        self.run_worker(self.parser.start())

    async def on_unmount(self):
        await self.parser.stopped.wait()

    def compose(self):
        with TabbedContent("YText", "Markdown"):
            yield self.text_area
            yield Markdown("# TEST")

if __name__ == "__main__":
    app = UI()
    app.run()
