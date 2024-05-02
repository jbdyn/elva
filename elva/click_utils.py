import click
from click import Command, Group, Context, Option
from collections.abc import Callable
from typing import Any
from elva.click_lazy_group import LazyGroup
import importlib

def lazy_cli(f: Callable) -> Group:
    """
    decorator function like click.group() 
    with f.lazy_load(import_name, **kwargs) being a shortcut to
    f.group(cls=LazyGroup, import_name=import_name, invoke_without_command=True, **kwargs).
    invoke_without_command is set to True so that it can be set in the lazy loaded command.
    """

    f = click.group()(f)
    def lazy_load(import_name: str, **kwargs):
        return f.group(cls=LazyGroup, import_name=import_name, invoke_without_command=True, **kwargs)
    f.lazy_load=lazy_load
    return f

def lazy_group(**kwargs):
    """  
    returns a decorator function equivalent to @click.group(**kwargs)
    with the default value of 'invoke_without_command' changed to True
    """

    def decorator(f: Callable):
        if 'invoke_without_command' in kwargs.keys() and not kwargs['invoke_without_command']:
                echo_help(click.group(**kwargs)(f)) 
                exit()
        kwargs['invoke_without_command'] = True
        return click.group(**kwargs)(f)
        
    return decorator

def lazy_group_without_invoke(**kwargs) -> Callable[[Callable], Group]:
    """
    decorator function like click.group(**kwargs) for lazy loaded commands
    so that invoke_without_command can be set via kwargs in the command decorator
    """

    def decorator(f: Callable):
        if 'invoke_without_command' in kwargs.keys() and kwargs['invoke_without_command']:
            return click.group(**kwargs)(f)
        kwargs['invoke_without_command'] = False
        echo_help(click.group(**kwargs)(f)) 
        exit()
        
    return decorator

def lazy_app_cli(**kwargs) -> Callable[[Callable], Group]:
    """
    like click.group(**kwargs) (with lazy_group) and with default options for elva apps already configured
    """

    def decorator(f: Callable):
        f = lazy_group(**kwargs)(f)
        f = click.option("--server", "-s", "server", default="local", help="'local' or 'remote'", callback=get_option_callback_check_in_list(['local', 'remote']))(f)
        f = click.option("--uuid", "-u", "uuid", default='test', help="room name")(f)
        f = click.option("--remote_websocket_server", "-r", "remote_websocket_server", default="wss://example.com/sync/", show_default=False)(f)
        f = click.option("--local_host", "-h", "local_websocket_host", default="localhost", show_default=True)(f)
        f = click.option("--local_port", "-p", "local_websocket_port", default=8000, show_default=True)(f)
        f = click.option("----------elva_provider","provider", hidden=True, callback=_lazy_app_processing_callback)(f)
        return f
    return decorator

def _lazy_app_processing_callback(ctx: Context, param, value):
    settings = dict()

    settings['server'] = ctx.params.pop('server')
    settings['uuid'] = ctx.params.pop('uuid')
    settings['remote_websocket_server'] = ctx.params.pop('remote_websocket_server')
    settings['local_websocket_host'] = ctx.params.pop('local_websocket_host')
    settings['local_websocket_port'] = ctx.params.pop('local_websocket_port')

    if settings['server'] == "remote":
        # connect to the remote websocket server directly, without using the metaprovider
        uri = settings['remote_websocket_server']
        Provider = importlib.import_module('elva.providers').get_websocket_like_elva_provider(settings['uuid'])
    elif settings['server'] == 'local':
        # connect to the local metaprovider
        uri = f"ws://{settings['local_websocket_host']}:{settings['local_websocket_port']}/{settings['uuid']}"
        Provider = providers = importlib.import_module('pycrdt_websocket','WebsocketProvider')

    settings['uri'] = uri
    settings['provider']= Provider
    ctx.params['uri'] = uri 
    ctx.obj = settings

    return Provider 

def echo_help(f: Command):
    """
    print help of function f with click.echo, considering f's context
    """

    try:
        with click.Context(f) as ctx:
            click.echo(f.get_help(ctx))
    except: 
        click.echo(f.get_help())

def get_option_callback_check_in_list(l: list) -> Callable[[Context, Option, Any], None]:
    def callback(ctx: Context, param: Option, value: Any) -> None:
        if value not in l:
            raise click.BadParameter('%s not in %s.' % (value, l))
        return value
    return callback 

def get_option_callback_check_with_lambda(fn: Callable[[Context, Option, Any], bool]) -> Callable[[Context, Option, Any], None]:
    def callback(ctx: Context, param: Option, value: Any) -> None:
        if fn(ctx, param, value):
            raise click.BadParameter('%s' % (value))
        return value
    return callback 