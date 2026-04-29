"""
CLI definition.
"""

from importlib import import_module as import_

import click

from elva.cli import app, file


@click.command(name="editor")
@click.option(
    "--ansi/--textual",
    "-a/-t",
    is_flag=True,
    help="Use the terminal ANSI colors for the Textual colortheme.",
    default=None,
)
@file
@app
def cli(config: dict) -> None:
    """
    Edit text documents collaboratively in real-time.
    \f

    Arguments:
        config: the merged configuration from CLI parameters and files.
        args: unused positional arguments.
        kwargs: parameters passed from the CLI.
    """
    logging = import_("logging")
    _log = import_("elva.log")
    app = import_(".app", __package__)

    # logging
    _log.LOGGER_NAME.set(__package__)
    log = logging.getLogger(__package__)

    log_config = config.get("log", {})
    file = log_config.get("file")
    level = log_config.get("level")

    if level is not None and file is not None:
        handler = logging.FileHandler(file)
        handler.setFormatter(_log.DefaultFormatter())
        log.addHandler(handler)

        log.setLevel(level)

    # run app
    ui = app.UI(config)
    ui.run()

    # reflect the app's return code
    ctx = click.get_current_context()
    ctx.exit(ui.return_code or 0)


if __name__ == "__main__":
    cli()
