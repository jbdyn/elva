import logging
import logging.handlers
import pickle
import socket
import time
from contextvars import ContextVar
from logging.handlers import SocketHandler
from threading import Thread
from time import sleep

from pythonjsonlogger.jsonlogger import JsonFormatter as BaseJsonFormatter
from websockets.client import ClientProtocol
from websockets.sync.client import connect
from websockets.uri import parse_uri

LOGGER_NAME = ContextVar("logger_name")


###
#
# formatter
#
class DefaultFormatter(logging.Formatter):
    def __init__(self):
        fmt = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
        datefmt = "%Y-%m-%d %H:%M:%S"
        super().__init__(fmt=fmt, datefmt=datefmt)


class JsonFormatter(BaseJsonFormatter):
    def __init__(self):
        fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
        datefmt = "%Y-%m-%dT%H:%M:%S"
        super().__init__(fmt=fmt, datefmt=datefmt)


###
#
# handler
#
class SimpleHandler(SocketHandler):
    def __init__(self, uri: str):
        self.uri = parse_uri(uri)
        self.events = list()
        super().__init__(self.uri.host, self.uri.port)

    def makePickle(self, record):
        """
        Pickles the record in binary format
        """
        ei = record.exc_info
        if ei:
            # just to get traceback text into record.exc_text ...
            self.format(record)
        # See issue #14436: If msg or args are objects, they may not be
        # available on the receiving end. So we convert the msg % args
        # to a string, save it as msg and zap the args.
        d = dict(record.__dict__)
        d["msg"] = record.getMessage()
        d["args"] = None
        d["exc_info"] = None
        # Issue #25685: delete 'message' if present: redundant with 'msg'
        d.pop("message", None)
        s = pickle.dumps(d, 1)
        return s

    def makeSocket(self):
        return connect(self.uri)


class WebsocketHandler(logging.Handler):
    def __init__(self, uri: str):
        self.uri = uri
        self.sock = None
        self.retryTime = None
        #
        # Exponential backoff parameters.
        #
        self.retryStart = 1.0
        self.retryMax = 30.0
        self.retryFactor = 2.0

        super().__init__()

    def makePickle(self, record):
        """
        Pickles the record in binary format with a length prefix, and
        returns it ready for transmission across the socket.
        """
        ei = record.exc_info
        if ei:
            # just to get traceback text into record.exc_text ...
            self.format(record)
        # See issue #14436: If msg or args are objects, they may not be
        # available on the receiving end. So we convert the msg % args
        # to a string, save it as msg and zap the args.
        d = dict(record.__dict__)
        d["msg"] = record.getMessage()
        d["args"] = None
        d["exc_info"] = None
        # Issue #25685: delete 'message' if present: redundant with 'msg'
        d.pop("message", None)
        s = pickle.dumps(d, 1)
        # slen = struct.pack(">L", len(s))
        # return slen + s
        return s

    def createSocket(self):
        """
        Try to create a socket, using an exponential backoff with
        a max retry time. Thanks to Robert Olson for the original patch
        (SF #815911) which has been slightly refactored.
        """
        now = time.time()
        # Either retryTime is None, in which case this
        # is the first time back after a disconnect, or
        # we've waited long enough.
        if self.retryTime is None:
            attempt = True
        else:
            attempt = now >= self.retryTime
        if attempt:
            try:
                print("try create socket")
                self.sock = connect(self.uri)
                print("create socket")
                self.retryTime = None  # next time, no delay before trying
            except OSError:
                # Creation failed, so set the retry time and return.
                if self.retryTime is None:
                    self.retryPeriod = self.retryStart
                else:
                    self.retryPeriod = self.retryPeriod * self.retryFactor
                    if self.retryPeriod > self.retryMax:
                        self.retryPeriod = self.retryMax
                self.retryTime = now + self.retryPeriod

    def send(self, s):
        if self.sock is None:
            self.createSocket()

        if self.sock:
            try:
                self.sock.send(s)
                print("emit")
            except (Exception, KeyboardInterrupt):
                self.closeSocket()

    def emit(self, record):
        try:
            s = self.makePickle(record)
            self.send(s)
        except Exception:
            self.handleError(record)

    def closeSocket(self):
        print("close socket")
        self.sock.close()
        self.sock = None

    def handleError(self, record):
        print("HANDLE ERROR")
        with self.lock:
            if self.sock:
                self.closeSocket()
            else:
                super().handleError(record)

    def close(self):
        with self.lock:
            if self.sock:
                self.closeSocket()

        super().close()
        print("close handler")


class WebsocketProtocolHandler(SocketHandler):
    def __init__(self, uri: str):
        self.uri = parse_uri(uri)
        self.events = list()
        super().__init__(self.uri.host, self.uri.port)

    def makePickle(self, record):
        """
        Pickles the record in binary format with a length prefix, and
        returns it ready for transmission across the socket.
        """
        ei = record.exc_info
        if ei:
            # just to get traceback text into record.exc_text ...
            self.format(record)
        # See issue #14436: If msg or args are objects, they may not be
        # available on the receiving end. So we convert the msg % args
        # to a string, save it as msg and zap the args.
        d = dict(record.__dict__)
        d["msg"] = record.getMessage()
        d["args"] = None
        d["exc_info"] = None
        # Issue #25685: delete 'message' if present: redundant with 'msg'
        d.pop("message", None)
        s = pickle.dumps(d, 1)
        # slen = struct.pack(">L", len(s))
        # return slen + s
        return s

    def makeSocket(self):
        print("make new socket")
        # open TCP connection
        self.sock = super().makeSocket()
        sock = self.sock

        # TODO: perform TLS handshake
        # if self.uri.secure:
        #    ...

        # init protocol
        # TODO: Here or in __init__?
        #       it seems that otherwise messages don't get sent
        #       on reconnect after a BrokenPipeError
        self.protocol = ClientProtocol(self.uri)
        protocol = self.protocol

        # send handshake request
        print("handshake")
        request = protocol.connect()
        protocol.send_request(request)
        self.send_data()

        # receive data
        self.receive_data()

        # raise reason if handshake failed
        if protocol.handshake_exc is not None:
            self.reset_socket()
            raise protocol.handshake_exc

        return sock

    def send_data(self):
        try:
            for data in self.protocol.data_to_send():
                if data:
                    print("send data")
                    self.sock.sendall(data)
                else:
                    # half-close TCP connection, i.e. close the write side
                    print("close write side")
                    self.sock.shutdown(socket.SHUT_WR)
        except OSError:
            self.reset_socket()

    def receive_data(self):
        try:
            data = self.sock.recv(65536)
        except OSError:  # socket closed
            data = b""
        if data:
            print("receive data")
            self.protocol.receive_data(data)
            self.process_events_received()
            self.check_close_expected()
            # necessary because `websockets` responds to ping frames,
            # close frames, and incorrect inputs automatically
            self.send_data()
        else:
            print("receive EOF")
            self.protocol.receive_eof()
            self.check_close_expected
            self.close_socket()

    def handleError(self, record):
        print("HANDLE ERROR")
        if self.closeOnError and self.sock:
            self.close_socket()
        else:
            logging.Handler.handleError(self, record)

    def check_close_expected(self):
        # TODO: run in separate thread
        if self.protocol.close_expected():
            print("close expected")
            t = Thread(target=self.close_socket, kwargs=dict(delay=10))
            t.run()

    def process_events_received(self):
        # do something with the events,
        # first event is handshake response
        print("process events received")
        events = self.protocol.events_received()
        if events:
            print("adding new events")
        self.events.extend(events)

    def close_socket(self, delay=None):
        print("close socket")
        if delay is not None:
            print("add delay", delay)
            sleep(delay)
        self.protocol.send_close()
        self.send_data()
        self.reset_socket()

    def reset_socket(self):
        if self.sock is not None:
            print("reset socket")
            self.sock.close()
            self.sock = None
            self.protocol = None

    def send(self, s):
        if self.sock is None:
            self.createSocket()

        if self.sock:
            try:
                self.protocol.send_binary(s)
                self.send_data()
            except Exception as exc:
                print(exc)
                self.close_socket()

    def close(self):
        with self.lock:
            if self.sock:
                self.close_socket()
        print("close handler")
        logging.Handler.close(self)


def get_default_handler(uri):
    handler = WebsocketHandler(uri)
    handler.setFormatter(DefaultFormatter())
    return handler
