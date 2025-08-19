"""
Module with the awareness component definition.
"""

from typing import Any, Callable

from pycrdt import Awareness as _Awareness

from elva.component import Component, create_component_state

AwarenessState = create_component_state("AwarenessState")
"""The states of the [`Awareness`][elva.awareness.Awareness] component."""


class Awareness(Component, _Awareness):
    """
    Component version of `pycrdt`'s [`Awareness`][pycrdt.Awareness] class.
    """

    @property
    def client_states(self) -> dict:
        """The client states."""
        return self._states

    @property
    def states(self) -> AwarenessState:
        """The states this component can have."""
        return AwarenessState

    async def run(self):
        """
        Hook performing periodic awareness updates.
        """
        await self._start()

    async def cleanup(self):
        """
        Hook removing the local awareness state.
        """
        self.remove_awareness_states([self.client_id], origin="local")

    def observe(
        self, callback: Callable[[str, tuple[dict[str, Any], Any]], None]
    ) -> str:
        """
        Add a callback to be run on awareness state changes.

        Arguments:
            callback: the function to call on state changes.

        Returns:
            the observer identifier to use for [`unobserve`][elva.awareness.Awareness.unobserve].
        """
        observer_id = super().observe(callback)
        self.log.info(f"added observer {observer_id}")

        return observer_id

    def unobserve(self, observer_id: str):
        """
        Remove a registered callback.

        Arguments:
            observer_id: the identifier associated with the callback as given by [`observe`][elva.awareness.Awareness.observe].
        """
        super().unobserve(observer_id)
        self.log.info(f"removed observer {observer_id}")
