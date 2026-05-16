from collections.abc import Mapping, MutableMapping
from typing import Any, Self


class Config:
    """
    Alternative API for mappings with attribute access rather than subscription.
    """

    raw: Mapping | MutableMapping
    """The underlying mapping providing the config data."""

    chain: list
    """The chained attributes used as the data query."""

    def __init__(self, raw: Mapping | MutableMapping) -> None:
        """
        Arguments:
            raw: the underlying config data.
        """
        if not isinstance(raw, Mapping):
            raise TypeError("provided config data is not a mapping")

        self.raw = raw
        self.chain = []

    def __str__(self) -> str:
        """
        Get the string value of this config.

        Returns:
            the string value of the config data.
        """
        return str(self.raw)

    def __repr__(self) -> str:
        """
        Get the string representation of this config.

        Returns:
            the string representation of the config data.
        """
        return f"{self.__class__.__name__}({repr(self.raw)})"

    def __len__(self) -> int:
        """
        Get the length of this config.

        Returns:
            the number of keys in the config data.
        """
        return len(self.raw)

    def __eq__(self, other: Self) -> bool:
        """
        Check whether this config is equal to another.

        Returns:
            `True` if the config data is equal to the other config data,
            else `False`.
        """
        return self.raw == other.raw

    def __ne__(self, other: Self) -> bool:
        """
        Check whether this config is not equal to another.

        Returns:
            `True` if the config data are not equal to the other config data,
            else `False`.
        """
        return self.raw != other.raw

    def __contains__(self, key: Any) -> bool:
        """
        Check whether a key is present in this config.

        Returns:
            `True` if the key is present in the config data, else `False`.
        """
        return key in self.raw

    def __getattr__(self, attr: str) -> Self:
        """
        Called on attributes not already present on the object.

        It appends the attribute to the query chain.

        Arguments:
            attr: the attribute given.

        Returns:
            the config object itself.
        """
        self.chain.append(attr)

        return self

    def reset(self) -> Self:
        """
        Reset the config query chain.

        Returns:
            the config object itself.
        """
        self.chain.clear()

        return self

    def get(self, default: Any = None) -> Any:
        """
        Retrieve a config value or get a default.

        Arguments:
            default: the value to return when no config value was found.

        Returns:
            the config value if present or the given default otherwise.
        """
        # alias
        current = self.raw
        chain = self.chain

        # check whether no attributes are present
        if not chain:
            return current

        # split and reset attribute chain
        *path, key = chain

        self.reset()

        # query mappings
        for attr in path:
            current = current.get(attr)

            if not isinstance(current, Mapping):
                # ensure mapping
                current = {}

                break

        # query the innermost mapping for the `key`
        return current.get(key, default)

    def set(self, value: Any, *, overwrite: bool = True, default: bool = False) -> Any:
        """
        Set a config value.

        Missing mappings are created automatically.

        Arguments:
            value: the value to set for the given query chain.
            overwrite:
                if `True`, automatically overwrite intermediate keys with value
                not being mappings, else raise an `AttributeError`.
            default:
                if `True`, return the value of a present key or set an absent
                key to the given value. Compare to `dict.setdefault`.

        Raises:
            TypeError: when the config data are not mutable.
            AttributeError: when no keys where chained.

        Returns:
            None or the present key's value if `default` is `True`.
        """
        # alias
        current = self.raw
        chain = self.chain

        # checks
        if not isinstance(current, MutableMapping):
            self.reset()

            raise TypeError("provided config data is not mutable")

        if not chain:
            if default:
                return current
            else:
                if not isinstance(value, Mapping):
                    raise TypeError("given value is not a mapping")
                else:
                    current.clear()
                    current.update(value)
                    return

        # split and reset attribute chain
        *path, key = chain

        self.reset()

        # query mappings
        for attr in path:
            out = current.setdefault(attr, {})

            if not isinstance(out, Mapping):
                if overwrite:
                    current[attr] = out = {}
                else:
                    raise AttributeError(
                        f"would overwrite mapping under config key {attr}"
                    )

            current = out

        # set the value in the innermost mapping under `key`
        if default:
            return current.setdefault(key, value)
        else:
            current[key] = value
