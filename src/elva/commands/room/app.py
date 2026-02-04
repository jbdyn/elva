from http.client import RemoteDisconnected
from json import JSONDecodeError, loads
from os import linesep
from ssl import SSLContext
from urllib.error import HTTPError, URLError
from urllib.parse import urlunparse
from urllib.request import urlopen

from click import ClickException, echo

from elva.config import Config
from elva.tls import client


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
        keys = ",".join(key for key, value in sorted(room.items()) if value)

        out += f"\t{keys}"

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

    # set net location
    port = c.get("connect.port")
    netloc = f"{host}:{port}" if port is not None else host

    # set up TLS
    ctx = client(host, c.get("tls", {}))
    safe = isinstance(ctx, SSLContext)

    protocols = [("https" if safe else "http", ctx)]

    # if TLS was enabled by default, add a non-secure fallback,
    # else don't try to set up a TLS context automatically
    if c.get("tls.on") is None and safe:
        protocols.append(("http", None))

    # set config details and default values
    timeout = c.get("room.timeout", 5)
    details = c.get("room.details", False)
    json = c.get("room.json", False)

    data = None
    error = None

    for protocol, tls in protocols:
        url = urlunparse((protocol, netloc, "", None, None, None))

        try:
            with urlopen(url, timeout=timeout, context=tls) as response:
                data = response.read().decode("utf-8")
                rooms = loads(data)
                break
        except (HTTPError, RemoteDisconnected) as exc:
            # HTTP error (4xx, 5xx) - don't retry with different protocol
            raise ClickException(f"server error: {exc}")
        except URLError as exc:
            # Connection error - try next protocol
            error = exc
            continue
        except JSONDecodeError as exc:
            raise ClickException(f"invalid response from server: {exc}")

    if data is None:
        reason = getattr(error, "reason", error)
        raise ClickException(f"could not connect to server: {reason}")

    if json:
        echo(data)
    else:
        if not rooms:
            echo("no active rooms", err=True)
        else:
            echo(
                linesep.join(
                    out for room in rooms if (out := display(room, details=details))
                )
            )
