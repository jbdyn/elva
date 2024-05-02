import click
from elva.click_utils import lazy_cli


@lazy_cli
def elva():
    """ELVA - A suite of real-time collaboration TUI apps."""


@elva.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.argument('app')
@click.pass_context
def run(ctx, app):
    import importlib
    import anyio
    #try:
    click.echo(ctx.params)
    del ctx.params['app']
    app = importlib.import_module('elva.apps.' + app)
    #anyio.run(app.run, *ctx.args)
    ctx.invoke(app.cli, *ctx.args)
    #except Exception as e:
    #    click.echo(e)

@elva.lazy_load('elva.apps.editor:cli')
def edit():
    """collaborative editor"""

@elva.lazy_load('elva.websocket-server:cli')
def serve():
    """local websocket server"""

@elva.lazy_load('elva.metaprovider:cli')
def meta():
    """local meta provider"""

@elva.lazy_load('elva.apps.chat:cli')
def chat():
    """chat app"""

if __name__ == "__main__":
    elva()
