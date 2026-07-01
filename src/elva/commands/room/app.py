from os import linesep

from click import ClickException, echo

from elva.config import Config
from elva.server import fetch_rooms


def display(room: dict, details: bool = False) -> None | str:
    """
    Get the display string for a single room.

    Arguments:
        room: the room object.
        details: if `True`, print more than the `identifier`.

    Returns:
        `None` if not to display at all, else the formtted string
        representation for a room.
    """
    out = room.pop("identifier")

    if out is None:
        return

    if details:
        clients = room.pop("clients", "?")

        keys = ",".join(key for key, value in sorted(room.items()) if value)

        out += f"\t{clients}\t{keys}"

    return out


def run(config: Config) -> None:
    """
    List active rooms on a server.

    Arguments:
        config: the CLI config.
    """
    # alias
    c = config

    # fail early when host is missing
    host = c.get("connect.host")

    if host is None:
        raise ClickException("no host specified")

    #
    # set config details and default values
    timeout = c.get("room.timeout")
    details = c.get("room.details", False)
    json = c.get("room.json", False)

    try:
        rooms = fetch_rooms(
            host,
            port=c.get("connect.port"),
            tls_config=c.get("tls", {}),
            timeout=timeout,
            raw=json,
        )
    except Exception as exc:
        reason = getattr(exc, "reason", str(exc))
        raise ClickException(reason)

    #
    # print fetch result
    if json:
        echo(rooms)
    else:
        if rooms:
            echo(
                linesep.join(
                    out for room in rooms if (out := display(room, details=details))
                )
            )
