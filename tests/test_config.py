from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Callable, Generator, Iterator

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
def test_str(mapping):
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
def test_repr(mapping):
    """
    Evaluating the string representation with `eval` gives an equal `Config`.

    Arguments:
        mapping: the mapping to get a config representation from.
    """
    config = Config(mapping)
    assert eval(repr(config)) == config


@parametrize(
    "mapping",
    (
        {},
        MAP,
    ),
)
def test_len(mapping):
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
def test_eq(mapping):
    """
    `Config`s are equal when their config data are equal.

    Arguments:
        mapping: the mapping to compare for equality.
    """
    assert Config(mapping) == Config(mapping)


@parametrize(
    ("left", "right"),
    (
        ({}, MAP),
        (MAP, {}),
        ({"foo": "bar"}, {"baz": 42}),
    ),
)
def test_ne(left, right):
    """
    `Config`s are not equal when their config data are not equal.

    Arguments:
        left: the left mapping to compare for unquality.
        right: the right mapping to compare for unquality.
    """
    assert Config(left) != Config(right)


@parametrize(
    ("mapping", "key"),
    (
        ({"foo": "bar"}, "foo"),
        ({"x": "y"}, "x"),
    ),
)
def test_contains(mapping, key):
    """
    A key is present when the key is present in the config data.

    Arguments:
        mapping: the mapping to test for.
        key: the key to check for presence.
    """
    assert key in mapping
    assert key in Config(mapping)


@parametrize(
    ("mapping", "key"),
    (
        ({}, "foo"),
        ({"baz": "quux"}, "foo"),
    ),
)
def test_not_contains(mapping, key):
    """
    A key is not present when the key is not present in the config data.

    Arguments:
        mapping: the mapping to test for.
        key: the key to check for absence.
    """
    assert key not in mapping
    assert key not in Config(mapping)


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
        c = Config(deepcopy(mapping))
        yield c
    finally:
        del c


@parametrize(
    ("query", "expected"),
    (
        #
        # all
        #
        (lambda c: c.raw, MAP),
        (lambda c: c.get(), MAP),
        #
        # existing
        #
        (lambda c: c.foo.get(), MAP["foo"]),
        (lambda c: c.foo.bar.get(), MAP["foo"]["bar"]),
        (lambda c: c.foo.bar.baz.get(), MAP["foo"]["bar"]["baz"]),
        (lambda c: c.foo.x.get(), MAP["foo"]["x"]),
        (lambda c: c.foo.y.get(), MAP["foo"]["y"]),
        #
        # absent
        #
        (lambda c: c.quux.get(), None),
        (lambda c: c.quux.get("mydefault"), "mydefault"),
        (lambda c: c.none.of.them.exist.get(), None),
    ),
)
def test_get(query: Callable, expected: Any) -> None:
    """
    Getting config values works via attributes and never throws an exception.

    Arguments:
        query: the query for a value.
        expected: the expected value of the query.
    """
    with config() as c:
        queried = query(c)

        assert queried == expected
        assert c.raw == MAP


def test_set_no_keys_no_mapping():
    """
    Setting the root config data can only be done with a mapping.
    """
    with config() as c, raises(TypeError):
        c.set("not a mapping")


@parametrize(
    ("operation", "expected"),
    (
        #
        # no keys chained
        #
        (
            # new value, i.e. root, needs to be a mapping
            lambda c: c.set({"bli": "bla"}),
            lambda m: (m["bli"] == "bla" and len(m) == 1),
        ),
        #
        # existing
        #
        (
            lambda c: c.foo.set("bar"),
            lambda m: (m["foo"] == "bar"),
        ),
        (
            lambda c: c.foo.x.set("?"),
            lambda m: (m["foo"]["x"] == "?"),
        ),
        #
        # mixed
        #
        (
            lambda c: c.foo.this.being.random.set("bar"),
            lambda m: (m["foo"]["this"]["being"]["random"] == "bar"),
        ),
        (
            lambda c: c.foo.x.nonexistend.set("?"),
            lambda m: (m["foo"]["x"]["nonexistend"] == "?"),
        ),
        #
        # absent
        #
        (
            lambda c: c.quux.set("blub"),
            lambda m: (m["quux"] == "blub"),
        ),
        (
            lambda c: c.none.of.them.exist.set(42),
            lambda m: (m["none"]["of"]["them"]["exist"] == 42),
        ),
    ),
)
def test_set(operation: Callable, expected: Callable) -> None:
    """
    Setting config values overwrites existing ones and creates missing
    mappings automatically.

    Arguments:
        operation: the operation to perform on the config instance.
        expected: the check whether an operation gave the expected result.
    """
    with config() as c:
        # alter config
        operation(c)

        # check that the chain has been reset
        assert len(c.chain) == 0

        # perform check
        assert expected(c.raw)


@parametrize(
    ("operation", "expected"),
    (
        #
        # no keys
        #
        (lambda c: c.set("new", default=True), MAP),
        #
        # present keys
        #
        (lambda c: c.foo.bar.baz.set("new", default=True), MAP["foo"]["bar"]["baz"]),
        (lambda c: c.foo.x.set("new", default=True), MAP["foo"]["x"]),
        #
        # absent keys
        #
        (lambda c: c.quux.set("new", default=True), "new"),
        (lambda c: c.foo.z.set("new", default=True), "new"),
    ),
)
def test_set_default(operation, expected):
    """
    When `default` is `True`, return a present key and set an absent key.

    Arguments:
        operation: the operation to perform on the config instance.
        expected: the expected result of the operation.
    """
    with config() as c:
        assert operation(c) == expected


@parametrize(
    "data",
    (
        None,
        1,
        3.14,
        list("abc"),
        set(list("abc")),
        tuple("abc"),
    ),
)
def test_wrong_data_type(data: None | int | float | list | set | tuple) -> None:
    """
    Raw config values other than mappings throw an exception.

    Arguments:
        data: the data config value.
    """
    with raises(TypeError):
        Config(data)


def test_read_only():
    """
    Setting values on read-only mappings fails.
    """

    class ReadOnlyMapping(Mapping):
        """
        A `Mapping` and not a `MutableMapping`.
        """

        def __init__(self, raw: Mapping) -> None:
            assert isinstance(raw, Mapping)

            self.raw = raw

        def __getitem__(self, item: str) -> Any:
            return self.raw[item]

        def __iter__(self) -> Iterator:
            return iter(self.raw)

        def __len__(self) -> int:
            return len(self.raw)

    # instantiate
    ro = ReadOnlyMapping(MAP)

    with config(ro) as c:
        # getting values work
        assert c.foo.get() == MAP["foo"]
        assert c.foo.bar.get() == MAP["foo"]["bar"]

        # setting values fails as the given mapping does not support
        with raises(TypeError):
            c.a.b.c.set("something")

        # the chain got reset despite the error
        assert len(c.chain) == 0


@parametrize(
    "operation",
    (
        # `x`, `y` and `baz` don't point to mappings and would be set to a mapping
        lambda c: c.foo.x.new.set("not allowed", overwrite=False),
        lambda c: c.foo.y.new.set("not allowed", overwrite=False),
        lambda c: c.foo.bar.baz.new.set("not allowed", overwrite=False),
    ),
)
def test_overwrite_protection(operation: Callable) -> None:
    """
    Disabling overwriting raises exceptions when key with non-mapping value
    would get overwritten.

    Arguments:
        operation: the operation to perform on the config instance.
    """
    with config() as c, raises(AttributeError):
        operation(c)
