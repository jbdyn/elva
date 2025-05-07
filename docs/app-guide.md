# App Guide

## What is an App?

An ELVA app is a python module

- defining the functionality - either as a `Textual` app or as something else - and
- providing a command line interface entry point with `click`, from which the app gets the merged configuration parameters.

Hence, an app needs to be findable by ELVA so that it can import the CLI command and pass the invokation context to it.


## Basic App Module Structure

An app module looks like this:

```python
import click
from elva.log import LOGGER_NAME
from elva.utils import gather_context_information
# other imports here ...

# app logic here ...

@click.command
@click.pass_context
def cli(ctx, ...):
    # collect all given parameters and merge them
    gather_context_information(ctx, file=somefile, app=someapp)

    # this is the mapping of the merged configuration parameters
    c = ctx.obj

    # do something with the given parameters ...
    
    # set the context variable so that components
    # log to the right logger in the right format
    LOGGER_NAME.set(__name__)

    # start your app here ...


if __name__ == "__main__":
    # run the command if the module is executed directly
    cli()
```


## Logging and Debugging

For components to work correctly in a module, one needs to import the `LOGGER_NAME` context variable from `elva.log`.
Components initialize a logger instance themselves, but only on instanciation.
Otherwise, the logger name would be wrong and messages would vanish from the app's logging stream.

This approach was chosen to satisfy the following points:

- [The Python logging cookbook discourages](https://docs.python.org/3/howto/logging-cookbook.html#using-loggers-as-attributes-in-a-class-or-passing-them-as-parameters) passing references to logger instances as arguments, which prohibits a class from another module to log to the module's logger.
- The logging shall be streamlined for ELVA apps.
