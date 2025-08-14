import json
from hashlib import md5

import pytest
from pycrdt import Doc, Map, Text, XmlElement, XmlFragment, XmlText

from elva.log import LOGGER_NAME
from elva.renderer import TextRenderer


@pytest.fixture(scope="module")
def manage_logger_name():
    reset_token = LOGGER_NAME.set(__name__)
    yield
    LOGGER_NAME.reset(reset_token)


# use the AnyIO plugin
pytestmark = pytest.mark.anyio


async def test_render_without_start(tmp_path):
    """The renderer does not permit writing without being active."""

    # setup path and content
    path = tmp_path / "test.txt"
    ytext = Text()

    # integrate into a YDoc
    ydoc = Doc()
    ydoc["text"] = ytext

    # instantiate the renderer
    renderer = TextRenderer(ytext, path)

    # not permitted to write when not active
    with pytest.raises(RuntimeError):
        await renderer.write()


async def test_render_ytext(tmp_path):
    """The YText data type is rendered properly."""

    # setup path and content
    path = tmp_path / "test.txt"

    content1 = "some content"
    ytext = Text(content1)

    # integrate the YText in a YDoc
    ydoc = Doc()
    ydoc["text"] = ytext

    # instantiate the renderer component
    renderer = TextRenderer(ytext, path)

    # the digest corresponds to the one of an empty string
    assert renderer.hash.digest() == md5(b"").digest()

    # run the renderer
    async with renderer:
        sub = renderer.subscribe()

        # it should save automatically as auto_save = True by default
        while renderer.states.SAVED not in renderer.state:
            await sub.receive()

        # the written content is indeed the one we put into the YText
        assert path.exists()
        with open(path, "r") as file:
            assert file.read() == content1

        # add content to YText
        content2 = r"\nand even more"
        ytext += content2

        # the renderer got notified and changed the state accordingly
        assert renderer.states.SAVED not in renderer.state

        # manually write as the timeout is 300s by default
        await renderer.write()

        # wait for component to signal the contents have been saved to file
        while renderer.states.SAVED not in renderer.state:
            await sub.receive()

        # again, the content is as expected
        with open(path, "r") as file:
            assert file.read() == content1 + content2

        # one last time changing content
        content3 = r"\nlast line"
        ytext += content3

        # the renderer recognized the change
        assert renderer.states.SAVED not in renderer.state

        # unsubscribe for good measure
        renderer.unsubscribe(sub)

    # the renderer ran the cleanup and should have written
    # the last line to file as auto_save = True
    with open(path, "r") as file:
        assert file.read() == content1 + content2 + content3


async def test_render_xml(tmp_path):
    """The XML data types are rendered properly."""
    # setup path and content
    path = tmp_path / "test.xml"
    frag = XmlFragment()

    # integrate the XML fragment in a YDoc
    ydoc = Doc()
    ydoc["tree"] = frag

    # add some XML content
    svg = frag.children.append(XmlElement("svg"))
    svg.children.append(XmlText("abc"))

    # run the renderer
    async with TextRenderer(frag, path) as renderer:
        sub = renderer.subscribe()

        # wait for the renderer to save the content to file
        while renderer.states.SAVED not in renderer.state:
            await sub.receive()

        # the file indeed exists and holds the expected content
        assert path.exists()
        with open(path, "r") as file:
            assert file.read() == "<svg>abc</svg>"

        # add another text element
        frag.children.append(XmlText("def"))

        # the renderer got notified and changed state
        assert renderer.states.SAVED not in renderer.state

        # write manually as the auto save loop takes too long
        await renderer.write()

        # wait for the renderer to write to file
        while renderer.states.SAVED not in renderer.state:
            await sub.receive()

        # we have our content written to file
        with open(path, "r") as file:
            assert file.read() == "<svg>abc</svg>def"

        # unsubscribe for good measure
        renderer.unsubscribe(sub)


async def test_get_content(tmp_path):
    """We can define how the content will be formatted."""

    class CustomContentRenderer(TextRenderer):
        def get_content(self):
            # returns `str(self.crdt)`
            repr = super().get_content()

            # we need to load the string to get the correct format
            content = json.loads(repr)

            # now we can dump the string as desired;
            # sort the keys for consistency across tests
            return json.dumps(content, indent=4, sort_keys=True)

    # setup path and content
    path = tmp_path / "test.json"
    map = Map(
        {
            "a": 1,
            "c": {
                "u": "v",
                "x": "y",
            },
            "b": 2,
        }
    )

    # integrate into a YDoc
    ydoc = Doc()
    ydoc["map"] = map

    # run the renderer
    async with CustomContentRenderer(map, path) as renderer:
        sub = renderer.subscribe()

        # wait for the renderer to save the contents to file
        while renderer.states.SAVED not in renderer.state:
            await sub.receive()

        # define what to expect from reading the file
        # this seems visually correct, but we need to remove
        # erroneously introduced whitespaces
        expected = """
        {
            "a": 1,
            "b": 2,
            "c": {
                "u": "v",
                "x": "y"
            }
        }
        """

        # remove leading and trailing newline
        expected_lines = expected.rstrip().splitlines(keepends=True)[1:]

        # dedent
        expected = "".join(line.removeprefix(" " * 8) for line in expected_lines)

        # we have our indented JSON file
        with open(path, "r") as file:
            assert file.read() == expected

        # unsubscribe for good measure
        renderer.unsubscribe(sub)


async def test_rapid_change_auto_save(tmp_path):
    """The `auto_save` property can be toggled rapidly."""
    # setup path and content
    path = tmp_path / "test.txt"
    ytext = Text()

    # integrate the YText into a YDoc
    ydoc = Doc()
    ydoc["text"] = ytext

    async with TextRenderer(ytext, path) as renderer:
        sub = renderer.subscribe()
        while renderer.states.SAVED not in renderer.state:
            await sub.receive()

        for _ in range(10):
            await renderer.set_auto_save(False)
            await renderer.set_auto_save(True)

        renderer.unsubscribe(sub)


async def test_auto_save(tmp_path):
    """The auto save loop is started and stopped on changing the `auto_save` property."""
    # setup path and content
    path = tmp_path / "test.txt"
    ytext = Text()

    # integrate the YText into a YDoc
    ydoc = Doc()
    ydoc["text"] = ytext

    class AskingTextRenderer(TextRenderer):
        """
        TextRenderer subclass with a flag whether its
        `confirm` method has been called on cleanup.
        """

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.asked_for_confirmation = False

        async def confirm(self):
            self.asked_for_confirmation = True
            return True

    # set the timeout to 0 to see changes in the auto save loop immediately
    timeout = 0

    # instantiate the renderer component
    renderer = AskingTextRenderer(ytext, path, auto_save=False, timeout=timeout)

    # run the renderer
    async with renderer:
        sub = renderer.subscribe()

        # not saved anything yet
        assert renderer.states.SAVED not in renderer.state

        # add content, triggering the crdt event callback
        line1 = "line1"
        ytext += line1

        # still not saved
        assert renderer.states.SAVED not in renderer.state

        # also, no file exists yet, but should have been existed by now if
        # auto_save was True
        assert not path.exists()

        # now enable auto save
        await renderer.set_auto_save(True)

        # wait for the component to start the loop and writing to file
        while renderer.states.SAVED not in renderer.state:
            await sub.receive()

        # we saved the current YText content
        assert renderer.states.SAVED in renderer.state

        # the file also exists and holds the expected content
        with open(path, "r") as file:
            assert file.read() == line1

        # turn off auto_save
        await renderer.set_auto_save(False)

        # make some changes
        line2 = r"\nline2"
        ytext += line2

        # still not saved the last changes
        assert renderer.states.SAVED not in renderer.state

        # the file is still the old one
        with open(path, "r") as file:
            assert file.read() == line1

        # unsubscribe for good measure
        renderer.unsubscribe(sub)

    # the renderer has stopped and called its `cleanup` method
    # which in turn runs the renderer's `confirm` method
    assert hasattr(renderer, "asked_for_confirmation")
    assert renderer.asked_for_confirmation

    # as the renderer's `confirm` method returns `True`,
    # the latest changes are visible in the file as well
    with open(path, "r") as file:
        assert file.read() == line1 + line2
