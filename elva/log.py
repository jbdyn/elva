import logging
import logging.handlers
import pickle
import socket
import socketserver
import struct
from logging.handlers import SocketHandler
from pathlib import Path
from time import sleep

import click
from pythonjsonlogger.jsonlogger import JsonFormatter as BaseJsonFormatter
from websockets.client import ClientProtocol
from websockets.uri import parse_uri


###
#
# formatter
#
class DefaultFormatter(logging.Formatter):
    def __init__(self):
        fmt = "%(asctime)s - %(levelname)s - (%(name)s) %(component)s %(message)s"
        datefmt = "%Y-%m-%d %H:%M:%S"
        defaults = dict(component=None)
        super().__init__(fmt=fmt, datefmt=datefmt, defaults=defaults)


class JsonFormatter(BaseJsonFormatter):
    def __init__(self):
        fmt = "%(asctime)s %(levelname)s %(name)s %(component)s %(message)s"
        datefmt = "%Y-%m-%dT%H:%M:%S"
        defaults = dict(component=None)
        super().__init__(fmt=fmt, datefmt=datefmt, defaults=defaults)


###
#
# handler
#
class WebsocketHandler(SocketHandler):
    def __init__(self, uri: str):
        self.uri = parse_uri(uri)
        self.protocol = ClientProtocol(self.uri)
        self.events = list()
        super().__init__(self.uri.host, self.uri.port)

    def makeSocket(self):
        # open TCP connection
        self.sock = super().makeSocket()
        sock = self.sock

        # TODO: perform TLS handshake
        # if self.uri.secure:
        #    ...

        # send handshake request
        protocol = self.protocol
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
        for data in self.protocol.data_to_send():
            if data:
                try:
                    self.sock.sendall(data)
                except OSError:  # socket closed
                    self.reset_socket()
                    break
            else:
                # half-close TCP connection
                self.sock.shutdown(socket.SHUT_WR)

    def receive_data(self):
        try:
            data = self.sock.recv(65536)
        except OSError:  # socket closed
            data = b""
        if data:
            self.protocol.receive_data(data)
        else:
            self.protocol.receive_eof()

        # necessary because `websockets` responds to ping frames,
        # close frames, and incorrect inputs automatically
        self.send_data()

        self.process_events_received()
        self.check_close_expected()

    def check_close_expected(self):
        if self.protocol.close_expected():
            sleep(5)
            self.reset_socket()

    def process_events_received(self):
        # do something with the events,
        # first event is handshake response
        events = self.protocol.events_received()
        self.events.extend(events)
        print(self.events)

    def close_socket(self):
        self.protocol.send_close()
        self.send_data()
        self.reset_socket()

    def reset_socket(self):
        self.sock.close()
        self.sock = None

    def send(self, s):
        if self.sock is None:
            self.createSocket()

        if self.sock:
            self.protocol.send_binary(s)
            self.send_data()

    def close(self):
        with self.lock:
            if self.sock:
                self.close_socket()
            logging.Handler.close(self)


def get_default_handler(uri):
    handler = WebsocketHandler(uri)
    handler.setFormatter(DefaultFormatter())
    return handler


###
#
# logging TCP server
#
class LogRecordStreamHandler(socketserver.StreamRequestHandler):
    """Handler for a streaming logging request.

    This basically logs the record using whatever logging policy is
    configured locally.
    """

    def __init__(self, filename="elva.log", *args, **kwargs):
        self.logHandler = logging.FileHandler(filename)
        super().__init__(*args, **kwargs)

    def handle(self):
        """
        Handle multiple requests - each expected to be a 4-byte length,
        followed by the LogRecord in pickle format. Logs the record
        according to whatever policy is configured locally.
        """
        while True:
            chunk = self.connection.recv(4)
            if len(chunk) < 4:
                break
            slen = struct.unpack(">L", chunk)[0]
            chunk = self.connection.recv(slen)
            while len(chunk) < slen:
                chunk = chunk + self.connection.recv(slen - len(chunk))
            obj = self.unPickle(chunk)
            record = logging.makeLogRecord(obj)
            self.handleLogRecord(record)

    def unPickle(self, data):
        return pickle.loads(data)

    def handleLogRecord(self, record):
        # if a name is specified, we use the named logger rather than the one
        # implied by the record.
        if self.server.logname is not None:
            name = self.server.logname
        else:
            name = record.name
        logger = logging.getLogger(name)
        if not logger.hasHandlers():
            logger.addHandler(self.logHandler)
        # N.B. EVERY record gets logged. This is because Logger.handle
        # is normally called AFTER logger-level filtering. If you want
        # to do filtering, do it at the client end to save wasting
        # cycles and network bandwidth!
        logger.handle(record)


class LogRecordSocketReceiver(socketserver.ThreadingTCPServer):
    """
    Simple TCP socket-based logging receiver suitable for testing.
    """

    allow_reuse_address = True

    def __init__(
        self,
        host="localhost",
        port=logging.handlers.DEFAULT_TCP_LOGGING_PORT,
        handler=LogRecordStreamHandler,
    ):
        super().__init__((host, port), handler)
        self.abort = 0
        self.timeout = 1
        self.logname = None

    def serve_until_stopped(self):
        import select

        abort = 0
        while not abort:
            rd, wr, ex = select.select([self.socket.fileno()], [], [], self.timeout)
            if rd:
                self.handle_request()
            abort = self.abort


@click.command
@click.pass_context
@click.argument("file", required=False, type=click.Path(dir_okay=False, path_type=Path))
def cli(ctx: click.Context, file):
    if file is None:
        file = ctx.obj["log"]
    # TODO: pass file as parameter to server
    tcpserver = LogRecordSocketReceiver()
    print("About to start TCP server...")
    tcpserver.serve_until_stopped()


if __name__ == "__main__":
    cli()
