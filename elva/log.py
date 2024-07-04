import logging
import logging.handlers
import pickle
import socketserver
import struct
from logging.handlers import DEFAULT_TCP_LOGGING_PORT
from logging.handlers import SocketHandler as BaseSocketHandler
from pathlib import Path

import click
from pythonjsonlogger.jsonlogger import JsonFormatter as BaseJsonFormatter


###
#
# formatter
#
class DefaultFormatter():
    def __init__(self):
        fmt ="%(asctime)s - %(levelname)s - (%(name)s) %(component)s %(message)s"
        datefmt = "%Y-%m-%d %H:%M:%S"
        defaults = dict(component=None)
        super().__init__(fmt=fmt, datefmt=datefmt, defaults=defaults)


class JsonFormatter(BaseJsonFormatter):
    def __init__(self):
        fmt ="%(asctime)s %(levelname)s %(name)s %(component)s %(message)s"
        datefmt = "%Y-%m-%dT%H:%M:%S"
        defaults = dict(component=None)
        super().__init__(fmt=fmt, datefmt=datefmt, defaults=defaults)


###
#
# handler
#
class SocketHandler(BaseSocketHandler):
    def __init__(
        self,
        host: str = "localhost",
        port: int = DEFAULT_TCP_LOGGING_PORT
    ):
        super().__init__(host, port)

def get_default_handler():
    return SocketHandler().setFormatter(DefaultFormatter())


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
            slen = struct.unpack('>L', chunk)[0]
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
        handler=LogRecordStreamHandler
    ):
        super().__init__((host, port), handler)
        self.abort = 0
        self.timeout = 1
        self.logname = None

    def serve_until_stopped(self):
        import select
        abort = 0
        while not abort:
            rd, wr, ex = select.select([self.socket.fileno()],
                                       [], [],
                                       self.timeout)
            if rd:
                self.handle_request()
            abort = self.abort


@click.command
@click.pass_context
@click.argument(
    "file",
    required=False,
    type=click.Path(dir_okay=False, path_type=Path)
)
def cli(ctx: click.Context, file):
    if file is None:
        file = ctx.obj["log"]
    # TODO: pass file as parameter to server
    tcpserver = LogRecordSocketReceiver()
    print('About to start TCP server...')
    tcpserver.serve_until_stopped()


if __name__ == '__main__':
    cli()
