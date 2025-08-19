"""
Selection definition.
"""

from typing import Callable, Self, TypeVar

from textual.widgets.text_area import Selection as _Selection

# define type variables for return values of the `on_selection` and `on_tuple` hooks
S = TypeVar("S")
T = TypeVar("T")


class Selection(_Selection):
    """
    An extended selection object supporting comparison.

    The implementation eases comparing to locations and other selections.
    """

    start: tuple
    """The start location of the selection. Not necessarily the top one."""

    end: tuple
    """The end location of the selection. Not necessarily the bottom one."""

    @property
    def top(self) -> tuple:
        """
        The minimum of end and start location of the selection.
        """
        return min(self.start, self.end)

    @property
    def bottom(self) -> tuple:
        """
        The maximum of end and start location of the selection.
        """
        return max(self.start, self.end)

    def _on_type(
        self,
        obj: tuple | Self,
        on_selection: Callable[[], S],
        on_tuple: Callable[[], T],
    ) -> S | T:
        """
        Perform defined actions depending on the type of the object to compare to.

        Arguments:
            obj: the object to compare to.
            on_selection: the object to call when `obj` is a [`Selection`][elva.widgets.ytextarea.Selection].
            on_tuple: the object to call when `obj` is an instance of [`tuple`][tuple].

        Raises:
            TypeError: if `obj` is not an instance of [`tuple`][tuple].

        Returns:
            the return value of either `on_selection` or `on_tuple`.
        """
        if type(obj) is type(self):
            # `obj` is of the *exact* same type as `self`
            return on_selection()
        elif isinstance(obj, tuple):
            # `obj` is a type of or of subtype of `tuple`
            return on_tuple()
        else:
            # something else was passed
            raise TypeError(
                (
                    "comparison not supported between instances of "
                    f"'{type(self)}' and '{type(obj)}'"
                )
            )

    def __contains__(self, obj: tuple | Self) -> bool:
        """
        Hook called on the `in` operator.

        Arguments:
            obj: the object to compare to.

        Raises:
            TypeError: if `obj` is not an instance of [`tuple`][tuple].

        Returns:
            `True` if the tuple or selection is within the top and bottom location of this selection, else `False`.
        """
        return self.top <= obj <= self.bottom

    def __gt__(self, obj: tuple | Self) -> bool:
        """
        Hook called on the `>` operator.

        Arguments:
            obj: the object to compare to.

        Raises:
            TypeError: if `obj` is not an instance of [`tuple`][tuple].

        Returns:
            `True` if the tuple or selection is before the top location, else `False`.
        """
        return self._on_type(
            obj,
            lambda: obj.bottom < self.top,
            lambda: obj < self.top,
        )

    def __ge__(self, obj: tuple | Self) -> bool:
        """
        Hook called on the `>=` operator.

        Arguments:
            obj: the object to compare to.

        Raises:
            TypeError: if `obj` is not an instance of [`tuple`][tuple].

        Returns:
            `True` if the tuple or selection is before or equal to the top location, else `False`.
        """
        return self._on_type(
            obj,
            lambda: obj.bottom <= self.top,
            lambda: obj <= self.top,
        )

    def __lt__(self, obj: tuple | Self) -> bool:
        """
        Hook called on the `<` operator.

        Arguments:
            obj: the object to compare to.

        Raises:
            TypeError: if `obj` is not an instance of [`tuple`][tuple].

        Returns:
            `True` if the tuple or selection is after the bottom location, else `False`.
        """
        return self._on_type(
            obj,
            lambda: self.bottom < obj.top,
            lambda: self.bottom < obj,
        )

    def __le__(self, obj: tuple | Self) -> bool:
        """
        Hook called on the `<=` operator.

        Arguments:
            obj: the object to compare to.

        Raises:
            TypeError: if `obj` is not an instance of [`tuple`][tuple].

        Returns:
            `True` if the tuple or selection is after or equal to the bottom location, else `False`.
        """
        return self._on_type(
            obj,
            lambda: self.bottom <= obj.top,
            lambda: self.bottom <= obj,
        )

    def __eq__(self, obj: tuple | Self) -> bool:
        """
        Hook called on the `==` operator.

        Arguments:
            obj: the object to compare to.

        Returns:
            `True` if the start and end locations are the same, else `False`.
        """
        if type(obj) is type(self):
            return obj.start == self.start and obj.end == self.end
        else:
            return False

    def __ne__(self, obj: Self) -> bool:
        """
        Hook called on the `!=` operator.

        Arguments:
            obj: the object to compare to.

        Returns:
            `False` if start and end locations are the same, else `True`.
        """
        return not self == obj
