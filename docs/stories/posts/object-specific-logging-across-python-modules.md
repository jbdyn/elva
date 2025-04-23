---
date: 2025-03-11
author:
  - Jakob Zahn
---

# Object-Specific Logging Across Python Modules

The `logging` module defines the standard way of handling log message flow in Python.
Although powerful and automagic, its setup can be a bit more involved for not-quite-standard situations, like having a separate logger for each instance of a class.
Also, mentioned best practices requires non-intuitive solutions by the using programmer.
Read on for some recipes outside the default cookbook.

<!-- more -->

## Where to Start

That ... might be the first hurdle to take.
Logging does not work straight away without reading at least some of [the documentation](https://docs.python.org/3/library/logging.html).
It is not enough to simply import and use it:

```python
# not working
import logging

logging.info("this won't get logged anywhere")
```

but you need to set at least the level as well:

```python
# minimal working example
import logging

logging.basicConfig(level=logging.INFO)  # some config magic
logging.info("this will get printed to stdout by the root logger") # method of the root logger
```

Executing this prints

```
INFO:root:this will get printed to stdout by the root logger
```

to your terminal.

An equivalent version of the minimal working example would be

```python
# explicit minimal working example
import logging

logger = logging.getLogger()  # or getLogger("") or getLogger("root")
logger.setLevel(logging.INFO)
logging.info("also printed but only when using the root logger")  # method of the root logger
```

which sets the `logging.INFO` level on the root logger.

However, when using the logger instance to log a message, you would also need to specify a handler:

```python
import logging

logger = logging.getLogger("my-logger")
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())
logger.info("this gets printed to stdout by 'my-logger' logger via its StreamHandler")  # method of the my-logger logger
```

Here, we added a `logging.StreamHandler` instance, which by default writes to the `stdout` stream.
Only the message methods directly callable by the `logging` module's name - like `logging.info()` - define a default handler.


## The Unusual Case

ELVA has lots of moving parts, and for debugging them if something goes wrong, proper logging is *tremendously* important.

What we want is:

- a per-app logger instance,
- a per-app logger configuration,
- information from which component in which app a log message originated, so per-component logger instances, and
- configuration inheritance must work.

See, ELVA's mechanisms are based on the `Component` class, a generic object from which parts of an app such as a provider or a store are derived, united via a backbone of Y data types.
For debugging, it is way easier to have some information in the log messages which point to their origin to narrow down the search.

The `Component` class is defined in its own module `component.py`, but subclasses are written down in other modules, which in turn get instanciated in the app modules.
So, how do we make a subclass of `Component` log with the needed information attached in an app?


The logging cookbook has a section about [patterns to avoid](https://docs.python.org/3/howto/logging-cookbook.html#patterns-to-avoid) when setting up log functionality, from which the following turned out to be the most interesting for the ELVA project:

- Don't use the root logger, as this might interfere with loggers in other projects.
  Configure your own with a custom logger name.
  That is okay, we already said we need more than one global logger and ELVA is a project intended to be used in other projects.
- Don't use too much different loggers, as they are singletons.
  Their memory [won't get freed until the end of script execution](https://docs.python.org/3/howto/logging-cookbook.html#creating-a-lot-of-loggers).
  Uhm, we will come back to that when that should become an issue.
- Don't store references to logger instances in attributes or give them as parameters.
  According to the cookbook, [it is not necessary in usual cases](https://docs.python.org/3/howto/logging-cookbook.html#using-loggers-as-attributes-in-a-class-or-passing-them-as-parameters).
  That is a tough one, and when we use a per-class logging, impossible.
  But ELVA isn't a usual case.

Let's see how far we can go.


## What (Not) Works

The core problem is to get the logger name right.
Only with the right logger name inheritance of the logging configuration can happen properly.

If the logger is defined with a hard-coded name in the `component.py` module, the maximum detail we can get is that a log message came from a `Component` instance named `MyComponentName`.
We cannot know in which app the component is currently running in.
The same is true when defining the logger name in another module other than the app module itself. 

So, we need to set the app's root logger name - not to be confused with the `root` logger - in the app modulewhere the configuration happens.
I could think of two ways:

The first one conservatively uses [`logging.LoggerAdapter`](https://docs.python.org/3/library/logging.html#logging.LoggerAdapter)s as also somewhat [suggested in the `logging` cookbook](https://docs.python.org/3/howto/logging-cookbook.html#using-loggeradapters-to-impart-contextual-information).
`LoggerAdapter` objects intercept a logger's message processing with a custom logic.
In the example below, we simply prepend a made up name to every logged message:

```python
import logging

class NameAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return '[%s] %s' % (self.extra["name"], msg), kwargs

log = logging.getLogger("my-logger")
log.setLevel(logging.INFO)
log.addHandler(logging.StreamHandler())

log_with_name = NameAdapter(log, {"name": "foo"})
log_with_name.info("bar")
```

Upon execution, this prints

```
[foo] bar
```

But where do we get the `log` instance in the line

```python
log_with_name = NameAdapter(log, {"name": "foo"})
```

from, when this was defined in a class method?
We would need to pass it as argument, which collides with the third pattern to avoid and adds to our component constructor signature.
Additionally, we had to define custom adapter logic.

The second approach solves this more magically, which might be more in line with the `logging` module's nature.
It leverages the context variables realized with the `contextvars.ContextVar` class, but not in the way the `logging` cookbook uses them.

In ELVA's central logging module `log.py`, we define the logger name as context variable:

```python
from contextvars import ContextVar

LOGGER_NAME = ContextVar("logger_name")
```

The module attribute `LOGGER_NAME` is then imported in the component's module to *get* the logger name from context:

```python
# in component module
import logging
from elva.log import LOGGER_NAME

class Component:

    # ...

    def __new__(cls, *args, **kwargs):
        self = super().__new__(cls)

        # self.__module__ is the default when no other value is present
        name = LOGGER_NAME.get(self.__module__) 

        self.log = logging.getLogger(f"{name}.{self.__class__.__name__}")

        # level is inherited from parent logger
        self.log.setLevel(logging.NOTSET)
        return self

    # ...
```

and imported in the app module to *set* the logger name to context:

```python
# in app module
import logging
from elva.log import LOGGER_NAME

log = logging.getLogger(__name__)

# ...

if __name__ == "__main__":
    # ...

    # set it to the same name as the app root logger,
    # so that components inherit its configuration
    LOGGER_NAME.set(__name__)

    # ...
```

Okay, to be fair, we had to write a custom [`__new__`](https://docs.python.org/3/reference/datamodel.html#object.__new__) method, which does not seem much different to a custom `LoggerAdapter`.
But, with the context variable, we don't need to pass the logging instance as a parameter anymore, which simplifies the component signatures and in turn the code itself to some noticable extent.
Also, we solved the problem at its core: We found a way to set the logger names for every part of an app in the app module while defining logging instances in auxiliary modules.

We just need to watch out for setting the `LOGGER_NAME` variable in an `if __name__ == "__main__"` clause.
Otherwise, just importing from this very module would also set the `LOGGER_NAME` context, which might be undesired.


## A Look Around

You might also want to check out [`loguru`](https://loguru.readthedocs.io/en/stable/overview.html#x-faster-than-built-in-logging) if you want to get a headstart with respect to logging in your project.

Whether ELVA would profit from that remains to be seen in a sophisticated test.
