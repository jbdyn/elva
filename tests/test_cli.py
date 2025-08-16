import os
from pathlib import Path

import click
import pytest
import tomli_w
from click.testing import CliRunner

import elva.auth as _auth
import elva.cli as _cli
import elva.core as _core
import elva.store as _store


@pytest.fixture
def runner() -> CliRunner:
    """
    Get a CLI Runner not catching any exceptions like `AssertionError`s.

    Warning:
        It is still necessary to set `standalone_mode = False` on invokation
        to also catch `click` internal errors like wrong option specification.

    Example:
        runner.invoke(cmd, args=["--foo", "bar], standalone_mode=False)
    """
    return CliRunner(catch_exceptions=False)


def test_get_composed_decorator():
    """A composed decorator has the same functionality as defined separately."""

    def get_decorator(val):
        """
        Getter for the `append` test decorator.
        """

        def append(f):
            """
            Decorator which appends `val` to the return value of `f`.
            """

            def _append(*args, **kwargs):
                return f(*args, **kwargs) + [val]

            return _append

        return append

    # define values to append
    values = ["foo", "bar", "baz"]

    # create decorators
    decorators = tuple(get_decorator(val) for val in values)

    # unpack to singular decorators
    append_foo, append_bar, append_baz = decorators

    # the result is in reverse order of the values, i.e. decorators, given
    expected = ["run", "baz", "bar", "foo"]

    # write out the decorators individually
    @append_foo
    @append_bar
    @append_baz
    def run():
        return ["run"]

    # again, everything got appended in the expected order
    assert run() == expected

    # compose decorators into one decorator
    composed = _cli.get_composed_decorator(*decorators)

    # define function decorated with composed decorator
    @composed
    def run():
        return ["run"]

    # everything got appended in the expected order
    assert run() == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    (
        ("test", "test.y"),
        ("test.y", "test.y"),
        ("test.md", "test.md.y"),
        ("test.md.y", "test.md.y"),
        ("test.md.y.bak", "test.md.y.bak"),
    ),
    ids=(
        "no suffixes",
        "with '.y' suffix",
        "with filetype but without '.y' suffix",
        "with filetype and '.y' suffix",
        "with '.y' and filetype suffix",
    ),
)
def test_get_data_file_path(tmp_path: Path, path: str, expected: str):
    # ensure we are working in `tmp_path`
    os.chdir(tmp_path)
    assert Path.cwd() == tmp_path

    # get the data file path
    data_file_path = _cli.get_data_file_path(Path(path))

    # the file name and the resolved path are as expected
    assert data_file_path.name == expected
    assert str(data_file_path) == str(tmp_path / expected)


@pytest.mark.parametrize(
    ("path", "expected"),
    (
        ("test", "test"),
        ("test.y", "test"),
        ("test.md", "test.md"),
        ("test.md.y", "test.md"),
        ("test.md.y.bak", "test.md"),
    ),
    ids=(
        "no suffixes",
        "with '.y' suffix",
        "with filetype but without '.y' suffix",
        "with filetype and '.y' suffix",
        "with '.y' and filetype suffix",
    ),
)
def test_derive_stem(path, expected):
    # convert to satisfy argument types
    path = Path(path)

    # the stem is as expected
    stem = _cli.derive_stem(path)
    assert stem.name == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    (
        ("test", "test"),
        ("test.y", "test"),
        ("test.md", "test.md"),
        ("test.md.y", "test.md"),
        ("test.md.y.bak", "test.md"),
    ),
    ids=(
        "no suffixes",
        "with '.y' suffix",
        "with filetype but without '.y' suffix",
        "with filetype and '.y' suffix",
        "with '.y' and filetype suffix",
    ),
)
def test_render_file_path(path, expected):
    # convert to satisfy argument types
    path = Path(path)

    # the render file name is equal to the stem,
    # as no additional extension is specified
    render_file_path = _cli.get_render_file_path(path)
    assert render_file_path.name == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    (
        ("test", "test.log"),
        ("test.y", "test.log"),
        ("test.md", "test.md.log"),
        ("test.md.y", "test.md.log"),
        ("test.md.y.bak", "test.md.log"),
    ),
    ids=(
        "no suffixes",
        "with '.y' suffix",
        "with filetype but without '.y' suffix",
        "with filetype and '.y' suffix",
        "with '.y' and filetype suffix",
    ),
)
def test_log_file_path(path, expected):
    # convert to satisfy argument types
    path = Path(path)

    # the log file name is the stem + _cli.LOG_SUFFIX
    log_file_path = _cli.get_log_file_path(path)
    assert log_file_path.name == expected


@pytest.mark.parametrize(
    ("metadata", "expected", "warn"),
    (
        (None, dict(), True),
        ({"foo": "bar", "baz": 42}, {"foo": "bar", "baz": 42}, False),
        ("text", dict(), True),
    ),
    ids=(
        "absent file",
        "present and valid file",
        "present in invalid file",
    ),
)
def test_read_data_file(tmp_path, capfd, metadata, expected, warn):
    # we know this works correctly
    data_file_path = _cli.get_data_file_path(tmp_path / "test")

    # write data to file
    if isinstance(metadata, str):
        with data_file_path.open(mode="w") as file:
            file.write(metadata)
    elif isinstance(metadata, dict):
        _store.set_metadata(data_file_path, metadata)

    # the return dict is populated as expected
    res = _cli.read_data_file(data_file_path)
    assert res == expected

    # no output to stdout
    captured = capfd.readouterr()
    assert captured.out == ""

    # we expect output to stderr in some cases
    if warn:
        assert captured.err != ""
    else:
        assert captured.err == ""


#
# SETUP FOR `test_read_config_files`
#

VALID_DATA_FOO = {
    "a": "b",
    "baz": {
        "quux": 42,
    },
    "dubbed": "foo",
}
VALID_TOML_FOO = tomli_w.dumps(VALID_DATA_FOO)

VALID_DATA_BAR = {
    "x": "y",
    "baz": {
        "blub": 3.14,
    },
    "dubbed": "bar",
}
VALID_TOML_BAR = tomli_w.dumps(VALID_DATA_BAR)

VALID_DATA_BAR_FOO = {
    # different keys get collected
    "a": "b",
    "x": "y",
    # `read_config_files` performs a deepmerge
    "baz": {
        "quux": 42,
        "blub": 3.14,
    },
    # `foo.toml` is read in last
    "dubbed": "foo",
}

INVALID_TOML = "foo == bar"


@pytest.mark.parametrize(
    # `"paths"` are relative to `tmp_path`,
    # `"expected"` contains `(checked_paths, config)`
    ("paths", "data", "expected", "warn"),
    (
        #
        # no paths, no files, no warnings
        #
        ([], [], ([], {}), False),
        #
        # single dummy path, no file, warning due to non-existing file
        (
            [None],
            [None],
            ([], {}),
            True,
        ),
        #
        # single test path, valid file, no warning
        #
        (
            ["foo.toml"],
            [VALID_TOML_FOO],
            (["foo.toml"], VALID_DATA_FOO),
            False,
        ),
        #
        # single test path, invalid file, warning due to decoding issues
        #
        (
            ["foo.toml"],
            [INVALID_TOML],
            ([], {}),
            True,
        ),
        #
        # multiple test paths, valid files, no warnings
        #
        (
            ["foo.toml", "bar.toml"],
            [VALID_TOML_FOO, VALID_TOML_BAR],
            (["foo.toml", "bar.toml"], VALID_DATA_BAR_FOO),
            False,
        ),
        #
        # multiple test paths with one dummy, valid files,
        # warnings due to non-existing file
        #
        (
            ["foo.toml", None, "bar.toml"],
            [VALID_TOML_FOO, None, VALID_TOML_BAR],
            (["foo.toml", "bar.toml"], VALID_DATA_BAR_FOO),
            True,
        ),
        #
        # multiple test paths, invalid files, warnings due to decoding issues
        #
        (
            ["foo.toml", "bar.toml"],
            [INVALID_TOML, INVALID_TOML],
            ([], {}),
            True,
        ),
        #
        # multiple test paths with one dummy, partially valid files,
        # warnings due to non-existing file or decoding issues
        #
        (
            ["foo.toml", None, "bar.toml"],
            [INVALID_TOML, None, VALID_TOML_BAR],
            (["bar.toml"], VALID_DATA_BAR),
            True,
        ),
        #
        # doubled test paths, doubled files, no warnings
        #
        (
            ["foo.toml", "foo.toml"],
            [VALID_TOML_FOO, VALID_TOML_BAR],
            (["foo.toml"], VALID_DATA_BAR),
            False,
        ),
        #
        # partially doubled test paths, partially doubled files, no warnings
        #
        (
            ["foo.toml", "bar.toml", "foo.toml"],
            [VALID_TOML_FOO, VALID_TOML_BAR, VALID_TOML_FOO],
            (["foo.toml", "bar.toml"], VALID_DATA_BAR_FOO),
            False,
        ),
    ),
    ids=(
        "empty list of files",
        "absent file",
        "present and valid file",
        "present but invalid file",
        "present and valid files",
        "partially present and fully valid files",
        "present but invalid files",
        "partially present and partially valid files",
        "doubled file",
        "partially doubled file",
    ),
)
def test_read_config_files(tmp_path, capfd, paths, data, expected, warn):
    # ensure we are working in `tmp_path`
    os.chdir(tmp_path)
    assert Path.cwd() == tmp_path

    # write data to path if given, else just create a dummy path
    for p, (path, data) in enumerate(zip(paths.copy(), data)):
        if path is not None:
            # check that we have some data to write
            assert data is not None

            path = Path(path)
            with path.open(mode="w") as file:
                file.write(data)

            paths[p] = path
        else:
            assert data is None
            paths[p] = Path("not-existing-on-disk.toml")

    # we managed to convert all string paths to instances of `Path`
    for path in paths:
        assert isinstance(path, Path)

    # convert expected paths
    expected_paths, expected_config = expected
    expected_paths = [Path(path).resolve() for path in expected_paths]

    # get the checked paths and underlying config
    checked_paths, config = _cli.read_config_files(paths)

    # everything is as expected
    assert checked_paths == expected_paths
    assert config == expected_config

    # no output to stdout ever
    captured = capfd.readouterr()
    assert captured.out == ""

    # we expect output to stderr in some cases
    if warn:
        assert captured.err != ""
    else:
        assert captured.err == ""


#
# SETUP FOR `test_merge_configs`
#

# a separate run directory because of search in the app dir by `click`
RUN_PATH = Path("run")


def noop(f):
    """A decorator which does nothing."""

    def _noop(*args, **kwargs):
        return f(*args, **kwargs)

    return _noop


# composed the config option decorators together
composed_configs = _cli.get_composed_decorator(
    _cli.configs_option,
    _cli.additional_configs_option,
)

DATA_FOO = {
    "a": "b",
    "baz": {
        "quux": 42,
    },
    "dubbed": "foo",
}
TOML_FOO = tomli_w.dumps(DATA_FOO)

DATA_ELVA = {
    "baz": {
        "qwix": "i",
    },
    "dubbed": "elva",
}
TOML_ELVA = tomli_w.dumps(DATA_ELVA)

DATA_APP_DIR = {
    "dubbed": "app_dir",
}
TOML_APP_DIR = tomli_w.dumps(DATA_APP_DIR)

# an option to overwrite or to be overwritten
dubbed_option = click.option(
    "--dubbed",
    default="dubbed_default",
)

# also use the data file argument
composed_configs_dubbed_data_file = _cli.get_composed_decorator(
    _cli.configs_option,
    _cli.additional_configs_option,
    dubbed_option,
    _cli.data_file_path_argument,
)

# metadata in data file
DATA_FILE = {
    "dubbed": "data_file",
}


@pytest.mark.parametrize(
    ("paths", "metadata", "api", "params", "app", "expected"),
    (
        #
        # noop
        #
        ([], [], noop, [], None, {}),
        #
        # COMPOSED CONFIGS
        #
        #
        # config options without arguments;
        # config is empty since there are no default config files
        #
        (
            [],
            [],
            composed_configs,
            [],
            None,
            {},
        ),
        #
        # default configs with additional config specified;
        # empty config since there are no config files
        #
        (
            [],
            [],
            composed_configs,
            ["--config", "test.toml"],
            None,
            {},
        ),
        #
        # default empty config file present
        #
        (
            [_cli.CONFIG_NAME],
            [None],
            composed_configs,
            [],
            None,
            {
                "configs": [_cli.CONFIG_NAME],
            },
        ),
        #
        # additional empty config present, no default configs
        #
        (
            ["foo.toml"],
            [None],
            composed_configs,
            ["--additional-config", "foo.toml"],
            None,
            {
                "configs": ["foo.toml"],
            },
        ),
        #
        # additional filled config present, no default configs,
        # without app table `baz`
        #
        (
            ["foo.toml"],
            [TOML_FOO],
            composed_configs,
            ["--additional-config", "foo.toml"],
            None,
            {
                "configs": ["foo.toml"],
                "a": "b",
                "dubbed": "foo",
            },
        ),
        #
        # additional filled config present, no default configs,
        # with data from app table `baz`
        #
        (
            ["foo.toml"],
            [TOML_FOO],
            composed_configs,
            ["--additional-config", "foo.toml"],
            "baz",
            {
                "configs": ["foo.toml"],
                "a": "b",
                "quux": 42,
                "dubbed": "foo",
            },
        ),
        #
        # default empty and additional empty config present,
        # additional config has higher precedence
        #
        (
            [_cli.CONFIG_NAME, "foo.toml"],
            [None, None],
            composed_configs,
            ["--additional-config", "foo.toml"],
            None,
            {
                "configs": ["foo.toml", _cli.CONFIG_NAME],
            },
        ),
        #
        # default and additional config present,
        # the additional overwrites the default
        #
        (
            [_cli.CONFIG_NAME, "foo.toml"],
            [TOML_ELVA, TOML_FOO],
            composed_configs,
            ["--additional-config", "foo.toml"],
            None,
            {
                "configs": ["foo.toml", _cli.CONFIG_NAME],
                "a": "b",
                "dubbed": "foo",
            },
        ),
        #
        # default paths replaced, only replaced config listed
        #
        (
            [_cli.CONFIG_NAME, "foo.toml"],
            [None, None],
            composed_configs,
            ["--config", "foo.toml"],
            None,
            {
                "configs": ["foo.toml"],
            },
        ),
        #
        # default config paths replaced, then additional config specified,
        # only specified paths listed, additional one has higher precedence
        #
        (
            ["foo.toml", "bar.toml"],
            [None, None],
            composed_configs,
            ["--config", "foo.toml", "--additional-config", "bar.toml"],
            None,
            {
                "configs": ["bar.toml", "foo.toml"],
            },
        ),
        #
        # additional config specified, then default config paths replaced,
        # only specified paths listed, additional one has higher precedence
        #
        (
            ["foo.toml", "bar.toml"],
            [None, None],
            composed_configs,
            ["--additional-config", "bar.toml", "--config", "foo.toml"],
            None,
            {
                "configs": ["bar.toml", "foo.toml"],
            },
        ),
        #
        # COMPOSED CONFIGS WITH APP DIRECTORY CONFIG
        #
        #
        # app directory config present and filled
        #
        (
            ["../" + _cli.CONFIG_NAME],
            [TOML_APP_DIR],
            composed_configs,
            [],
            None,
            {
                "configs": ["../" + _cli.CONFIG_NAME],
                "dubbed": "app_dir",
            },
        ),
        #
        # app directory and default config present,
        # default config has higher precedence
        #
        (
            ["../" + _cli.CONFIG_NAME, _cli.CONFIG_NAME],
            [TOML_APP_DIR, TOML_ELVA],
            composed_configs,
            [],
            None,
            {
                "configs": [_cli.CONFIG_NAME, "../" + _cli.CONFIG_NAME],
                "dubbed": "elva",
            },
        ),
        #
        # CONFIGS WITH DUBBED OPTION AND DATA FILE ARGUMENT
        #
        #
        # no input, no configs,
        # only default value from `dubbed` option present
        #
        (
            [],
            [],
            composed_configs_dubbed_data_file,
            [],
            None,
            {
                "dubbed": "dubbed_default",
            },
        ),
        #
        # only dubbed option specified, overwrites its default
        #
        (
            [],
            [],
            composed_configs_dubbed_data_file,
            ["--dubbed", "dubbed_cli"],
            None,
            {
                "dubbed": "dubbed_cli",
            },
        ),
        #
        # default config file has higher precedence over CLI defaults
        #
        (
            [_cli.CONFIG_NAME],
            [TOML_ELVA],
            composed_configs_dubbed_data_file,
            [],
            None,
            {
                "configs": [_cli.CONFIG_NAME],
                "dubbed": "elva",
            },
        ),
        #
        # explicit CLI values have higher precedence than default configs
        #
        (
            [_cli.CONFIG_NAME],
            [TOML_ELVA],
            composed_configs_dubbed_data_file,
            ["--dubbed", "dubbed_cli"],
            None,
            {
                "configs": [_cli.CONFIG_NAME],
                "dubbed": "dubbed_cli",
            },
        ),
        #
        # only data file specified, no default configs present
        #
        (
            ["data.y", "data", "data.log"],
            [DATA_FILE, None, None],
            composed_configs_dubbed_data_file,
            ["data.y"],
            None,
            {
                "dubbed": "data_file",
                "file": "data.y",
                "render": "data",
                "log": "data.log",
            },
        ),
        #
        # data file has higher precedence than default config
        #
        (
            [_cli.CONFIG_NAME, "data.y", "data", "data.log"],
            [TOML_ELVA, DATA_FILE, None, None],
            composed_configs_dubbed_data_file,
            ["data.y"],
            None,
            {
                "configs": [_cli.CONFIG_NAME],
                "dubbed": "data_file",
                "file": "data.y",
                "render": "data",
                "log": "data.log",
            },
        ),
        #
        # explicit CLI values have higher precedence than data file metadata
        # and CLI defaults
        #
        (
            [_cli.CONFIG_NAME, "data.y", "data", "data.log"],
            [TOML_ELVA, DATA_FILE, None, None],
            composed_configs_dubbed_data_file,
            ["--dubbed", "dubbed_cli", "data.y"],
            None,
            {
                "configs": [_cli.CONFIG_NAME],
                "dubbed": "dubbed_cli",
                "file": "data.y",
                "render": "data",
                "log": "data.log",
            },
        ),
        #
        # CONFIGS WITH DUBBED OPTION, DATA FILE ARGUMENT AND APP DIR CONFIG
        #
        #
        # data file has higher precedence than app directory config,
        # default config and CLI defaults
        #
        (
            ["../" + _cli.CONFIG_NAME, _cli.CONFIG_NAME, "data.y", "data", "data.log"],
            [TOML_APP_DIR, TOML_ELVA, DATA_FILE, None, None],
            composed_configs_dubbed_data_file,
            ["data.y"],
            None,
            {
                "configs": [_cli.CONFIG_NAME, "../" + _cli.CONFIG_NAME],
                "dubbed": "data_file",
                "file": "data.y",
                "render": "data",
                "log": "data.log",
            },
        ),
        #
        # explicit CLI values have higher precedence than data file metadata,
        # default config, app directory config and CLI defaults
        #
        (
            ["../" + _cli.CONFIG_NAME, _cli.CONFIG_NAME, "data.y", "data", "data.log"],
            [TOML_APP_DIR, TOML_ELVA, DATA_FILE, None, None],
            composed_configs_dubbed_data_file,
            ["--dubbed", "dubbed_cli", "data.y"],
            None,
            {
                "configs": [_cli.CONFIG_NAME, "../" + _cli.CONFIG_NAME],
                "dubbed": "dubbed_cli",
                "file": "data.y",
                "render": "data",
                "log": "data.log",
            },
        ),
        #
        # app name is accounted for
        #
        (
            ["../" + _cli.CONFIG_NAME, _cli.CONFIG_NAME, "data.y", "data", "data.log"],
            [TOML_APP_DIR, TOML_ELVA, DATA_FILE, None, None],
            composed_configs_dubbed_data_file,
            ["--dubbed", "dubbed_cli", "data.y"],
            "baz",
            {
                "configs": [_cli.CONFIG_NAME, "../" + _cli.CONFIG_NAME],
                "dubbed": "dubbed_cli",
                "qwix": "i",
                "file": "data.y",
                "render": "data",
                "log": "data.log",
            },
        ),
        #
        # deep merge is performed on app config
        #
        (
            [
                "../" + _cli.CONFIG_NAME,
                _cli.CONFIG_NAME,
                "foo.toml",
                "data.y",
                "data",
                "data.log",
            ],
            [TOML_APP_DIR, TOML_ELVA, TOML_FOO, DATA_FILE, None, None],
            composed_configs_dubbed_data_file,
            ["--additional-config", "foo.toml", "--dubbed", "dubbed_cli", "data.y"],
            "baz",
            {
                "configs": ["foo.toml", _cli.CONFIG_NAME, "../" + _cli.CONFIG_NAME],
                "a": "b",
                "dubbed": "dubbed_cli",
                "qwix": "i",
                "quux": 42,
                "file": "data.y",
                "render": "data",
                "log": "data.log",
            },
        ),
    ),
)
def test_merge_configs(runner, tmp_path, paths, metadata, api, params, app, expected):
    # ensure app dir is in `tmp_path`
    tmp_path_str = str(tmp_path)
    env = {
        # Unix, POSIX
        "HOME": tmp_path_str,
        "XDG_CONFIG_HOME": tmp_path_str,
        # Windows
        "APPDATA": tmp_path_str,
        "LOCALAPPDATA": tmp_path_str,
    }

    # set current working directory
    cwd = tmp_path / RUN_PATH
    cwd.mkdir()

    os.chdir(cwd)
    assert Path.cwd() == cwd

    # convert and resolve given path strings
    full_paths = dict()

    for path, data in zip(paths, metadata):
        # resolve relative paths
        file = (cwd / path).resolve()

        # create files with or without content
        if isinstance(data, str):
            with file.open(mode="w") as fd:
                fd.write(data)
        elif isinstance(data, dict):
            _store.set_metadata(file, data)
        elif data is None:
            file.touch()

        # save converted path
        full_paths[path] = file

    # all present paths point to existing files
    for path in full_paths.values():
        assert path.exists()

    # replace expected config paths
    config_paths = expected.get("configs")
    if config_paths is not None:
        config_paths = [full_paths[path] for path in config_paths]
        expected["configs"] = config_paths

    # replace file paths
    for key in ("file", "render", "log"):
        value = expected.get(key)
        if value is not None:
            expected[key] = full_paths[value]

    # def test command
    @click.command
    @api
    @click.pass_context
    def merge_configs_manually(ctx, *args, **kwargs):
        # `click` really returns a path in `tmp_path`
        app_dir = Path(click.get_app_dir(_core.APP_NAME.lower()))
        assert app_dir.is_relative_to(tmp_path)

        # the merged config is as expected
        config = _cli.merge_configs(ctx, app=app)
        assert config == expected

    # invoke the command
    runner.invoke(merge_configs_manually, args=params, env=env, standalone_mode=False)


# a separate run directory because of search in the app dir by `click`
RUN_PATH = Path("run")


def test_find_default_config_paths(runner, tmp_path):
    # ensure app dir is in `tmp_path`
    tmp_path_str = str(tmp_path)
    env = {
        # Unix, POSIX
        "HOME": tmp_path_str,
        "XDG_CONFIG_HOME": tmp_path_str,
        # Windows
        "APPDATA": tmp_path_str,
        "LOCALAPPDATA": tmp_path_str,
    }

    # create run and config directories
    run_path = tmp_path / RUN_PATH
    run_path.mkdir()

    dirs = [
        "foo",
        "foo/bar",
        "foo/bar/baz",
    ]
    innermost = run_path / dirs[-1]
    innermost.mkdir(parents=True)

    # set current working directory
    os.chdir(innermost)
    assert Path.cwd() == innermost

    # create empty config files from the outermost to the innermost directory
    config_paths = [
        path / _core.CONFIG_NAME
        for path in [run_path] + [run_path / dir for dir in dirs]
    ]
    for config_path in config_paths:
        config_path.touch()

    # we need to reverse the list of config paths since
    # the routine `find_default_config_paths` searches from
    # the innermost the outermost path
    config_paths.reverse()

    # define test command
    @click.command
    def get_default_config_paths(*args, **kwargs):
        default_paths = _cli.find_default_config_paths()

        assert default_paths == config_paths

    runner.invoke(get_default_config_paths, env=env, standalone_mode=False)

    # add an app directory config file to `tmp_path` and the list of
    # config paths
    app_dir_config = tmp_path / _cli.CONFIG_NAME
    config_paths.append(app_dir_config)
    app_dir_config.touch()

    runner.invoke(get_default_config_paths, env=env, standalone_mode=False)


def test_pass_empty_config(runner):
    @click.command
    @_cli.pass_config
    def get_config(config, *args, **kwargs):
        # we get a dictionary
        assert isinstance(config, dict)
        assert isinstance(args, tuple)
        assert isinstance(kwargs, dict)

        # since we didn't specify options, arguments or passing context,
        # all parameters are empty
        for passed in (config, args, kwargs):
            assert len(passed) == 0

    runner.invoke(get_config, standalone_mode=False)


def test_pass_config_and_context(runner):
    # pass config first, then the context
    @click.command
    @click.pass_context  # <--
    @_cli.pass_config  # <--
    def get_config_then_context(config, ctx, *args, **kwargs):
        # we have an empty config dictionary
        assert isinstance(config, dict)

        # we get a context with no parameters
        assert isinstance(ctx, click.Context)

        # no parameters anywhere
        for passed in (config, ctx.params, args, kwargs):
            assert len(passed) == 0

    runner.invoke(get_config_then_context, standalone_mode=False)

    # pass context first, then the config
    @click.command
    @_cli.pass_config  # <--
    @click.pass_context  # <--
    def get_context_then_config(ctx, config, *args, **kwargs):
        # we get a context
        assert isinstance(ctx, click.Context)

        # we have a config dictionary
        assert isinstance(config, dict)

        # no parameters anywhere
        for passed in (ctx.params, config, args, kwargs):
            assert len(passed) == 0

    runner.invoke(get_context_then_config, standalone_mode=False)


def test_pass_custom_config(runner):
    @click.command
    @click.option("--foo")
    @click.argument("bar", required=False)
    @_cli.pass_config
    def get_config(config, *args, **kwargs):
        return config, args, kwargs

    # no options and arguments specified
    # disable standalone_mode to get the return value
    res = runner.invoke(get_config, standalone_mode=False)
    config, args, kwargs = res.return_value

    # config is empty since we clean `None`
    assert config == dict()

    # click passed arguments as keyword arguments, not as positional
    assert args == tuple()

    # we see the value of command option and argument
    assert "foo" in kwargs
    assert kwargs["foo"] is None
    assert "bar" in kwargs
    assert kwargs["bar"] is None

    # with options and arguments specified
    # disable standalone_mode to get the return value
    res = runner.invoke(get_config, ["--foo", "baz", "quux"], standalone_mode=False)
    config, args, kwargs = res.return_value

    # config holds custom key-value pairs
    assert "foo" in config
    assert config["foo"] == "baz"
    assert "bar" in config
    assert config["bar"] == "quux"

    # positional arguments are still empty as before
    assert args == tuple()

    # keyword arguments are still the same as before
    assert "foo" in kwargs
    assert kwargs["foo"] == "baz"
    assert "bar" in kwargs
    assert kwargs["bar"] == "quux"


def test_misuse_of_pass_config_for():
    with pytest.raises(ValueError):

        @_cli.pass_config_for  # <-- misuse: no round brackets
        def test(config):
            pass


@pytest.mark.parametrize(
    ("pass_config_decorator", "expected"),
    (
        # app is None
        (
            _cli.pass_config_for(),
            {
                "foo": "bar",
            },
        ),
        # we also want key-value pairs from `my-app` section
        (
            _cli.pass_config_for("my-app"),
            {
                "foo": "bar",
                "baz": "quux",
            },
        ),
        # we want key-value pairs from `another-app` section,
        # which is not present in the config
        (
            _cli.pass_config_for("another-app"),
            {
                "foo": "bar",
            },
        ),
    ),
    ids=(
        "no app specified",
        "present app specified",
        "absent app specified",
    ),
)
def test_pass_config_for(tmp_path, runner, pass_config_decorator, expected):
    # ensure we are working in `tmp_path`
    os.chdir(tmp_path)
    assert Path.cwd() == tmp_path

    # create the config file
    path = "foo.toml"
    file = tmp_path / path
    with file.open("w") as fd:
        fd.write(
            tomli_w.dumps(
                {
                    "foo": "bar",
                    "my-app": {"baz": "quux"},
                }
            )
        )

    # define the command
    @click.command
    @_cli.additional_configs_option
    @pass_config_decorator
    def test(config, **kwargs):
        # pop list of config paths as they are not of interest here
        config.pop("configs")

        # the config is as expected
        assert config == expected

    runner.invoke(test, ["--additional-config", path], standalone_mode=False)


@pytest.mark.parametrize(
    ("params", "input", "expected_present", "expected_value"),
    (
        (None, None, False, None),
        (["--password"], "foo\nfoo", True, "foo"),
        (["--password", "foo"], None, True, "foo"),
    ),
)
def test_password_option(runner, params, input, expected_present, expected_value):
    @click.command
    @_cli.password_option
    @_cli.pass_config
    def test(config, **kwargs):
        assert "password" in kwargs

        present = "password" in config
        assert present == expected_present

        if present:
            for password in (kwargs["password"], config["password"]):
                assert type(password) is _auth.Password
                assert str(password) == password.redact
                assert password.value == expected_value
        else:
            assert kwargs["password"] is None

    runner.invoke(test, params, input=input, standalone_mode=False)
