"""
Module holding the [Y-Protocol](https://github.com/yjs/y-protocols/blob/master/PROTOCOL.md) specification.
"""

from codecs import Codec, IncrementalDecoder, IncrementalEncoder
from enum import Enum
from typing import Self


def write_var_uint(data: bytes) -> tuple[bytes, int]:
    """
    Calculate the variable unsigned integer length of `data`.

    Arguments:
        data: bytes object.

    Returns:
        A tuple of two values: `data` with the variable unsigned integer prepended and the length of `data`.
    """
    num = len(data)
    res = []
    while num > 127:
        res.append(128 | (127 & num))
        num >>= 7
    res.append(num)
    return bytes(res) + data, len(data)


def read_var_uint(data: bytes) -> tuple[bytes, int]:
    """
    Read and strip off the variable unsigned interger value from `data`.

    Arguments:
        data: bytes object.

    Returns:
        A tuple of two values: `data` with the variable unsigned integer stripped and the length of bytes of `data` being processed.
    """
    uint = 0
    bit = 0
    byte_idx = 0
    while True:
        byte = data[byte_idx]
        uint += (byte & 127) << bit
        bit += 7
        byte_idx += 1
        if byte < 128:
            break
    return data[byte_idx : byte_idx + uint], min(byte_idx + uint, len(data))


class YCodec(Codec):
    """
    Codec for Y messages according to the [Yjs base encoding](https://github.com/yjs/y-protocols/blob/master/PROTOCOL.md#base-encoding-approaches).
    """

    def encode(self, payload: bytes, errors: str = "strict") -> tuple[bytes, int]:
        """
        Prepend the size of `payload` to itself as a variable unsigned integer.

        Arguments:
            payload: data to encode
            errors: no-op.

        Returns:
            A tuple of two values: `data` with the variable unsigned integer prepended and the length of `data`.
        """
        return write_var_uint(payload)

    def decode(self, message: bytes, errors: str = "strict") -> tuple[bytes, int]:
        """
        Read and strip off the encoded size from `payload`.

        Arguments:
            message: data to decode
            errors: no-op.

        Returns:
            A tuple of two values: `data` with the variable unsigned integer stripped and the length of bytes of `data` being processed.
        """
        return read_var_uint(message)


class YIncrementalEncoder(IncrementalEncoder):
    state = 0

    def encode(self, payloads):
        message, length = write_var_uint(payloads[self.state])
        self.state += 1
        return message, length

    def reset(self):
        self.state = 0

    def getstate(self):
        return self.state

    def setstate(self, state):
        self.state = state


class YIncrementalDecoder(IncrementalDecoder):
    state = 0

    def decode(self, message):
        payload, length = read_var_uint(message[self.state :])
        self.state += length
        return payload, length

    def reset(self):
        self.state = 0

    def getstate(self):
        return self.state

    def setstate(self, state):
        self.state = state


class Message(YCodec, Enum):
    """
    Base class for Y messages according to the [Yjs sync and awareness protocol](https://github.com/yjs/y-protocols/blob/master/PROTOCOL.md#sync-protocol-v1-encoding).
    """

    def __init__(self, *magic_bytes: bytes):
        """
        Arguments:
            magic_bytes: arbitrary number of bytes prepended in the encoded payload.
        """
        self.magic_bytes = bytes(magic_bytes)

    def __repr__(self):
        return f"{self.__class__.__name__}.{self.name}"

    def encode(self, payload: bytes, errors: str = "strict") -> tuple[bytes, int]:
        """
        Calculate the encoded `payload` with the message type's magic bytes prepended.

        Arguments:
            payload: data to be encoded.
            errors: no-op.

        Returns:
            A tuple of two objects: the encoded payload with the message type's magic bytes prepended and the length of bytes being processed.
        """
        message, length = super().encode(payload, errors=errors)
        return self.magic_bytes + message, length

    def decode(self, message: bytes, errors: str = "strict") -> tuple[bytes, int]:
        """
        Remove magic bytes and decode `message`.

        Arguments:
            message: data to be decoded.
            errors: no-op.

        Returns:
            A tuple of two objects: the decoded message with the message type's magic bytes removed and the length of bytes being processed.
        """
        message = message.removeprefix(self.magic_bytes)
        payload, length = super().decode(message, errors=errors)
        return payload, length + len(self.magic_bytes)

    @classmethod
    def infer_and_decode(
        cls, message: bytes, errors: str = "strict"
    ) -> tuple[Self, bytes, int]:
        """
        Infer the type of the given message and return its decoded form.

        Arguments:
            message: data to decode
            errors: no-op.

        Returns:
            A tuple of three objects: the inferred message type of `message`, the decoded form of `message` and the length of processed bytes from `message`
        """
        first = message[0]
        match first:
            case 0:
                ymsg = cls((first, message[1]))
                return ymsg, *ymsg.decode(message, errors=errors)
            case 1:
                ymsg = cls((first,))
                return ymsg, *ymsg.decode(message, errors=errors)
            case _:
                raise ValueError(f"given message '{message}' is not a valid YMessage")


class YMessage(Message):
    """
    Implementation of Y messages according to the [Yjs sync and awareness protocol](https://github.com/yjs/y-protocols/blob/master/PROTOCOL.md#sync-protocol-v1-encoding)
    """

    SYNC_STEP1 = (0, 0)
    """Synchronization request message."""

    SYNC_STEP2 = (0, 1)
    """synchronization reply message."""

    SYNC_UPDATE = (0, 2)
    """Update message."""

    AWARENESS = (1,)
    """Awareness message."""


# TODO: rewrite with letter magic bytes
class ElvaMessage(Message):
    """
    Extension of Y messages with additional message types.
    """

    SYNC_STEP1 = (0, 0)
    """Synchronization request message."""

    SYNC_STEP2 = (0, 1)
    """Synchronization reply message."""

    SYNC_UPDATE = (0, 2)
    """Update message."""

    SYNC_CROSS = (0, 3)
    """
    Cross-synchronization message holding
    [`SYNC_STEP1`][elva.protocol.ElvaMessage.SYNC_STEP1] and
    [`SYNC_STEP2`][elva.protocol.ElvaMessage.SYNC_STEP2].
    """

    AWARENESS = (1,)
    """Awareness message."""

    ID = (2, 0)
    """Identitity message."""

    READ = (2, 1)
    """Read-only message."""

    READ_WRITE = (2, 2)
    """Read-write message."""

    DATA_REQUEST = (3, 0)
    """Message requesting a specific blob of data."""

    DATA_OFFER = (3, 1)
    """Message offering a requested blob of data."""

    DATA_ORDER = (3, 2)
    """Message ordering a offered blob of data."""

    DATA_TRANSFER = (3, 3)
    """Message transferring a ordered blob of data."""
