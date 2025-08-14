from importlib import import_module as import_

import click

from elva.cli import common_options, file_paths_option_and_argument, pass_config_for

APP_NAME = "editor"


@click.command(name=APP_NAME)
@common_options
@click.option(
    "--auto-save/--no-auto-save",
    "auto_save",
    is_flag=True,
    default=True,
    help="Enable automatic rendering of the file contents.",
)
@click.option(
    "--timeout",
    "timeout",
    help="The time interval in seconds between consecutive renderings.",
    type=click.IntRange(min=0),
)
@click.option(
    "--ansi-color/--no-ansi-color",
    "ansi_color",
    is_flag=True,
    help="Use the terminal ANSI colors for the Textual colortheme.",
)
@file_paths_option_and_argument
@pass_config_for(APP_NAME)
def cli(
    config,
    **kwargs,
):
    """
    Edit text documents collaboratively in real-time.
    \f

    Arguments:
        ctx: the click context holding the configuration parameter mapping.
        auto_save: flag whether to render on closing.
        ansi_color: flag whether to use the terminal's ANSI color codes.
        file: path to the ELVA SQLite database file.
    """
    logging = import_("logging")
    _log = import_("elva.log")
    app = import_("elva.apps.editor.app")

    # logging
    _log.LOGGER_NAME.set(__package__)
    log = logging.getLogger(__package__)

    log_path = config.get("log")
    level_name = config.get("verbose")
    if level_name is not None and log_path is not None:
        handler = logging.FileHandler(log_path)
        handler.setFormatter(_log.DefaultFormatter())
        log.addHandler(handler)

        level = logging.getLevelNamesMapping()[level_name]
        log.setLevel(level)

    # run app
    ui = app.UI(config)
    ui.run()


if __name__ == "__main__":
    cli()
