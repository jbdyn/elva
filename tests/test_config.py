from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Callable, Generator, Sequence

from pytest import mark, raises

from elva.config import Config

# alias
parametrize = mark.parametrize

MAP = {
    "foo": {
        "bar": {
            "baz": [1, 2, 3],
        },
        "x": 1,
        "y": set(list("abc")),
    },
}
"""Test mapping."""


@parametrize(
    "mapping",
    (
        {},
        MAP,
    ),
)
def test_str(mapping: dict) -> None:
    """
    The string conversion is the string conversion of the config data.

    Arguments:
        mapping: the mapping to convert to a string.
    """
    assert str(mapping) == str(Config(mapping))


@parametrize(
    "mapping",
    (
        {},
        MAP,
    ),
)
def test_repr(mapping: dict) -> None:
    """
    Evaluating the string representation with `eval` gives an equal `Config`.

    Arguments:
        mapping: the mapping to get a config representation from.
    """
    config = Config(mapping)
    evaluated = eval(repr(config))

    # the data are the same
    assert evaluated == config

    # it is a `Config` instance
    assert isinstance(evaluated, Config)


@parametrize(
    "mapping",
    (
        {},
        MAP,
    ),
)
def test_len(mapping: dict) -> None:
    """
    The length of a config is the length of the config data.

    Arguments:
        mapping: the mapping to compare the length of.
    """
    assert len(Config(mapping)) == len(mapping)


@parametrize(
    "mapping",
    (
        {},
        MAP,
    ),
)
def test_eq(mapping: dict) -> None:
    """
    `Config`s are equal when their config data are equal.

    Arguments:
        mapping: the mapping to compare for equality.
    """
    assert mapping == Config(mapping)
    assert mapping is not Config(mapping)
    assert Config(mapping) == Config(mapping)


@parametrize(
    ("left", "right"),
    (
        ({}, MAP),
        (MAP, {}),
        ({"foo": "bar"}, {"baz": 42}),
    ),
)
def test_ne(left: dict, right: dict) -> None:
    """
    `Config`s are not equal when their config data are not equal.

    Arguments:
        left: the left mapping to compare for unquality.
        right: the right mapping to compare for unquality.
    """
    assert left != Config(right)
    assert Config(left) != right
    assert Config(left) != Config(right)


@parametrize(
    ("mapping", "path"),
    (
        ({"foo": "bar"}, "foo"),
        ({"x": "y"}, "x"),
        (MAP, "foo.bar.baz"),
    ),
)
def test_contains(mapping: dict, path: str) -> None:
    """
    A key is present when the key is present in the config data.

    Arguments:
        mapping: the mapping to test for.
        path: the path to check for presence.
    """
    assert path in Config(mapping)


@parametrize(
    ("mapping", "path"),
    (
        ({}, "foo"),
        ({}, "foo.bar"),
        ({"baz": "quux"}, "foo"),
        (MAP, "quux.fizz.buzz"),
    ),
)
def test_not_contains(mapping: dict, path: str) -> None:
    """
    A key is not present when the key is not present in the config data.

    Arguments:
        mapping: the mapping to test for.
        path: the path to check for absence.
    """
    assert path not in Config(mapping)


def test_delimiter() -> None:
    """
    The delimiter of keys in a path is the dot `.`.
    """
    assert Config().delimiter == "."


@parametrize(
    ("keys", "expected"),
    (
        ([], ""),
        (["a"], "a"),
        (["a", "b"], "a.b"),
        (["a", "b", "c"], "a.b.c"),
    ),
)
def test_path(keys: Sequence[str], expected: str) -> None:
    """
    A `Config` generates correct paths from a sequence of keys.

    Arguments:
        keys: the keys to assemble to a path.
        expected: the expected returned path.
    """
    assert Config().path(*keys) == expected


@contextmanager
def config(mapping: Mapping = MAP) -> Generator[Config, None, None]:
    """
    Manage the test config instance.

    Arguments:
        mapping: the config data.

    Yields:
        the test config instance.
    """
    try:
        _config = Config(deepcopy(mapping))
        yield _config
    finally:
        del _config


@parametrize(
    ("operation", "expected"),
    (
        (lambda c: c.get("foo"), MAP["foo"]),
        (lambda c: c.get("foo.bar"), MAP["foo"]["bar"]),
        (lambda c: c.get("foo.bar.baz"), MAP["foo"]["bar"]["baz"]),
        (lambda c: c.get("foo.x"), MAP["foo"]["x"]),
        (lambda c: c.get("foo.y"), MAP["foo"]["y"]),
    ),
)
def test_get_present(operation: Callable, expected: Any) -> None:
    """
    Getting present paths returns the associated values.

    Arguments:
        operation: the operation to perform on the config instance.
        expected: the expected value of the operation.
    """
    with config() as c:
        queried = operation(c)

        assert queried == expected
        assert c == MAP


@parametrize(
    ("operation", "expected"),
    (
        (lambda c: c.get("quux"), None),
        (lambda c: c.get("foo.nonexistend", "mydefault"), "mydefault"),
    ),
)
def test_get_absent(operation: Callable, expected: Any) -> None:
    """
    Getting absent paths returns the default value.

    Arguments:
        operation: the operation to perform on the config instance.
        expected: the expected value of the operation.
    """
    with config() as c:
        queried = operation(c)

        assert queried == expected
        assert c == MAP


@parametrize(
    ("operation", "expected"),
    (
        (lambda c: c["foo"], MAP["foo"]),
        (lambda c: c["foo.bar"], MAP["foo"]["bar"]),
        (lambda c: c["foo.bar.baz"], MAP["foo"]["bar"]["baz"]),
        (lambda c: c["foo.x"], MAP["foo"]["x"]),
        (lambda c: c["foo.y"], MAP["foo"]["y"]),
    ),
)
def test_getitem_present(operation: Callable, expected: Any) -> None:
    """
    Lookup of present paths returns the associated value.

    Arguments:
        operation: the operation to perform on the config instance.
        expected: the expected value of the operation.
    """
    with config() as c:
        queried = operation(c)

        assert queried == expected
        assert c == MAP


@parametrize(
    "operation",
    (
        lambda c: c["quux"],
        lambda c: c["none.of.them.exist"],
    ),
)
def test_getitem_absent(operation: Callable) -> None:
    """
    Lookup of absent paths raises an error.

    Arguments:
        operation: the operation to perform on the config instance.
    """
    with config() as c, raises(KeyError):
        operation(c)


@parametrize(
    ("operation", "expected"),
    (
        #
        # existing
        #
        (
            lambda c: c.set("foo", "bar"),
            lambda m: m["foo"] == "bar",
        ),
        (
            lambda c: c.set("foo.x", "?"),
            lambda m: m["foo"]["x"] == "?",
        ),
        #
        # mixed
        #
        (
            lambda c: c.set("foo.new.from.here.on", "bar"),
            lambda m: m["foo"]["new"]["from"]["here"]["on"] == "bar",
        ),
        #
        # absent
        #
        (
            lambda c: c.set("quux", "blub"),
            lambda m: m["quux"] == "blub",
        ),
        (
            lambda c: c.set("none.of.them.exist", 42),
            lambda m: m["none"]["of"]["them"]["exist"] == 42,
        ),
    ),
)
def test_set(operation: Callable, expected: Callable) -> None:
    """
    Setting new paths creates mappings automatically if not present.

    Arguments:
        operation: the operation to perform on the config instance.
        expected: the check whether an operation gave the expected result.
    """
    with config() as c:
        # alter config
        operation(c)

        # perform check
        assert expected(dict(c))


@parametrize(
    ("operation", "expected"),
    (
        #
        # present keys
        #
        (lambda c: c.set("foo.bar.baz", "new", default=True), MAP["foo"]["bar"]["baz"]),
        (lambda c: c.set("foo.x", "new", default=True), MAP["foo"]["x"]),
        #
        # absent keys
        #
        (lambda c: c.set("quux", "new", default=True), "new"),
        (lambda c: c.set("foo.z", "new", default=True), "new"),
    ),
)
def test_set_default(operation: Callable, expected: Callable) -> None:
    """
    Setting the `default` flag to `True` returns a present value or the default.

    Arguments:
        operation: the operation to perform on the config instance.
        expected: the expected result of the operation.
    """
    with config() as c:
        assert operation(c) == expected


@parametrize(
    ("operation", "expected"),
    (
        #
        # present keys
        #
        (lambda c: c.setdefault("foo.bar.baz", "new"), MAP["foo"]["bar"]["baz"]),
        (lambda c: c.setdefault("foo.x", "new"), MAP["foo"]["x"]),
        #
        # absent keys
        #
        (lambda c: c.setdefault("quux", "new"), "new"),
        (lambda c: c.setdefault("foo.z", "new"), "new"),
    ),
)
def test_setdefault(operation: Callable, expected: Any) -> None:
    """
    The `setdefault` `dict` API works like `set(..., default=True)`.

    Arguments:
        operation: the operation to perform on the config instance.
        expected: the expected result of the operation.
    """
    with config() as c:
        assert operation(c) == expected


@parametrize(
    ("operation", "expected"),
    (
        (
            lambda c: c.set("foo.x.nonexistend", "?", overwrite=True),
            lambda m: m["foo"]["x"]["nonexistend"] == "?",
        ),
        (
            lambda c: c.set("foo.bar.baz.nonexistend", "?", overwrite=True),
            lambda m: m["foo"]["bar"]["baz"]["nonexistend"] == "?",
        ),
    ),
)
def test_set_intermediate_overwrite(operation: Callable, expected: Callable) -> None:
    """
    Setting a path overwrites intermediate mappings if the `overwrite` flag is given.

    Arguments:
        operation: the operation to perform on the config instance.
        expected: the expected result of the operation.
    """
    with config() as c:
        operation(c)

        assert expected(dict(c))


@parametrize(
    ("operation", "expected"),
    (
        (
            lambda c: c.set("foo.x.nonexistend", "?"),
            lambda m: m["foo"]["x"]["nonexistend"] == "?",
        ),
        (
            lambda c: c.set("foo.bar.baz.nonexistend", "?"),
            lambda m: m["foo"]["bar"]["baz"]["nonexistend"] == "?",
        ),
    ),
)
def test_set_intermediate_no_overwrite(operation: Callable, expected: Callable) -> None:
    """
    Setting a path by which a mapping would be overwritten raises an error.

    Arguments:
        operation: the operation to perform on the config instance.
        expected: the expected result of the operation.
    """
    with config() as c, raises(KeyError):
        operation(c)


@parametrize(
    ("operation", "expected"),
    (
        (
            lambda c: c.__delitem__("foo"),
            lambda m: set(m.keys()) == set(),
        ),
        (
            lambda c: c.__delitem__("foo.x"),
            lambda m: set(m["foo"].keys()) == {"bar", "y"},
        ),
    ),
)
def test_del(operation: Callable, expected: Callable) -> None:
    """
    Deleting a present path removes it from the mapping.

    Arguments:
        operation: the operation to perform on the config instance.
        expected: the expected result of the operation.
    """
    with config() as c:
        operation(c)

        assert expected(dict(c))


@parametrize(
    ("operation", "returned", "expected"),
    (
        (
            lambda c: c.pop("foo"),
            MAP["foo"],
            lambda m: set(m.keys()) == set(),
        ),
        (
            lambda c: c.pop("foo.x"),
            MAP["foo"]["x"],
            lambda m: set(m["foo"].keys()) == {"bar", "y"},
        ),
    ),
)
def test_pop_present_no_default(
    operation: Callable, returned: Any, expected: Callable
) -> None:
    """
    Popping a present path returns its value.

    Arguments:
        operation: the operation to perform on the config instance.
        returned: the return value of the operation.
        expected: the expected result of the operation.
    """
    with config() as c:
        assert operation(c) == returned

        assert expected(dict(c))


@parametrize(
    "operation",
    (
        lambda c: c.pop("nonexistend"),
        lambda c: c.pop("foo.does.not.exist"),
    ),
)
def test_pop_absent_no_default(operation: Callable) -> None:
    """
    Popping an absent path without giving a default value raises an error.

    Arguments:
        operation: the operation to perform on the config instance.
    """
    with config() as c, raises(KeyError):
        operation(c)


@parametrize(
    ("operation", "expected"),
    (
        (lambda c: c.pop("nonexistend", "mydefault"), "mydefault"),
        (lambda c: c.pop("foo.does.not.exist", "mydefault"), "mydefault"),
    ),
)
def test_pop_absent_default(operation: Callable, expected: Callable) -> None:
    """
    Popping an absent path gives back the specified default value.

    Arguments:
        operation: the operation to perform on the config instance.
        expected: the expected result of the operation.
    """
    with config() as c:
        assert operation(c) == expected


@parametrize(
    ("mapping", "expected"),
    (
        # empty
        (
            {},
            MAP,
        ),
        # 1st level key added
        (
            {
                "z": 1337,
            },
            {
                "foo": {"bar": {"baz": [1, 2, 3]}, "x": 1, "y": set(list("abc"))},
                "z": 1337,
            },
        ),
        # 2nd level key added
        (
            {
                "foo": {
                    "quux": "blub",
                },
            },
            {
                "foo": {
                    "bar": {"baz": [1, 2, 3]},
                    "x": 1,
                    "y": set(list("abc")),
                    "quux": "blub",
                }
            },
        ),
        # 3rd level key added
        (
            {
                "foo": {
                    "bar": {"quux": "blub"},
                },
            },
            {
                "foo": {
                    "bar": {"baz": [1, 2, 3], "quux": "blub"},
                    "x": 1,
                    "y": set(list("abc")),
                }
            },
        ),
        # merge deeply nested list
        (
            {
                "foo": {
                    "bar": {"baz": [4, 5, 6]},
                },
            },
            {
                "foo": {
                    "bar": {"baz": [1, 2, 3, 4, 5, 6]},
                    "x": 1,
                    "y": set(list("abc")),
                }
            },
        ),
        # merge deeply nested set
        (
            {
                "foo": {
                    "y": set([4, 5, 6]),
                },
            },
            {
                "foo": {
                    "bar": {"baz": [1, 2, 3]},
                    "x": 1,
                    "y": set(list("abc")) | set([4, 5, 6]),
                }
            },
        ),
        # overwrite existing value when not mergable
        (
            {
                "foo": {
                    "y": ["not", "a", "set", "anymore"],
                },
            },
            {
                "foo": {
                    "bar": {"baz": [1, 2, 3]},
                    "x": 1,
                    "y": ["not", "a", "set", "anymore"],
                }
            },
        ),
    ),
)
def test_merge(mapping: dict, expected: dict) -> None:
    """
    Merging means deeply merging with another mapping.

    Arguments:
        mapping: the mapping to merge in.
        expected: the config data after the deepmerge.
    """
    with config() as c:
        c.merge(mapping)
        assert c == expected
