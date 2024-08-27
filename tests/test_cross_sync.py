import pytest
from pycrdt import Doc, Text

STATE_ZERO = b"\x00\x00"


def get_state(doc, method):
    match method:
        # simulate a sync step 1 + sync step 2 synchronization
        case "get_state":
            return doc.get_state()
        # simulate a sync-step-2-only synchronization, skipping sync step 1
        case "state_zero":
            return STATE_ZERO


@pytest.mark.parametrize(
    "foo_state_method,bar_state_method",
    [
        ("get_state", "get_state"),  # symmetric
        ("state_zero", "state_zero"),  # symmetric
        ("get_state", "state_zero"),  # asymmetric
        ("state_zero", "get_state"),  # asymmetric
    ],
)
def test_cross_sync(foo_state_method, bar_state_method):
    callback_update = None

    def callback(event):
        nonlocal callback_update
        callback_update = event.update

    ##
    # init
    foo = Doc()
    foo_text = Text("foo")
    foo["text"] = foo_text

    bar = Doc()
    bar_text = Text("bar")
    bar["text"] = bar_text

    # the contents are as expected,
    # both YDocs contain a non-empty, but different history
    assert str(foo["text"]) == "foo" and str(bar["text"]) == "bar"

    ##
    # one-sided sync
    # foo gets update from bar
    foo_state = get_state(foo, foo_state_method)
    bar_update = bar.get_update(foo_state)
    foo.apply_update(bar_update)

    # now foo has the contents of bar,
    # bar remains unchanged
    assert str(foo["text"]) in ["foobar", "barfoo"]
    assert str(bar["text"]) == "bar"

    # save the actual state of foo_text
    # one of "foobar" or "barfoo"
    choice = str(foo["text"])

    ##
    # get a single callback update
    subscription = foo.observe(callback)
    foo_text += "baz"
    foo.unobserve(subscription)

    # foo gets updated with new content and the callback update is catched
    assert str(foo["text"]) == choice + "baz"
    assert callback_update is not None

    ##
    # apply callback update to other YDoc as the Provider classes also do
    bar.apply_update(callback_update)

    # nothing happens, the callback update has no effect
    assert str(bar["text"]) == "bar"

    ##
    # one-sided sync, now in the opposite way,
    # now bar gets update from foo
    bar_state = get_state(bar, bar_state_method)
    foo_update = foo.get_update(bar_state)
    bar.apply_update(foo_update)

    # bar is also now updated, the callback update is taken into account
    assert str(bar["text"]) == choice + "baz"
