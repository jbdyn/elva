"""
Module providing the main command line interface functionality.
"""

from functools import partial, wraps
from importlib import import_module as import_
from pathlib import Path
from sqlite3 import DatabaseError
from tomllib import TOMLDecodeError, load
from typing import Any, Callable

from click import (
    ClickException,
    Context,
    Group,
    Parameter,
    echo,
    get_app_dir,
    option,
    pass_context,
)
from click import Path as PathParamType
from click.core import ParameterSource
from deepmerge import always_merger

from elva.core import (
    APP_NAME,
    CONFIG_NAME,
    FILE_SUFFIX,
    LOG_SUFFIX,
    get_command_import_path,
)
from elva.store import get_metadata

deepmerge = always_merger.merge
"""
Deepmerge two dictionaries.
"""


class OrderedGroup(Group):
    """
    Group listing commands in definition order.
    """

    def list_commands(self, ctx: Context | None = None) -> list[str]:
        """
        Lists commands as internally stored.

        Arguments:
            ctx: the CLI context.

        Returns:
            a list of group commands.
        """
        return list(self.commands)


def info(message: str):
    """
    Emit an info to stderr.

    Arguments:
        message: the message to include in the warning.
    """
    echo(message, err=True)


#
# PATHS
#


def get_data_file_path(path: Path) -> Path:
    """
    Ensure a correct and resolved data file path.

    Arguments:
        path: the path to the data file.

    Returns:
        the correct and resolved data file path.
    """
    # resolve given path
    path = path.resolve()

    # append the ELVA data file suffix if necessary
    if FILE_SUFFIX not in path.suffixes:
        path = path.with_name(path.name + FILE_SUFFIX)

    return path


def derive_stem(path: Path, extension: None | str = None) -> Path:
    """
    Derive the data file stem.

    Arguments:
        path: the path to the data file.
        extension: the extension to add to the stem.

    Returns:
        the data file stem.
    """
    # collect all present suffixes
    suffixes = "".join(path.suffixes)

    # get the data file basename
    name = path.name.removesuffix(suffixes)

    # strip all suffixes after the data file suffix
    suffixes = suffixes.split(FILE_SUFFIX, maxsplit=1)[0]

    # translate absent extension definition
    if extension is None:
        extension = ""

    # exchange the file name
    return path.with_name(name + suffixes + extension)


def get_render_file_path(path: Path) -> Path:
    """
    Derive the render file path from the path to a data file.

    Arguments:
        path: the path to the data file.

    Returns:
        the path to the rendered file.
    """
    return derive_stem(path)


def get_log_file_path(path: Path) -> Path:
    """
    Derive the log file path from the path to a data file.

    Arguments:
        path: the path to the data file.

    Returns:
        the path to the log file.
    """
    return derive_stem(path, extension=LOG_SUFFIX)


#
# CONFIGURATION READING AND MERGING
#


def read_data_file(path: str | Path) -> dict:
    """
    Get metadata from file as parameter mapping.

    Arguments:
        path: path where the ELVA SQLite database is stored.

    Returns:
        parameter mapping stored in the ELVA SQLite database.
    """
    try:
        return get_metadata(path, "config")
    except (
        FileNotFoundError,
        PermissionError,
        DatabaseError,
    ) as exc:
        info(f"Ignoring {path}: {exc}")

        return dict()


def read_config_files(paths: list[Path]) -> tuple[list[Path], dict]:
    """
    Get parameters defined in configuration files.

    Arguments:
        paths: list of paths to ELVA configuration files.

    Returns:
        parameter mapping from all configuration files.
        The value from the highest priority configuration overwrites all other parameter values.
    """
    config = dict()

    # filter only first occurences while maintaining order with respect to highest precedence
    unique_paths = list()

    for path in paths:
        path = Path(path)

        path = path.resolve()

        if path not in unique_paths:
            unique_paths.append(path)

    # read and apply each config
    checked_paths = list()

    # go in reversed order because last paths have lowest precedence
    for path in reversed(unique_paths):
        try:
            with path.open(mode="rb") as file:
                data = load(file)
        except (
            FileNotFoundError,
            PermissionError,
            TOMLDecodeError,
        ) as exc:
            info(f"Ignoring {path}: {exc}")
        else:
            # perform a deep merge to merge also app tables
            config = deepmerge(config, data)

            # add this path to our list of successful checks
            checked_paths.append(path)

    checked_paths.reverse()

    return checked_paths, config


#
# CLI CALLBACKS
#


def find_default_config_paths() -> list[Path]:
    """
    CLI default callback finding config files from highest to lowest precedence.

    It first searches project files in the current working directory and in its parents,
    then in the OS-specific app directory.

    Returns:
        a list paths to found config files, sorted by descending precedence.
    """
    paths = []

    # find project config files
    cwd = Path.cwd()

    for path in [cwd] + list(cwd.parents):
        config = path / CONFIG_NAME

        if config.exists():
            paths.append(config)

    # find user home config file
    app_dir = Path(get_app_dir(APP_NAME.lower()))
    app_dir_config = app_dir / CONFIG_NAME

    if app_dir_config.exists():
        paths.append(app_dir_config)

    return paths


def resolve_data_file_path(ctx: Context, param: Parameter, path: Path) -> None | Path:
    """
    CLI callback ensuring a correct and resolved data file path.

    Arguments:
        ctx: the context of the current command invokation.
        param: the data file CLI parameter object.
        path: the value of the data file CLI parameter.

    Returns:
        the correct and resolved data file path if given else `None`.
    """
    if path is not None:
        path = get_data_file_path(path)

    return path


file = option(
    "--file",
    "-f",
    "data",
    help="Set the path to the data file.",
    type=PathParamType(
        path_type=Path,
        exists=False,
        file_okay=True,
        dir_okay=False,
        readable=True,
        writable=True,
        executable=False,
        resolve_path=True,
        allow_dash=False,
    ),
    callback=resolve_data_file_path,
)
"""A CLI command decorator defining the render options and the data file path."""


#
# CLI API
#


def context(arg: Callable | None = None, /, cmd: bool = False) -> Callable:
    """
    Make a function return the subcommand.

    Arguments:
        arg: the first argument needed for convenient operation with and without paranthesis.
        cmd: flag whether to include decorated function in the returned mapping.

    Returns:
        the decorated function.
    """

    def _context(fn: Callable) -> Callable:
        """
        Command decorator for returning the CLI context and the command function in a mapping.

        Arguments:
            fn: the command to get the CLI context from.

        Returns:
            the wrapped command.
        """

        # wrap the command to let `wrapper` look like `cmd`
        # (same name and docstring) but with altered signature
        @wraps(fn)
        @pass_context
        def __context(ctx: Context, **kwargs: Any) -> Any:
            """
            Command wrapper returning the CLI context and, the command function if `cmd` is `True`.

            Arguments:
                ctx: the context of the current command invokation.
                kwargs: keyword arguments passed in from the CLI parser.

            Returns:
                the mapping of the command name to its associated CLI context.
            """
            # map the command's name to its context
            mapping = {
                ctx.command.name: ctx,
            }

            if cmd:
                # include the command function itself
                mapping["cmd"] = fn

            return mapping

        return __context

    # make decorator work with and without paranthesis
    if callable(arg):
        return _context(arg)
    else:
        return _context


app = partial(context, cmd=True)
"""App subcommand decorator returning a routine to run in addition to its CLI context."""


def stored(ctxs: dict[str, Context]) -> dict[str, Any]:
    """
    Initialize a config mapping from config files.

    Arguments
        ctxs: a mapping of CLI contexts to its originating command names.

    Returns:
        the inital config mapping with config from config files.
    """
    # get `config` command config
    ctx = ctxs.pop("config", None)
    config = ctx.params if ctx is not None else dict()

    defaults = config.setdefault("defaults", True)
    files = list(config.setdefault("files", []))

    if defaults:
        files = find_default_config_paths() + files

    paths, out = read_config_files(files)

    out["config"] = config

    # include config paths
    out["config"]["files"] = paths

    return out


def split(ctx: Context) -> tuple[dict, dict]:
    """
    Split CLI parameters into defaults and other.

    Arguments:
        ctx: the CLI context.

    Returns:
        a tuple of a parameter mapping with defaults and a parameter mapping
        with values from other sources.
    """
    default = {}
    given = ctx.params.copy()

    for param in ctx.params:
        source = ctx.get_parameter_source(param)

        if source in (
            ParameterSource.DEFAULT,
            ParameterSource.DEFAULT_MAP,
        ):
            default[param] = given.pop(param)

    return default, given


def merge(config: dict[str, Any], ctxs: dict[str, Context]) -> None:
    """
    Merge a config mapping with a mapping of contexts.

    Order of Precedence (from highest to lowest)

    1. CLI, explicitely given values
    2. data file metadata
    3. additional config files, first has highest precedence
    4. project config files, nearest has highest precedence
    5. app directory config file
    6. CLI defaults

    Arguments:
        config: the config mapping.
        ctxs: the mapping of contexts.
    """
    default = dict()
    data = dict()
    given = dict()

    # collect mappings
    for name, ctx in ctxs.items():
        # read data files
        if (file := ctx.params.get("data")) is not None:
            _data = read_data_file(file)
            data.update(_data)

        # split in default and given CLI parameters
        _default, _given = split(ctx)

        default[name] = _default
        given[name] = _given

    out = dict()

    # deepmerge mappings
    for mapping in (default, config, data, given):
        out = deepmerge(out, mapping)

    return out


def clean(mapping: dict) -> None:
    """
    Clean a config mapping from empty containers and `None` values.

    Nested mappings are clean recursively.

    Arguments:
        mapping: the mapping to clean.
    """
    for key, value in mapping.copy().items():
        if value is None or (type(value) in (list, tuple, dict) and len(value) == 0):
            mapping.pop(key)
        elif isinstance(value, dict):
            clean(value)

            if len(value) == 0:
                mapping.pop(key)


def typecast(config: dict, ctxs: dict[str, Context]) -> None:
    """
    Cast read config file values to their CLI parameter types.

    Arguments:
        config: the config mapping.
        ctxs: the mapping of contexts.
    """
    # iterate over read config sections, not over available commands
    for name in config:
        # import the command
        command_path = get_command_import_path(name)

        try:
            module = import_(command_path)
        except ImportError:
            info(f"Skipping type casting of table {name}: no corresponding command")

            continue

        command = module.cli

        # get or create a context for typecasting
        ctx = ctxs.get(name, Context(command))

        for param in command.params:
            # this parameter might not be in the read config files
            if param.name in config[name]:
                config[name][param.name] = param.type_cast_value(
                    ctx, config[name][param.name]
                )


def run(returned) -> None:
    """
    Routine executed at the end of a chain of group commands.

    Arguments:
        returned: the return values of every invoked group command.
    """
    # merge mappings
    ctxs = dict()

    for mapping in returned:
        ctxs.update(mapping)

    # fail early when there is nothing to run with the config
    cmd = ctxs.pop("cmd", None)

    if cmd is None:
        raise ClickException("no app command specified")

    # read config from config files
    config = stored(ctxs)

    # merge parameters from contexts with file configs
    config = merge(config, ctxs)

    # remove empty and `None` values
    clean(config)

    # convert config file values to their CLI types
    typecast(config, ctxs)

    # run the command
    cmd(config)
