from codecs import register, Codec, CodecInfo, IncrementalEncoder, IncrementalDecoder
from enum import Enum

def write_var_uint(data):
    num = len(data)
    res = []
    while num > 127:
        res.append(128 | (127 & num))
        num >>= 7
    res.append(num)
    return bytes(res) + data, len(data)

def read_var_uint(data):
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
    def encode(self, payload, errors='strict'):
        return write_var_uint(payload)

    def decode(self, message, errors='strict'):
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
        payload, length = read_var_uint(message[self.state:])
        self.state += length
        return payload, length

    def reset(self):
        self.state = 0

    def getstate(self):
        return self.state

    def setstate(self, state):
        self.state = state


class Message(YCodec, Enum):
    def __init__(self, *magic_bytes):
        self.magic_bytes = bytes(magic_bytes)

    def __repr__(self):
        return f"{self.__class__.__name__}.{self.name}"

    def encode(self, payload, errors='strict'):
        message, length = super().encode(payload, errors=errors)
        return self.magic_bytes + message, length

    def decode(self, message, errors='strict'):
        message = message.removeprefix(self.magic_bytes)
        payload, length = super().decode(message, errors=errors)
        return payload, length + len(self.magic_bytes)

    @classmethod
    def infer_and_decode(cls, message, errors='strict'):
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
    SYNC_STEP1  = (0, 0)
    SYNC_STEP2  = (0, 1)
    SYNC_UPDATE = (0, 2)
    AWARENESS   = (1,)


class ElvaMessage(Message):
    SYNC_STEP1    = (0, 0)
    SYNC_STEP2    = (0, 1)
    SYNC_UPDATE   = (0, 2)
    SYNC_CROSS    = (0, 3)
    AWARENESS     = (1,)
    ID            = (2, 0)
    READ          = (2, 1)
    READ_WRITE    = (2, 2)
    DATA_REQUEST  = (3, 0)
    DATA_OFFER    = (3, 1)
    DATA_ORDER    = (3, 2)
    DATA_TRANSFER = (3, 3)

