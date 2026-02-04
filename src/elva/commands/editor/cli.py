"""
CLI definition.
"""

from importlib import import_module as import_
from json import JSONDecodeError, loads
from logging import FileHandler, getLogger
from typing import Callable
from urllib.error import URLError
from urllib.request import urlopen

from click import ClickException, command, echo, option, prompt

from elva.cli import context, data, unset
from elva.config import Config
from elva.core import update_port
from elva.log import LOGGER_NAME, DefaultFormatter

TRANSLATE = {
    "ansi": "ansi",
    "a": "ansi",
    "textual": "ansi",
    "t": "ansi",
    "file": "data",
    "f": "data",
}
"""
Table for translation from flag to parameter names.
"""

# TODO: move fetching of rooms into new `room.py` module
# TODO: refine feedback to user


def fetch_rooms(host: str, port: int) -> list[str]:
    """
    Fetch list of room identifiers from server.

    Arguments:
        host: the server hostname.
        port: the server port.

    Returns:
        list of room identifiers, or empty list on error.
    """
    url = f"http://{host}:{port}/"
    try:
        with urlopen(url, timeout=5) as response:
            data = response.read().decode("utf-8")
            rooms = loads(data)
            return [r.get("identifier") for r in rooms if r.get("identifier")]
    except (URLError, JSONDecodeError):
        return []


def prompt_for_room(host: str, port: int) -> str:
    """
    Prompt user to select or enter a room name.

    Arguments:
        host: the server hostname.
        port: the server port.

    Returns:
        the selected or entered room name.
    """
    rooms = fetch_rooms(host, port)

    if rooms:
        echo(f"Available rooms on {host}:{port}:")
        for i, room in enumerate(rooms, 1):
            echo(f"  {i}. {room}")
        echo()

        choice = prompt(
            "Enter room number or new room name",
            default=rooms[0] if rooms else None,
        )

        # Check if user entered a number
        try:
            idx = int(choice)
            if 1 <= idx <= len(rooms):
                return rooms[idx - 1]
        except ValueError:
            pass

        return choice
    else:
        echo(f"No rooms available on {host}:{port}.")
        echo()
        return prompt("Enter room name")


def run(config: Config) -> None:
    """
    Run the app.

    Arguments:
        config: the merged config.
    """
    # alias
    c = config

    host = c.get("connect.host")

    if host is None:
        ClickException("no host specified")

    # Prompt for room if not specified
    if not c.get("connect.identifier"):
        port = update_port(host, port=c.get("connect.port"))

        if port is not None:
            c["connect.port"] = port

        c["connect.identifier"] = prompt_for_room(host, port)

    # logging
    LOGGER_NAME.set(__package__)
    log = getLogger(__package__)

    level = c.get("log.level")
    file = c.get("log.file")

    if file is not None and level is not None:
        handler = FileHandler(file)
        handler.setFormatter(DefaultFormatter())
        log.addHandler(handler)
        log.setLevel(level)

    # defer heavy app import
    app = import_(".app", __package__)

    # run app
    ui = app.UI(c)
    ui.run()

    return ui.return_code


@command(name="editor")
@option(
    "--ansi/--textual",
    "-a/-t",
    "ansi",
    is_flag=True,
    help="Use the terminal ANSI colors for the Textual colortheme.",
    default=None,
)
@data
@unset(TRANSLATE)
@context
def cli(config: dict) -> Callable:
    """
    Edit text documents collaboratively in real-time.
    \f

    Arguments:
        config: the merged `editor` config section.
    """
    return run
