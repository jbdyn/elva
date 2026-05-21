from collections.abc import Mapping, MutableMapping, Sequence
from copy import deepcopy
from typing import Any, Literal

from deepmerge import always_merger

deepmerge = always_merger.merge
"""Deepmerge two mappings."""


class Undefined:
    """
    Object representing an undefined value.
    """

    def __repr__(self) -> str:
        """
        Get the string representation.

        Returns:
            the string representation.
        """
        return "<undefined>"


class Config(dict):
    """
    Dictionary with config path lookup.
    """

    def __str__(self) -> str:
        """
        Get the string value.

        Returns:
            the string value of the config data.
        """
        return super().__repr__()

    def __repr__(self) -> str:
        """
        Get the string representation.

        Returns:
            the string representation of this config.
        """
        return f"{self.__class__.__name__}({super().__repr__()})"

    @property
    def delimiter(self) -> Literal["."]:
        """
        The delimiter of keys in a config path.
        """
        return "."

    def path(self, keys: Sequence[str]) -> str:
        """
        Get the config path for a sequence of keys.

        Arguments:
            keys: the keys to join to a config path.

        Returns:
            the config path.
        """
        return self.delimiter.join(keys)

    def get(
        self,
        path: str,
        default: Any = None,
        strict: bool = False,
    ) -> Any:
        """
        Get the value to the given path.

        Arguments:
            path: the config path to query.
            default: the value to return when the given path is absent.
            strict: if `True`, raise a `KeyError` on lookup errors.

        Raises:
            KeyError: if `strict` is `True` and a lookup error occurred.

        Returns:
            the value of a present path or the default when the path is absent.
        """
        items = path.split(self.delimiter)
        nitems = len(items)

        # start on superclass
        out = super()

        try:
            for i, item in enumerate(items):
                if strict:
                    out = out.__getitem__(item)
                else:
                    out = out.get(
                        item,
                        {} if i != nitems - 1 else default,
                    )

            return out
        except (KeyError, AttributeError, TypeError):
            if strict:
                raise KeyError(item) from None
            else:
                return default

    def set(
        self,
        path: str,
        value: Any,
        overwrite: bool = False,
        default: bool = False,
    ) -> Any:
        """
        Set a path to a given value.

        Arguments:
            path: the config path.
            value: the value to associate with the path.
            overwrite:
                if `True`, overwrite intermediate non-mappings to mappings,
                else raise a `KeyError`.
            default:
                if `True`, return the value of a present path or set it to the
                given value, else just set the value.

        Raises:
            KeyError:
                if `overwrite` is `True` and an intermediate non-mapping would
                be overwritten to a mapping.

        Returns:
            if `default` is `True`, the value of a present path or `None`, else
            `None`.
        """
        *items, last = path.split(self.delimiter)

        # start on superclass
        current = super()

        for item in items:
            out = current.setdefault(item, {})

            if not isinstance(out, MutableMapping):
                if overwrite:
                    out = {}
                    current.__setitem__(item, out)
                else:
                    raise KeyError(f"would overwrite mapping under config key {item}")

            current = out

        # set the value in the innermost mapping under `key`
        if default:
            return current.setdefault(last, value)
        else:
            current.__setitem__(last, value)

    def pop(self, path: str, default: Any = Undefined()) -> Any:
        """
        Remove a present path and return the value, else return the default if explicitely given.

        Arguments:
            path: the path to remove.
            default: the value to return if the path is absent.

        Raises:
            KeyError: if the given path is absent and `default` was not explicitely given.

        Returns:
            the value of a present path or the default if explicitely given.
        """
        *items, last = path.split(self.delimiter)

        # start on superclass
        current = super()

        try:
            for item in items:
                current = current.__getitem__(item)

            item = last

            return current.pop(last)
        except (KeyError, AttributeError, TypeError):
            if type(default) is Undefined:
                raise KeyError(item)
            else:
                return default

    def __contains__(self, path: str) -> bool:
        """
        Check for presence of a path.

        Arguments:
            path: the path to check presence for.

        Returns:
            `True` if the path is present, else `False`.
        """
        *items, last = path.split(self.delimiter)

        # start on superclass
        current = super()

        try:
            for item in items:
                current = current.__getitem__(item)

            return current.__contains__(last)
        except (KeyError, AttributeError, TypeError):
            return False

    def __getitem__(self, path: str) -> Any:
        """
        Lookup the value to a given path.

        Arguments:
            path: the path to query.

        Returns:
            the value of a present path.
        """
        return self.get(path, strict=True)

    def __setitem__(self, path: str, value: Any) -> None:
        """
        Set a value to a given path.

        Overwrite intermediate non-mappings to mappings if necessary.

        Arguments:
            path: the path to insert or update.
            value: the value associated with the path.
        """
        self.set(path, value, overwrite=True, default=False)

    def setdefault(self, path: str, default: Any) -> Any:
        """
        Get the value of a present path or insert the default if the path is absent.

        Arguments:
            path: the path to query or set the default value to.
            default: the value to set when the given path is absent.

        Returns:
            the path of a present value or the default if the path is absent.
        """
        return self.set(path, default, overwrite=True, default=True)

    def __delitem__(self, path: str) -> None:
        """
        Delete a present path.

        Arguments:
            path: the path to remove.
        """
        self.pop(path)

    def merge(self, other: Mapping) -> None:
        """
        Deepmerge with a given mapping.

        Arguments:
            other: the new config data to deepmerge in.
        """
        self.update(deepmerge(self, other))

        # enable chaining and ad-hoc referencing
        return self

    def deepcopy(self) -> dict:
        """
        Get a deep copy of the config data.

        Returns:
            a deep copy of the config data.
        """
        return deepcopy(self)


def clean(mapping: MutableMapping) -> None:
    """
    Clean a config mapping from empty containers and `None` values.

    Nested mappings are clean recursively.

    Arguments:
        mapping: the mapping to clean.
    """
    for key, value in mapping.copy().items():
        if value is None or (type(value) in (list, tuple, dict) and len(value) == 0):
            mapping.pop(key)
        elif isinstance(value, dict):
            clean(value)

            if len(value) == 0:
                mapping.pop(key)


def convert(item: Any) -> Any:
    """
    Make an item TOML-serializable.

    Containers are converted recursively.

    Arguments:
        item: the item to convert.

    Returns:
        the TOML-serializable conversion of the given item.
    """
    if isinstance(item, Sequence) and not isinstance(item, str):
        return list(convert(i) for i in item)
    elif isinstance(item, Mapping):
        return dict((key, convert(i)) for key, i in item.items())
    elif type(item) not in (str, bool, int, float):
        return str(item)
    else:
        return item
