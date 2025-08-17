# App Guide

## What is an App?

An ELVA app is a Python [namespace package](https://docs.python.org/3/glossary.html#term-namespace-package)

- defining the functionality - either as a `Textual` app or as something else - and
- providing a command line interface entry point with `click`, from which the app gets the merged configuration parameters.

Namespace packages allows you to write your own app and install it along with others in your local ELVA package.

You will need the following directory tree:

```
 my-app
├── 󰣞 src
│   └──  elva
│       └──  apps
│           └──  my_app
│               ├──  __init__.py
│               ├──  app.py
│               └──  cli.py
└──  pyproject.toml
```

The `pyproject.toml` contains the necessary package configuration.

The content if the `__init__.py` needs to be at least:

```python
# __init__.py
from .cli import cli

__all__ = [cli]
```

so that the ELVA entrypoint script can find the `cli` startup command of your app.

The `cli.py` defines the click command with the appropriate options and arguments.
The `pass_config_for` decorator generating function might be handy for easy access to the final configuration mapping.
Also make sure to set the `LOGGER_NAME` context variable in the command's body to `__package__` (and not `__name__`) for proper logger names.

```python
# cli.py

# only import the bare minimum here;
# this keeps ELVA as performant as possible
from importlib import import_module as import_

import click

from elva.cli import common_options, pass_config_for
from elva.log import LOGGER_NAME

APP_NAME = "my-app"

@click.command(name=APP_NAME)
@common_options
@pass_config_for(APP_NAME)
def cli(config, *args, **kwargs):  # <-- mandatory name!!
    # import the rest here
    dep = import_("my.needed.dependency")
    # ...

    LOGGER_NAME.set(__package__)
    # further logging setup here ...

    # import your app and run it with config mapping
    app = import_("elva.apps.my_app.app")
    app.UI(config).run()

if __name__ == "__main__":
    # run the command if the module is executed directly
    cli()
```

The `app.py` module defines then the actual app functionality.

```python
# app.py

class UI:
    ...
```

This layout comes with several benefits:

- We leverage namespace packages to keep ELVA easily and transparently modular.
- The command invokation is kept performant by deferring imports into the command body.

## Widgets

In analogy to app packages, you can define a new widget namespace package like so:

```
 my-widget
├── 󰣞 src
│   └──  elva
│       └──  widgets
│           └──  my_widget
│               ├──  __init__.py
│               ├──  widget.py
│               └──  auxiliary.py
└──  pyproject.toml
```

Again the `__init__.py` holds the packages initialization code and `__widget__.py` defines the main functionality if your widget.

In contrast to writing apps, ELVA does not specify how certain widget modules need to be named.
You are free to choose your own.

The widget - once installed - will be importable as usual from `elva.widgets.my_widget`.


## Logging and Debugging

For components to work correctly in a module, one needs to import the `LOGGER_NAME` context variable from `elva.log`.
Components initialize a logger instance themselves, but only on instanciation.
Otherwise, the logger name would be wrong and messages would vanish from the app's logging stream.

This approach was chosen to satisfy the following points:

- [The Python logging cookbook discourages](https://docs.python.org/3/howto/logging-cookbook.html#using-loggers-as-attributes-in-a-class-or-passing-them-as-parameters) passing references to logger instances as arguments, which prohibits a class from another module to log to the module's logger.
- The logging shall be streamlined for ELVA apps.

Feel free to also read one of our stories about [Object-specific Logging Across Python Modules](./stories/posts/object-specific-logging-across-python-modules.md) for a more in-depth discussion of logging in this context.
