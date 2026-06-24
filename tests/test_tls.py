from enum import IntFlag
from functools import reduce
from itertools import product
from operator import or_
from ssl import Options, TLSVersion, VerifyFlags, VerifyMode

from pytest import mark

from elva.tls import Check, Mode, Option, Version

parametrize = mark.parametrize

#
# TLS modes
#


@parametrize(
    "member",
    Mode,
)
def test_mode_name_mapping(member: Mode) -> None:
    """
    The member names differ only in prefix.

    Arguments:
        member: the mode member to check.
    """
    assert Mode.prefix + member.name == VerifyMode(member.translate()).name


#
# TLS versions
#


@parametrize(
    "member",
    Version,
)
def test_version_name_mapping(member: Version) -> None:
    """
    The member names differ only in prefix.

    Arguments:
        member: the version member to check.
    """
    assert Version.prefix + member.name == TLSVersion(member.translate()).name


#
# TLS checks
#


def test_check_not_null() -> None:
    """
    Not `0` is equal to the `ALL` alias.
    """
    assert ~Check(0) == Check.ALL


def test_check_all() -> None:
    """
    `ALL` translates to all original flags set.
    """
    assert Check.ALL.translate() == reduce(or_, VerifyFlags.__members__.values())


def test_check_iteration() -> None:
    """
    Iteration of flags includes every member.
    """
    assert reduce(or_, Check) == Check.ALL

    # the original flags do not fulfill this, which was the reason to
    # have the translation enum in the first place
    assert reduce(or_, VerifyFlags) != Check.ALL.translate()


def test_check_all_non_null_covered() -> None:
    """
    All members and (false) aliases except the default ones (with value `0`)
    are represented.
    """
    # no deprecated or renamed members, skips (only true) aliases
    members = set(Check.prefix + m.name for m in Check)

    # exclude default (`0`) members and include members and (false) aliases
    expected = set(n for n, m in VerifyFlags.__members__.items() if m > 0)

    assert members == expected


@parametrize(
    "member",
    Check,
)
def test_check_name_mapping(member: Check) -> None:
    """
    The member names differ only in prefix.

    Arguments:
        member: the check member to check.
    """
    assert Check.prefix + member.name == VerifyFlags(member.translate()).name


@parametrize(
    "member",
    (reduce(or_, p) for i in range(2) for p in product(Check, repeat=i + 1)),
)
def test_check_names(member: Check) -> None:
    """
    Every member and member combination translates correctly.

    No need to check every possible combination of flags.
    It suffices to know that
    - a `Flag` class is tested,
    - every member passes the test on its own and
    - every combination of two members passes the test,
    so every larger combination is expected to work as well.

    Arguments:
        member: the check member to check.
    """
    translated = member.translate()

    assert isinstance(translated, IntFlag)
    assert translated in VerifyFlags


#
# TLS options
#


def test_option_not_null() -> None:
    """
    Not `0` is equal to the `ALL` alias.
    """
    assert ~Option(0) == Option.ALL


def test_option_all() -> None:
    """
    `ALL` translates to all original flags set.
    """
    assert Option.ALL.translate() in reduce(or_, Options.__members__.values())


def test_option_iteration() -> None:
    """
    Iteration of flags includes every member.
    """
    assert reduce(or_, Option) == Option.ALL

    # the original flags do not fulfill this, which was the reason to
    # have the translation enum in the first place
    assert reduce(or_, Options) != Option.ALL.translate()


def test_option_all_non_null_covered() -> None:
    """
    All members and (false) aliases except the default ones (with value `0`)
    are represented.
    """
    # no deprecated or renamed members, skips (only true) aliases
    members = set(Option.rename.get(m.name, Option.prefix + m.name) for m in Option)

    # exclude default (`0`) members and include members and (false) aliases
    expected = set(n for n, m in Options.__members__.items() if m > 0)

    # ignore deprecated options
    deprecated = set(
        n
        for n in Options.__members__
        if any(n.startswith(d) for d in ("OP_NO_SSL", "OP_NO_TLS"))
    )

    assert members == expected - deprecated


@parametrize(
    "member",
    Option,
)
def test_option_name_mapping(member: Option) -> None:
    """
    The member names differ only in prefix or have been renamed.

    Arguments:
        member: the option member to check.
    """
    assert (
        Option.rename.get(member.name, Option.prefix + member.name)
        == Options(member.translate()).name
    )


@parametrize(
    "member",
    (reduce(or_, p) for i in range(2) for p in product(Option, repeat=i + 1)),
)
def test_option_names(member: Option) -> None:
    """
    Every member and member combination translates correctly.

    No need to check every possible combination of flags.
    It suffices to know that
    - a `Flag` class is tested,
    - every member passes the test on its own and
    - every combination of two members passes the test,
    so every larger combination is expected to work as well.

    Arguments:
        member: the option member to check.
    """
    translated = member.translate()

    assert isinstance(translated, IntFlag)
    assert translated in Options
