"""
Module holding renderer components.
"""

from hashlib import md5

from anyio import TASK_STATUS_IGNORED, CancelScope, Path, open_file, sleep
from anyio.abc import TaskStatus
from pycrdt import (
    Array,
    ArrayEvent,
    Map,
    MapEvent,
    Text,
    TextEvent,
    XmlElement,
    XmlEvent,
    XmlFragment,
    XmlText,
)

from elva.component import Component, create_component_state

TextRendererState = create_component_state("TextRendererState", ("SAVED",))
"""The states of the [`TextRenderer`][elva.renderer.TextRenderer] component."""


class TextRenderer(Component):
    """
    Component rendering Y text data types to text files.
    """

    crdt: Text
    """Instance of a Y text data type."""

    path: Path
    """Path where to store the rendered text file."""

    timeout: int
    """the time seconds between two consecutive periodic writes."""

    _auto_save: bool
    """Flag whether to render to text file on hook execution."""

    _auto_save_scope: CancelScope
    """(while auto saving) Scope of the auto save loop."""

    def __init__(
        self,
        crdt: Text | Array | Map | XmlFragment | XmlElement | XmlText,
        path: str,
        auto_save: bool = True,
        timeout: int = 300,
    ):
        """
        Arguments:
            crdt: instance of a Y CRDT.
            path: the filepath to write content to.
            auto_save: flag whether to write repeatedly and on cleanup (`True`) or not (`False`).
            timeout: the time in seconds between two consecutive periodic writes.
        """
        self.crdt = crdt
        self.path = Path(path)
        self._auto_save = auto_save
        self.timeout = timeout
        self.hash = md5()

    @property
    def states(self) -> TextRendererState:
        """
        The states this component can have.
        """
        return TextRendererState

    @property
    def auto_save(self) -> bool:
        """
        Flag whether to write repeatedly and on cleanup (`True`) or not (`False`).
        """
        return self._auto_save

    async def set_auto_save(self, auto_save: bool):
        """
        Set the auto save flag.

        This method is idempotent, i.e. it does not change the state when
        setting `auto_save` to the current value.

        Arguments:
            auto_save: flag whether to write repeatedly and on cleanup (`True`) or not (`False`).
        """
        # we need to define this mechanism as async method as opposed to
        # property setter because we need to await the definition of the
        # _auto_save_scope attribute.

        # obey idempotence
        if auto_save != self._auto_save:
            if auto_save:
                # start the auto save loop, thereby creating the
                # auto save scope
                await self._task_group.start(self._run_auto_save)
            else:
                # cancel and delete auto save scope
                self._auto_save_scope.cancel()
                del self._auto_save_scope
                self.log.info("disabled auto save")

            # update the corresponding private attribute
            self._auto_save = auto_save

    async def _run_auto_save(self, task_status: TaskStatus[None] = TASK_STATUS_IGNORED):
        """
        Hook running the write loop in a dedicated cancel scope
        """
        with CancelScope() as self._auto_save_scope:
            self.log.info("enabled auto save")

            # signal that the task has started and `_auto_save_scope` is defined
            task_status.started()

            while True:
                # start with a write, so we save immediatly on startup
                await self.write()
                await sleep(self.timeout)

    def _on_crdt_event(self, event: TextEvent | ArrayEvent | MapEvent | XmlEvent):
        """
        Hook called on a CRDT event.

        It compares hashes of the current and the saved content and manages the `SAVED` state accordingly.
        It does not write to file.

        Arguments:
            event: object holding update information.
        """
        # get content after as it would be written to file
        content = self.get_content()

        # copy the hash algorithm (and included content)
        hash = self.hash.copy()

        # update the copied hash
        hash.update(content.encode())

        if hash.digest() != self.hash.digest():
            # the new content differs from the one on the last write;
            # remove the `SAVED` state
            self._change_state(self.states.SAVED, self.states.NONE)
        else:
            # both contents are the same;
            # ensure the `SAVED` state is set
            self._change_state(self.states.NONE, self.states.SAVED)

    async def before(self):
        """
        Hook run after the component adds the `ACTIVE` state and before it adds the `RUNNING` state.
        """
        self._subscription = self.crdt.observe(self._on_crdt_event)

    async def run(self):
        """
        Hook run after the component adds the `RUNNING` state.

        The contents of `self.crdt` get rendered to file if [`auto_save`][elva.renderer.TextRenderer.auto_save] is `True`.
        """
        if self.auto_save:
            await self._task_group.start(self._run_auto_save)

    async def cleanup(self):
        """
        Hook after the component has been cancelled.

        The contents of `self.crdt` get rendered to file if [`auto_save`][elva.renderer.TextRenderer.auto_save] is `True`.
        """
        # unobserve to avoid transactions failures
        if hasattr(self, "_subscription"):
            self.crdt.unobserve(self._subscription)
            del self._subscription

        # maybe one final write before stopping this component
        if self.auto_save or await self.confirm():
            await self.write()

    async def write(self):
        """
        Render the contents of [`crdt`][elva.renderer.TextRenderer.crdt] to file.
        """
        # it does not make sense to write without having the component started,
        # the `SAVED` state wouldn't get updated and writes not performed
        if self.states.ACTIVE not in self.state:
            raise RuntimeError(f"{self} not active")

        # no need to write anything if saved already;
        # it should be rather safe to rely on the component's `SAVED` state as the
        # subscription callback handles it on updates.
        if self.states.SAVED not in self.state:
            # write content
            async with await open_file(self.path, "w") as file:
                content = self.get_content()
                await file.write(content)

            # wait for the file closing to finish;
            # now we can run calls after finish
            self.log.info(f"wrote to file {self.path}")

            # update the hash of the freshly written content
            self.hash.update(content.encode())
            self.log.debug(f"updated hash to {self.hash.hexdigest()}")

            # update state
            self._change_state(self.states.NONE, self.states.SAVED)

    def get_content(self) -> str:
        """
        Logic for manipulating the content of the given Y CRDT.
        The returned string will be written to file.

        Overwrite this method to run custom content manipulation.

        By default, it calls `str(self.crdt)`.
        """
        return str(self.crdt)

    async def confirm(self) -> bool:
        """
        Hook called on cleanup when [`auto_save`][elva.renderer.TextRenderer.auto_save] is off.

        Overwrite this method to run custom confirmation logic.

        By default, it returns `False`.
        """
        return False
