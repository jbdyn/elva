import os
from pathlib import Path

import tomli_w
from pytest import mark, raises

import elva.cli as _cli
import elva.files as _files
import elva.store as _store

# alias
parametrize = mark.parametrize


def test_empty_data_file_path():
    """
    Empty paths and directories are not allowed.
    """
    with raises(ValueError):
        _files.get_data_file_path(Path(""))


@parametrize(
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
    data_file_path = _files.get_data_file_path(Path(path))

    # the file name and the resolved path are as expected
    assert data_file_path.name == expected
    assert str(data_file_path) == str(tmp_path / expected)


@parametrize(
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
    stem = _files.derive_stem(path)
    assert stem.name == expected


@parametrize(
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
    render_file_path = _files.get_render_file_path(path)
    assert render_file_path.name == expected


@parametrize(
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
    log_file_path = _files.get_log_file_path(path)
    assert log_file_path.name == expected


@parametrize(
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
    data_file_path = _files.get_data_file_path(tmp_path / "test")

    # write data to file
    if isinstance(metadata, str):
        with data_file_path.open(mode="w") as file:
            file.write(metadata)
    elif isinstance(metadata, dict):
        _store.set_metadata(data_file_path, "config", metadata)

    # the return dict is populated as expected
    res = _cli.basis.read_data_file(data_file_path)
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


@parametrize(
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
    checked_paths, config = _cli.basis.read_config_files(paths)

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
