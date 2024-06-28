import click
from elva.click_utils import get_option_callback_check_in_list
import uuid

@click.group( context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.pass_context
@click.option("--name", "-n", "name", default=str(uuid.uuid4()), help="username")
@click.option("--server", "-s", "server", default="wss://example.com/sync/")
@click.option("--identifier", "-i", "identifier", default='test', help="room name")
@click.option("--provider", "-p", "provider", default='ElvaProvider', help="room name")
def elva(ctx: click.Context, name: str, server: str, identifier: str, provider: str):
    """ELVA - A suite of real-time collaboration TUI apps."""

    if ctx.invoked_subcommand is None:
        click.echo(elva.get_help(ctx))
        return

    from elva.provider import ElvaProvider, WebsocketElvaProvider

    ctx.ensure_object(dict)
    settings = ctx.obj 
    settings['identifier'] = identifier
    settings['name'] = name
    settings['server'] = server
    settings['provider'] = provider.lower()

    if settings['provider'] == "elvaprovider":
        # connect to the remote websocket server directly, without using the metaprovider
        uri = server
        Provider: ElvaProvider = ElvaProvider
    else: #elif settings['server'] == 'local':
        # connect to the local metaprovider
        if server[-1] == "/":
            uri = f"{server}{identifier}"
        else:
            uri = f"{server}/{identifier}"
            
        Provider: ElvaProvider = WebsocketElvaProvider

    settings['uri'] = uri
    settings['provider']= Provider




from elva.apps.editor import cli
elva.add_command(cli, "edit")

from elva.apps.chat import cli
elva.add_command(cli, "chat")

from elva.websocket_server import cli
elva.add_command(cli, "serve")

from elva.metaprovider import cli
elva.add_command(cli, "meta")

if __name__ == "__main__":
    elva()

