"""
CLI definition.
"""

from importlib import import_module as import_
from logging import FileHandler, getLogger

from click import command, get_current_context, option

from elva.cli import app, file
from elva.config import Config
from elva.log import LOGGER_NAME, DefaultFormatter


@command(name="editor")
@option(
    "--ansi/--textual",
    "-a/-t",
    is_flag=True,
    help="Use the terminal ANSI colors for the Textual colortheme.",
    default=None,
)
@file
@app
def cli(config: Config) -> None:
    """
    Edit text documents collaboratively in real-time.
    \f

    Arguments:
        config: the merged configuration from CLI parameters and files.
        args: unused positional arguments.
        kwargs: parameters passed from the CLI.
    """
    # logging
    LOGGER_NAME.set(__package__)
    log = getLogger(__package__)

    level = config.log.level.get()
    file = config.log.file.get()

    if file is not None and level is not None:
        handler = FileHandler(file)
        handler.setFormatter(DefaultFormatter())
        log.addHandler(handler)

        log.setLevel(level)

    # defer heavy app import
    app = import_(".app", __package__)

    # run app
    ui = app.UI(config)
    ui.run()

    # reflect the app's return code
    ctx = get_current_context()
    ctx.exit(ui.return_code or 0)


if __name__ == "__main__":
    cli()
