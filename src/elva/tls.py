from collections.abc import Sequence
from enum import STRICT, Enum, IntEnum, IntFlag, auto
from functools import reduce
from itertools import chain
from operator import or_
from ssl import (
    Options,
    Purpose,
    SSLContext,
    TLSVersion,
    VerifyFlags,
    VerifyMode,
    create_default_context,
)
from typing import Any, Callable, Generator, Type

from elva.core import LOCAL_HOSTS


class Renamed:
    """
    Proxy enumeration for holding renamed members of a given source enumeration.
    """

    source = Enum
    """
    The source enumeration to translate back to.
    """

    prefix = ""
    """
    The prefix to preprend to member names when translating.
    """

    rename = dict()
    """
    Mapping of renames.
    """

    def __str__(self) -> str:
        """
        Get the string conversion of the enumeration member.
        """
        return self.name

    def translate(self) -> Enum:
        """
        Translate back to the source member.

        Returns:
            the member of the source enumeration.
        """
        name = self.rename.get(self.name, self.prefix + self.name)

        return self.source[name]


class RenamedIterable(Renamed):
    """
    Proxy enumeration for holding renamed members of a given source enumeration
    which is iterable.
    """

    def translate(self) -> Enum:
        """
        Translate back to the source member.

        Returns:
            the member of the source enumeration.
        """
        return reduce(
            or_,
            (
                self.source[self.rename.get(member.name, self.prefix + member.name)]
                for member in self
            ),
        )


def filtered(
    source: Type[Enum],
    by: Callable,
) -> Generator[tuple[str, Any], None, None]:
    """
    Generate the filtered members of a given enumeration.

    Arguments:
        source: the enumeration to filter the member of.
        by:
            the filter function getting `name` and `member` of the source and
            returning `None` when to exclude or `(name, value)` tuple else.

    Yields:
        the output of the filter function if it is not `None`.
    """
    for item in source.__members__.items():
        if (out := by(*item)) is not None:
            yield out


#
# versions
#


class RenamedVersion(Renamed):
    """
    Renamed TLS versions.
    """

    source = TLSVersion


def filter_version(name: str, member: TLSVersion) -> None | tuple[str, TLSVersion]:
    """
    Filter versions.

    Arguments:
        name: the version name.
        member: the version enumeration member.

    Returns:
        `None` if to be excluded, else the `(name, member)` tuple as given.
    """
    if name in (
        # deprecated versions
        "SSLv3",
        "TLSv1",
        "TLSv1_1",
    ):
        return
    else:
        return name, member


Version = IntEnum(
    "Version",
    filtered(TLSVersion, filter_version),
    type=RenamedVersion,
)
"""
Available TLS versions.
"""


#
# modes
#

PREFIX_MODE = "CERT_"


class RenamedMode(Renamed):
    """
    Renamed TLS verification modes.
    """

    source = VerifyMode
    prefix = PREFIX_MODE


def filter_mode(name: str, member: VerifyMode) -> tuple[str, VerifyMode]:
    """
    Filter modes.

    Arguments:
        name: the mode name.
        member: the mode enumeration member.

    Returns:
        `(name, member)` tuple with the prefix stripped from the name.
    """
    return name.replace(PREFIX_MODE, ""), member


Mode = IntEnum(
    "Mode",
    filtered(VerifyMode, filter_mode),
    type=RenamedMode,
)
"""
Available TLS modes.
"""


#
# checks
#

PREFIX_CHECK = "VERIFY_"


class RenamedCheck(RenamedIterable):
    """
    Renamed TLS checks.
    """

    source = VerifyFlags
    prefix = PREFIX_CHECK


def filter_check(name: str, member: VerifyFlags) -> None | tuple[str, int]:
    """
    Filter checks.

    Arguments:
        name: the check name.
        member: the check enumeration member.

    Returns:
        `(name, int)` tuple with the prefix stripped from the name and
        and an automatically set continuous flag value.
    """
    if member == 0:
        return
    else:
        return name.replace(PREFIX_CHECK, ""), auto()


_Check = IntFlag(
    "_Check",
    filtered(VerifyFlags, filter_check),
)
"""
Intermediate check enumeration without aliases.
"""

Check = IntFlag(
    "Check",
    chain(
        _Check.__members__.items(),
        (("ALL", reduce(or_, _Check)),),
    ),
    type=RenamedCheck,
    boundary=STRICT,
)
"""
Available TLS checks.
"""


#
# options
#

PREFIX_OPTION = "OP_"


class RenamedOption(RenamedIterable):
    """
    Renamed TLS options.
    """

    source = Options
    prefix = PREFIX_OPTION
    rename = {
        "DEFAULT": "OP_ALL",
    }


def filter_option(name: str, member: Options) -> None | tuple[str, int]:
    """
    Filter options.

    Arguments:
        name: the option name.
        member: the option enumeration member.

    Returns:
        `(name, int)` tuple with the prefix stripped from the name and
        and an automatically set continuous flag value.
    """
    if member == 0 or any(
        name.startswith(deprecated)
        for deprecated in (
            "OP_NO_SSL",
            "OP_NO_TLS",
        )
    ):
        return
    elif name == "OP_ALL":
        return "DEFAULT", auto()
    else:
        return name.replace(PREFIX_OPTION, ""), auto()


_Option = IntFlag(
    "_Option",
    filtered(Options, filter_option),
)
"""
Intermediate option enumeration without aliases.
"""

Option = IntFlag(
    "Option",
    chain(
        _Option.__members__.items(),
        (("ALL", reduce(or_, _Option)),),
    ),
    type=RenamedOption,
    boundary=STRICT,
)
"""
Available TLS options.
"""

#
# setup
#


def enable(purpose: Purpose, config: dict) -> SSLContext:
    """
    Return TLS context and websocket scheme for TLS turned off.

    Arguments:
        config: the TLS section of the ELVA config.

    Returns:
        the configured TLS context.
    """
    # the client authenticates the server
    ctx = create_default_context(purpose)

    hostname = config.get("hostname")

    # update hostname check flag depending on the mode set
    if config.get("mode") in (Mode.NONE, Mode.OPTIONAL):
        config["hostname"] = hostname = False

    # update hostname check flag in the TLS context
    if hostname is not None:
        ctx.check_hostname = hostname

    # update other attributes with enumeration values
    for param, attr in (
        ("mode", "verify_mode"),
        ("version", "minimum_version"),
        ("options", "options"),
        ("checks", "verify_flags"),
    ):
        if (new := config.get(param)) is not None:
            if isinstance(new, Sequence):
                new = reduce(or_, new)

            setattr(ctx, attr, new.translate())

    return ctx


def setup(purpose: Purpose, host: str, config: dict) -> None | SSLContext:
    """
    Return the TLS context and websocket scheme depending on the given TLS config.

    Arguments:
        purpose: the purpose of the TLS context.
        host: the host address.
        config: the TLS section of the ELVA config.

    Returns:
        `None` if TLS is disabled, else the configured TLS context.
    """
    on = config.get("on")

    if on is None:
        if host in LOCAL_HOSTS:
            return
        else:
            return enable(purpose, config)
    elif on:
        return enable(purpose, config)
    else:  # not on and not `None`
        return


def client(host: str, config: dict) -> None | SSLContext:
    """
    Set up the TLS context for a client.

    Arguments:
        host: the host address.
        config: the TLS section of the ELVA config.

    Returns:
        `None` if TLS is disabled, else the configured TLS context.
    """
    return setup(Purpose.SERVER_AUTH, host, config)


def server(host: str, config: dict) -> None | SSLContext:
    """
    Set up the TLS context for a client.

    Arguments:
        host: the host address.
        config: the TLS section of the ELVA config.

    Returns:
        `None` if TLS is disabled, else the configured TLS context.
    """
    return setup(Purpose.CLIENT_AUTH, host, config)
