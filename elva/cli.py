import importlib
import click
import anyio
from functools import partial
import ssl

from elva.utils import save_ydoc, load_ydoc


@click.group()
def elva():
    """ELVA - A suite of real-time collaboration TUI apps."""

@elva.command()
@click.argument('app')
def run(app):
    try:
        app = importlib.import_module('elva.apps.' + app)
        anyio.run(app.run)
    except Exception as e:
        click.echo(e)

@elva.command()
@click.argument("name", required=False)
@click.option("--uri", "-u", "uri", default="ws://localhost:8000", show_default=True)
def edit(name, uri):
    import elva.apps.editor as editor
    anyio.run(editor.run, name, uri) 

@elva.command()
@click.option("--host", "-h", "host", default="localhost", show_default=True)
@click.option("--port", "-p", "port", default="8000", type=int, show_default=True)
def serve(host, port):
    try:
        server = importlib.import_module('elva.websocket-server')
        anyio.run(server.run, host, port)
    except Exception as e:
        click.echo(e)

if __name__ == "__main__":
    elva()
