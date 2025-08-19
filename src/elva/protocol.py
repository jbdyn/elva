"""
Module holding the [Y-Protocol](https://github.com/yjs/y-protocols/blob/master/PROTOCOL.md) specification.
"""

from codecs import Codec
from enum import Enum
from typing import Self

STATE_ZERO = b"\x00"
"""The state of an empty YDoc."""

EMPTY_UPDATE = b"\x00\x00"
"""The update between two equivalent YDoc states."""


##
#
# HELPERS
#
def write_var_uint(num: int) -> list[int]:
    """
    Encode an integer into a variable unsigned integer.

    Arguments:
        num: the integer to encode.

    Returns:
        a list of integers representing the bits of the variable unsigned integer.
    """
    res = []

    # while `num` is bigger than 1 byte minus 1 continuation bit, i.e. 7 bits
    while num > 127:
        #        127 & num   <=>  extract the last 7 bits of `num`
        # 128 | (127 & num)  <=>  put a "1" as continuation bit before the last 7 bits of `num`
        res.append(128 | (127 & num))

        # discard the last 7 bits of `num`
        num >>= 7

    # append the remaining bits in `num`
    res.append(num)

    return res


def read_var_uint(data: bytes) -> tuple[int, int]:
    """
    Read the first variable unsigned integer in `data`.

    Arguments:
        data: data holding the variable unsigned integer.

    Returns:
        a tuple of the decoded variable unsigned integer and its number of bytes
    """
    # we start at the very first byte/bit of `data`
    uint = 0
    bit = 0
    byte_idx = 0

    while True:
        byte = data[byte_idx]

        #  byte & 127          <=>  extract the last 7 bits in the current `byte`
        # (byte & 127) << bit  <=>  shift bits in `res` `bit` times to the left
        uint += (byte & 127) << bit

        # move the bit offset by 7
        bit += 7

        # move the byte offset by 1
        byte_idx += 1

        if byte < 128:
            # the first bit of this byte, i.e. the continuation bit, is not a "1",
            # so this is the last byte being part of the variable unsigned integer
            break

    return uint, byte_idx


def prepend_var_uint(data: bytes) -> tuple[bytes, int]:
    """
    Prepend the length of `data` as variable unsigned integer to `data`.

    See [Yjs base encoding](https://github.com/yjs/y-protocols/blob/master/PROTOCOL.md#base-encoding-approaches) for reference.

    Arguments:
        data: the payload of a Y protocol message.

    Returns:
        A tuple of two values: `data` with the variable unsigned integer prepended and the length of `data`.
    """
    len_data = len(data)
    res = write_var_uint(len_data)

    return bytes(res) + data, len_data


def strip_var_uint(data: bytes) -> tuple[bytes, int]:
    """
    Read and strip off the variable unsigned integer length from `data`.

    See [Yjs base encoding](https://github.com/yjs/y-protocols/blob/master/PROTOCOL.md#base-encoding-approaches) for reference.

    Arguments:
        data: the payload of a Y protocol message plus its length as variable unsigned integer prepended.

    Returns:
        A tuple of two values: `data` with the variable unsigned integer length stripped and the length of bytes of `data` being processed.
    """
    uint, byte_idx = read_var_uint(data)

    # extract the payload from `data`, return the actual length of the payload
    return data[byte_idx : byte_idx + uint], min(byte_idx + uint, len(data))


##
#
# CODEC
#


class YCodec(Codec):
    """
    Codec for Y messages according to the [Yjs base encoding](https://github.com/yjs/y-protocols/blob/master/PROTOCOL.md#base-encoding-approaches).
    """

    def encode(self, payload: bytes, errors: str = "strict") -> tuple[bytes, int]:
        """
        Prepend the size of `payload` to itself as a variable unsigned integer.

        Arguments:
            payload: the payload of a Y protocol message.
            errors: no-op.

        Returns:
            A tuple of two values: `data` with the variable unsigned integer prepended and the length of `data`.
        """
        return prepend_var_uint(payload)

    def decode(self, message: bytes, errors: str = "strict") -> tuple[bytes, int]:
        """
        Read and strip off the encoded size from `message`.

        Arguments:
            message: the payload of a Y protocol message plus its length as variable unsigned integer prepended.
            errors: no-op.

        Returns:
            A tuple of two values: `data` with the variable unsigned integer stripped and the length of bytes of `data` being processed.
        """
        return strip_var_uint(message)


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

    @classmethod
    def get_types(cls) -> tuple[str]:
        """
        The message types associated with this codec.

        Returns:
            a tuple containing all message type names as strings.
        """
        return tuple(attr for attr in dir(cls) if not attr.startswith("__"))

    def encode(self, payload: bytes, errors: str = "strict") -> tuple[bytes, int]:
        """
        Calculate the encoded `payload` with the message type's magic bytes prepended.

        Arguments:
            payload: the payload of a Y protocol message.
            errors: no-op.

        Returns:
            A tuple of two objects: the encoded payload with the message type's magic bytes prepended and the length of bytes being processed.
        """
        message, length = super().encode(payload, errors=errors)
        return self.magic_bytes + message, length

    def decode(self, message: bytes, errors: str = "strict") -> tuple[bytes, int]:
        """
        Remove magic bytes and extract the payload of `message`.

        Arguments:
            message: the Y protocol message.
            errors: no-op.

        Returns:
            A tuple of two objects: the decoded message with the message type's magic bytes removed and the length of bytes being processed.
        """
        message = message.removeprefix(self.magic_bytes)
        payload, length = self._decode(message, errors=errors)
        return payload, length + len(self.magic_bytes)

    def _decode(self, data: bytes, errors: str = "strict") -> tuple[bytes, int]:
        """
        Hook extracting the payload of `message`.

        Arguments:
            data: the payload of a Y protocol message plus its length as variable unsigned integer prepended.
            errors: no-op.

        Returns:
            A tuple of two objects: `data` with the variable unsigned integer stripped and the length of bytes of `data` being processed.
        """
        return super().decode(data, errors=errors)

    @classmethod
    def infer_and_decode(
        cls, message: bytes, errors: str = "strict"
    ) -> tuple[Self, bytes, int]:
        """
        Infer the type of the given message and return its decoded form.

        Arguments:
            message: the Y protocol message.
            errors: no-op.

        Returns:
            A tuple of three objects: the inferred message type of `message`, the decoded form of `message` and the length of processed bytes from `message`.
        """
        # there might be no second magic byte
        mb2_off = 0

        mb1, mb1_off = read_var_uint(message)

        try:
            if mb1 == 1:
                # awareness message is the only type with a single magic byte
                ymsg = cls((mb1,))
            else:
                mb2, mb2_off = read_var_uint(message[mb1_off:])
                ymsg = cls((mb1, mb2))
        except ValueError:
            raise ValueError(
                f"Message with magic bytes {mb1}, {mb2} is not a valid {cls.__name__}"
            ) from None

        payload, length = ymsg._decode(message[mb1_off + mb2_off :], errors=errors)
        return ymsg, payload, mb1_off + mb2_off + length


##
#
# PROTOCOLS
#

# be aware to give integers from `*write_var_uint`;
# here we stay below 127 and thus `write_var_uint` is not needed.


class YMessage(Message):
    """
    Implementation of Y messages according to the [Yjs sync and awareness protocol](https://github.com/yjs/y-protocols/blob/master/PROTOCOL.md#sync-protocol-v1-encoding).
    """

    SYNC_STEP1 = (0, 0)
    """Synchronization request message."""

    SYNC_STEP2 = (0, 1)
    """Synchronization reply message."""

    SYNC_UPDATE = (0, 2)
    """Update message."""

    AWARENESS = (1,)
    """Awareness message."""


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

    ID = (ord("I"), ord("D"))
    """Identitity message."""

    READ = (ord("R"), ord("O"))
    """Read-only message."""

    READ_WRITE = (ord("R"), ord("W"))
    """Read-write message."""

    DATA_REQUEST = (ord("D"), 1)
    """Message requesting a specific blob of data."""

    DATA_OFFER = (ord("D"), 2)
    """Message offering a requested blob of data."""

    DATA_ORDER = (ord("D"), 3)
    """Message ordering an offered blob of data."""

    DATA_TRANSFER = (ord("D"), 4)
    """Message transferring an ordered blob of data."""
