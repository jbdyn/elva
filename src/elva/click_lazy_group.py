"""
Module defining a lazy loading for CLI.
"""

# This file is part of Indico.
# Copyright (C) 2002 - 2024 CERN
#
# Indico is free software; you can redistribute it and/or
# modify it under the terms of the MIT License; see the
# LICENSE file for more details.

from functools import cached_property
from importlib import import_module

import click


# source: https://github.com/indico/indico/blob/3c2d369b6a76a4362750c06340c6d9664e0de330/indico/cli/util.py#L84
class LazyGroup(click.Group):
    """
    A command group that imports the actual implementation only when needed.

    This allows for more resilient CLIs where the top-level
    command does not fail when a subcommand is broken enough to fail
    at import time.
    """

    def __init__(self, import_name, **kwargs):
        self._import_name = import_name
        super().__init__(**kwargs)

    @cached_property
    def _impl(self):
        module, name = self._import_name.split(":", 1)
        return getattr(import_module(module), name)

    def get_command(self, ctx, cmd_name):
        return self._impl.get_command(ctx, cmd_name)

    def list_commands(self, ctx):
        return self._impl.list_commands(ctx)

    def invoke(self, ctx):
        return self._impl.invoke(ctx)

    def get_usage(self, ctx):
        return self._impl.get_usage(ctx)

    def get_params(self, ctx):
        return self._impl.get_params(ctx)
