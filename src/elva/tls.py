from enum import STRICT, Enum, IntEnum, IntFlag, auto
from functools import reduce
from itertools import chain
from operator import or_
from ssl import Options, TLSVersion, VerifyFlags, VerifyMode
from typing import Any, Callable, Generator, Type


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
