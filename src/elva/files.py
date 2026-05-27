"""
Module providing the main command line interface functionality.
"""

from pathlib import Path
from sqlite3 import Connection, Cursor, DatabaseError, connect
from tomllib import loads
from types import TracebackType
from typing import Self, Sequence

from tomli_w import dumps

from elva.config import Config, clean, convert
from elva.core import (
    FILE_SUFFIX,
    LOG_SUFFIX,
)


def get_data_file_path(path: Path) -> Path:
    """
    Ensure a correct and resolved data file path.

    Arguments:
        path: the path to the data file.

    Returns:
        the correct and resolved data file path.
    """
    if path.is_dir():
        raise ValueError(f"{path} is a directory")

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


class Metadata:
    """
    Handle ELVA metadata in an SQLite database.
    """

    path: Path
    """
    The path to the SQLite database.
    """

    db: Connection
    """
    The SQLite database connection instance.
    """

    def __init__(self, path: str | Path, fail: bool = False) -> None:
        """
        Arguments:
            path: the path to the SQLite database.
            fail: raise an error when the path does not exist.

        Raises:
            FileNotFoundError: if `fail` is `True` and `path` does not exist.
        """
        # ensure `Path` object
        path = Path(path)

        # check for existence
        if fail and not path.exists():
            raise FileNotFoundError(f"{path}: no such file")

        # attributes
        self.path = path
        self.db = connect(path)

        # ensure `metadata` table
        self._ensure()

    def __del__(self) -> None:
        """
        Destructor.

        Closes the database connection if present.
        """
        if hasattr(self, "db"):
            self.db.close()

    def __enter__(self) -> Self:
        """
        Enter a context.

        Returns:
            itself.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """
        Exit a context.

        Deletes itself.

        Arguments:
            exc_type: the type of the occured exception.
            exc_val: the occured exception.
            exc_tb: the occured exception's traceback.
        """
        del self

    def _execute(self, statement: str, parameters: dict | Sequence = tuple()) -> Cursor:
        """
        Execute an SQL statement with given parameters.

        Arguments:
            statement: the SQL statement.
            parameters: the parameters to use in the SQL statement.

        Returns:
            the current cursor.
        """
        return self.db.cursor().execute(statement, parameters)

    def _commit(self) -> None:
        """
        Commit an SQL change.
        """
        self.db.commit()

    def _ensure(self) -> None:
        """
        Ensure the `metadata` table.
        """
        self._execute(
            "CREATE TABLE IF NOT EXISTS metadata (key PRIMARY KEY, value BLOB)",
        )
        self._commit()

    def get(self, key: str) -> bytes | None:
        """
        Get the metadata value for a given key.

        Arguments:
            key: the metadata key.

        Returns:
            the value corresponding to the given key
            or `None` if no value exists.
        """
        res = self._execute(
            "SELECT value FROM metadata WHERE key = ?", [key]
        ).fetchone()

        return res[0] if res else None

    def set(self, key: str, value: bytes) -> None:
        """
        Set the metadata value for a given key.

        Arguments:
            key: the metadata key.
            value: the metadata value.
        """
        try:
            # try to insert this key
            self._execute("INSERT INTO metadata VALUES (?, ?)", [key, value])
        except DatabaseError:
            # key is already present, update it
            self._execute("UPDATE metadata SET value = ? WHERE key = ?", [value, key])

        # commit the changes
        self._commit()

    def get_config(self) -> Config:
        """
        Get the value for the `config` metadata key.

        Returns:
            the saved config.
        """
        res = self.get("config")
        config = loads(res.decode()) if res is not None else {}

        return Config(config)

    def set_config(self, config: Config, *, replace: bool = False) -> None:
        """
        Update the config.

        Arguments:
            config: the config to insert.
            replace: if `True`, save the config as given, else deepmerge.
        """
        new = config if replace else self.get_config().merge(config)

        clean(new)

        value = dumps(convert(new)).encode()

        self.set("config", value)


class Data(Metadata):
    """
    Handle ELVA metadata and Y-updates in an SQLite database.
    """

    path: Path
    """
    The path to the SQLite database.
    """

    db: Connection
    """
    The SQLite database connection instance.
    """

    def _ensure(self) -> None:
        """
        Ensure the `metadata` and `yupdates` table.
        """
        # ensure `metadata` table
        super()._ensure()

        # ensure `yupdates` table
        self._execute("CREATE TABLE IF NOT EXISTS yupdates (yupdate BLOB)")
        self._commit()

    def get_updates(self) -> list[bytes]:
        """
        Get stored Y-updates.

        Returns:
            a list of Y-updates.
        """
        res = self._execute("SELECT yupdate FROM yupdates").fetchall()

        return [update for update, *_ in res]
