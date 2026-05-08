"""
CLI definition.
"""

from importlib import import_module as import_
from logging import FileHandler, getLogger

from click import command, get_current_context, option

from elva.cli import app, file
from elva.config import Config
from elva.log import LOGGER_NAME, DefaultFormatter


@command(name="chat")
@option(
    "--self/--no-self",
    "-s/-n",
    help="Show your own writing in the preview.",
    is_flag=True,
    default=None,
)
@file
@app
def cli(config: Config) -> None:
    """
    Send messages with real-time preview.
    \f

    Arguments:
        config: the merged configuration from CLI parameters and files.
    """

    # logging
    LOGGER_NAME.set(__package__)
    log = getLogger(__package__)

    level = config.log.level.get()
    file = config.log.file.get()

    if level is not None and file is not None:
        handler = FileHandler(file)
        handler.setFormatter(DefaultFormatter())
        log.addHandler(handler)

        log.setLevel(level)

    # defer heavy app import
    app = import_(".app", __package__)

    # init and run app
    ui = app.UI(config)
    ui.run()

    # reflect the app's return code
    ctx = get_current_context()
    ctx.exit(ui.return_code or 0)


if __name__ == "__main__":
    cli()
