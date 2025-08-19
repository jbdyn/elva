"""
CLI definition.
"""

from importlib import import_module as import_

import click

from elva.cli import common_options, file_paths_option_and_argument, pass_config_for

APP_NAME = "editor"
"""The name of the app."""


@click.command(name=APP_NAME)
@common_options
@click.option(
    "--ansi-color/--no-ansi-color",
    "ansi_color",
    is_flag=True,
    help="Use the terminal ANSI colors for the Textual colortheme.",
)
@file_paths_option_and_argument
@pass_config_for(APP_NAME)
def cli(
    config: dict,
    *args: tuple,
    **kwargs: dict,
):
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

    # reflect the app's return code
    ctx = click.get_current_context()
    ctx.exit(ui.return_code or 0)


if __name__ == "__main__":
    cli()
