"""
CLI definition.
"""

from importlib import import_module as import_

import click

from elva.cli import app, file


@click.command(name="chat")
@click.option(
    "--self",
    "-s",
    help="Show your own writing in the preview.",
    is_flag=True,
    default=None,
)
@file
@app
def cli(config: dict) -> None:
    """
    Send messages with real-time preview.
    \f

    Arguments:
        config: the merged configuration from CLI parameters and files.
    """
    logging = import_("logging")
    _log = import_("elva.log")
    app = import_(".app", __package__)

    # logging
    _log.LOGGER_NAME.set(__package__)
    log = logging.getLogger(__package__)

    file = config.get("log", {}).get("file")
    level = config.get("log", {}).get("level")

    if level is not None and file is not None:
        handler = logging.FileHandler(file)
        handler.setFormatter(_log.DefaultFormatter())
        log.addHandler(handler)

        log.setLevel(level)

    # init and run app
    ui = app.UI(config)
    ui.run()

    # reflect the app's return code
    ctx = click.get_current_context()
    ctx.exit(ui.return_code or 0)


if __name__ == "__main__":
    cli()
