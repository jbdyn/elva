from textual.app import App
from textual.widgets import TextArea


def main():
    app = App()
    # app is active from here on and
    # widgets can be initialized
    widget = TextArea()

    # no need to initialize a widget after run
    app.run()

main()
