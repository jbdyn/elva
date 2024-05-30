from textual.app import App
from textual.widgets import TextArea
from anyio import run, create_task_group


class TestApp(App):
    def compose(self):
        yield TextArea()

async def main():
    app = TestApp()
    async with create_task_group() as tg:
        tg.start_soon(app.run_async)

if __name__ == "__main__":
    run(main)
