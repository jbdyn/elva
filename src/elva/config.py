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
            raw: the underlying mapping treated as config.
        """
        if not isinstance(raw, Mapping):
            raise TypeError("provided config data is not a mapping")

        self.raw = raw
        self.chain = []

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

    def set(self, value: Any, *, overwrite: bool = True) -> None:
        """
        Set a config value.

        Missing mappings are created automatically.

        Arguments:
            value: the value to set for the given query chain.
            overwrite: if `True`, automatically overwrite intermediate keys with value
                not being mappings, else raise an `AttributeError`.
        """
        # alias
        current = self.raw
        chain = self.chain

        # checks
        if not isinstance(current, MutableMapping):
            raise TypeError("provided config data is not mutable")

        if not chain:
            raise AttributeError("no config keys specified")

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
        current[key] = value
