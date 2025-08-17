from typing import Literal

import pytest

from elva.protocol import (
    ElvaMessage,
    YMessage,
    prepend_var_uint,
    read_var_uint,
    strip_var_uint,
    write_var_uint,
)

STATE_ZERO = b"\x00"
"""State of a Y document directly after initialization."""

EMPTY = b"\x00\x00"
"""Payload of an empty update."""


def get_protocol_class(name: Literal["y", "elva"]) -> YMessage | ElvaMessage:
    """
    Get the protocol class for a given protocol name.

    Arguments:
        name: the protocol name.

    Returns:
        the class defining the protocol.
    """
    match name:
        case "y":
            Message = YMessage
        case "elva":
            Message = ElvaMessage

    return Message


@pytest.mark.parametrize(
    ("num", "expected"),
    (
        (0, [0]),
        (128, [128, 1]),
        (256, [128, 2]),
        (16384, [128, 128, 1]),
        (2097152, [128, 128, 128, 1]),
    ),
)
def test_write_and_read_var_uint(num, expected):
    """Encode to and decode from a variable unsigned integer."""
    # encode
    res = write_var_uint(num)
    assert res == expected

    # decode
    data = bytes(res)
    uint, byte_idx = read_var_uint(data)
    assert uint == num
    assert byte_idx == len(expected)


@pytest.mark.parametrize(
    ("payload_in", "expected"),
    (
        (b"", b"\x00"),
        (STATE_ZERO, b"\x01" + STATE_ZERO),
        (bytes(42), b"\x2a" + bytes(42)),
        (bytes(200), b"\xc8\x01" + bytes(200)),
    ),
)
def test_prepend_and_strip_var_uint(payload_in, expected):
    """Prepend and strip a variable unsigned integer to or from a payload, respectively."""
    # prepend
    message_out, length = prepend_var_uint(payload_in)
    assert message_out == expected
    assert length == len(payload_in)

    # strip
    payload_out, length = strip_var_uint(message_out)
    assert payload_out == payload_in
    assert length == len(message_out)


def test_strip_var_uint_overshooting_length():
    """Strip a message with an overshooting length."""
    MSG = b"\x0a"
    payload_out, length = strip_var_uint(MSG)
    assert payload_out == b""
    assert length == len(MSG)


@pytest.mark.parametrize(
    ("protocol", "protocol_name", "types"),
    (
        ("y", "YMessage", YMessage.get_types()),
        ("elva", "ElvaMessage", ElvaMessage.get_types()),
    ),
)
def test_message_type_repr(protocol, protocol_name, types):
    """Represent a message type with its name only."""
    Message = get_protocol_class(protocol)

    for t in types:
        assert repr(getattr(Message, t)) == f"{protocol_name}.{t}"


@pytest.mark.parametrize(
    "protocol",
    ("y", "elva"),
)
@pytest.mark.parametrize(
    ("message_type", "payload_in", "message_out"),
    (
        ("SYNC_STEP1", b"", b"\x00\x00\x00"),
        ("SYNC_STEP1", STATE_ZERO, b"\x00\x00\x01\x00"),
        ("SYNC_STEP2", STATE_ZERO, b"\x00\x01\x01\x00"),
        ("SYNC_UPDATE", EMPTY, b"\x00\x02\x02\x00\x00"),
        ("AWARENESS", EMPTY, b"\x01\x02\x00\x00"),
    ),
)
def test_y_protocol(protocol, message_type, payload_in, message_out):
    """Conform to the Y protocol specification."""

    Message = get_protocol_class(protocol)

    # expected: magic bytes + payload length + payload
    MessageType = getattr(Message, message_type)

    # encoding, before sending
    msg, length = MessageType.encode(payload_in)
    assert msg == message_out
    assert length == len(payload_in)

    # decoding, after receiving
    payload_out, length = MessageType.decode(msg)
    assert payload_out == payload_in
    assert length == len(msg)

    # inferring (and decoding), after receiving
    msg_type, payload_out, length = Message.infer_and_decode(msg)
    assert msg_type == MessageType
    assert payload_out == payload_in
    assert length == len(msg)


def test_message_types():
    """List all defined message types."""
    assert set(YMessage.get_types()) == set(
        (
            "SYNC_STEP1",
            "SYNC_STEP2",
            "SYNC_UPDATE",
            "AWARENESS",
        )
    )
    assert set(ElvaMessage.get_types()) == set(
        (
            "SYNC_STEP1",
            "SYNC_STEP2",
            "SYNC_UPDATE",
            "AWARENESS",
            "SYNC_CROSS",
            "ID",
            "READ",
            "READ_WRITE",
            "DATA_REQUEST",
            "DATA_OFFER",
            "DATA_ORDER",
            "DATA_TRANSFER",
        )
    )


@pytest.mark.parametrize(
    "message_type",
    ElvaMessage.get_types(),
)
def test_infer_and_decode(message_type):
    """Infer and decode a message for all message types in the ElvaMessage protocol."""
    MSG = b""

    MessageType = getattr(ElvaMessage, message_type)

    msg, _ = MessageType.encode(MSG)
    msg_type, payload_out, _ = ElvaMessage.infer_and_decode(msg)

    assert msg_type == MessageType
    assert payload_out == MSG


@pytest.mark.parametrize(
    ("protocol", "protocol_name"),
    (("y", "YMessage"), ("elva", "ElvaMessage")),
)
def test_infer_and_decode_exception(protocol, protocol_name):
    """Raise an exception on an undefined message type."""
    MSG = b"??\x00"

    Message = get_protocol_class(protocol)

    with pytest.raises(ValueError) as excinfo:
        Message.infer_and_decode(MSG)

    exc = excinfo.value
    exc_msg = exc.args[0]
    assert f"{MSG[0]}, {MSG[1]}" in exc_msg
    assert protocol_name in exc_msg
