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

    f = click.group(invoke_without_command=True, context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))(f)
    def lazy_load(import_name: str, **kwargs):
        return f.group(cls=LazyGroup, import_name=import_name, invoke_without_command=True, **kwargs)
    f.lazy_load=lazy_load
    return f

def elva_app_cli(**kwargs):
    """  
    returns a decorator function equivalent to @click.group(**kwargs)
    with the default value of 'invoke_without_command' changed to True
    """

    def decorator(f: Callable):
        if 'invoke_without_command' in kwargs.keys() and not kwargs['invoke_without_command']:
                print_help(click.group(**kwargs)(f)) 
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
        print_help(click.group(**kwargs)(f)) 
        exit()
        
    return decorator

def lazy_group(**kwargs) -> Callable[[Callable], Group]:
    """
    function need to take the arguments:
        identifier: str
        uri: str
        provider: WebsocketProvider like

    get all settings from click context:
        with click.Context(f) as ctx:
            settings = ctx.obj
    like click.group(**kwargs) (with lazy_group) and with default options for elva apps already configured
    """

    def decorator(f: Callable):
        f = elva_app_cli(**kwargs)(f)
        return f
    return decorator

def _lazy_app_processing_callback(ctx: Context, param: None = None, value: None = None):
    settings = dict()

    settings['identifier'] = ctx.params['identifier']

    settings['server'] = ctx.params.pop('server')
    settings['remote_websocket_server'] = ctx.params.pop('remote_websocket_server')
    settings['local_websocket_host'] = ctx.params.pop('local_websocket_host')
    settings['local_websocket_port'] = ctx.params.pop('local_websocket_port')

    if settings['server'] == "remote":
        # connect to the remote websocket server directly, without using the metaprovider
        uri = settings['remote_websocket_server']
        Provider = importlib.import_module('elva.providers').get_websocket_like_elva_provider(settings['identifier'])
    elif settings['server'] == 'local':
        # connect to the local metaprovider
        uri = f"ws://{settings['local_websocket_host']}:{settings['local_websocket_port']}/{settings['identifier']}"
        Provider = importlib.import_module('pycrdt_websocket','WebsocketProvider')

    settings['uri'] = uri
    settings['provider']= Provider
    ctx.params['uri'] = uri 
    ctx.obj = settings

    return Provider 

def print_help(f: Command):
    """
    print help of function f with click.echo, considering f's context
    """

    try:
        with click.Context(f) as ctx:
            click.echo(f.get_help(ctx))
    except: 
        pass

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