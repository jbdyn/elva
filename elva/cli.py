import click
from elva.click_utils import get_option_callback_check_in_list
import uuid

@click.group( context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.pass_context
@click.option("--name", "-n", "name", default=str(uuid.uuid4()), help="username")
@click.option("--server", "-s", "server", default="local", help="'local' or 'remote'", callback=get_option_callback_check_in_list(['local', 'remote']))
@click.option("--identifier", "-i", "identifier", default='test', help="room name")
@click.option("--remote_ws_server", "-r", "remote_websocket_server", default="wss://example.com/sync/", show_default=False)
@click.option("--local_host", "-h", "local_websocket_host", default="localhost", show_default=True)
@click.option("--local_port", "-p", "local_websocket_port", default=8000, show_default=True)
def elva(ctx: click.Context, name: str, server: str, identifier: str, remote_websocket_server: str, local_websocket_host: str, local_websocket_port: int):
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
    settings['remote_websocket_server'] = remote_websocket_server
    settings['local_websocket_host'] = local_websocket_host
    settings['local_websocket_port'] = local_websocket_port

    if settings['server'] == "remote":
        # connect to the remote websocket server directly, without using the metaprovider
        uri = remote_websocket_server
        Provider: ElvaProvider = ElvaProvider
    else: #elif settings['server'] == 'local':
        # connect to the local metaprovider
        uri = f"ws://{local_websocket_host}:{local_websocket_port}/{identifier}"
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

