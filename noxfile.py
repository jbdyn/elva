import logging
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Generator, Iterable

import nox

##
#
# HELPERS
#


def parameters_excluding_last(
    *params: Iterable[Iterable[str]],
) -> Generator[nox.param, None, None]:
    """
    Generate the products of parameters except for the last one.

    Arguments:
        params: a collection of iterables with `nox`-session parameters.

    Yields:
        `nox` parameter
    """
    latest = tuple(param[-1] for param in params)

    for prod in product(*params):
        if prod != latest:
            yield nox.param(*prod)


def set_log_file(path: str | Path):
    """
    Adds a filepath handler to the root logger.

    Arguments:
        path: log file path.
    """
    SESSION_HANDLER = "nox-session"
    logger = logging.getLogger()

    for handler in logger.handlers:
        if handler.name == SESSION_HANDLER:
            logger.removeHandler(handler)

    handler = logging.FileHandler(path)
    handler.name = SESSION_HANDLER
    logger.addHandler(handler)


##
#
# CONSTANTS
#

BACKEND = "uv|virtualenv"
EDITABLE = ("-e", ".[dev,logo]")
TIMESTAMP = datetime.now().strftime("%Y-%m-%dT%H-%M")
LOG_PATH = Path(__file__).parent / "logs" / "nox" / TIMESTAMP

# ensure existence of log file directory
LOG_PATH.mkdir(parents=True, exist_ok=True)

PROJECT = nox.project.load_toml("pyproject.toml")

# from classifiers and not `requires-python` entry;
# see https://nox.thea.codes/en/stable/config.html#nox.project.python_versions
PYTHON = nox.project.python_versions(PROJECT)

# versions to test by compatible release;
# check for every version adding new functionality or breaking the API
WEBSOCKETS = ("13.0.0", "13.1.0", "14.0.0", "14.1.0", "14.2.0", "15.0.0")
TEXTUAL = ("1.0.0", "2.0.0", "2.1.0", "3.0.0", "3.1.0", "3.2.0")


##
#
# SESSIONS
#


# backwards compatibility
@nox.session(
    venv_backend=BACKEND,
)
@nox.parametrize(
    # exclude newest since this environment configuration is covered by the `coverage` session below
    ("python", "websockets", "textual"),
    parameters_excluding_last(PYTHON, WEBSOCKETS, TEXTUAL),
)
def tests(session, websockets, textual):
    NAME = Path(session._runner.envdir).stem
    LOG_FILE = LOG_PATH / f"{NAME}.log"
    set_log_file(LOG_FILE)

    # idempotent
    session.notify("coverage")

    # install from `pyproject.toml`
    session.install(*EDITABLE)

    # overwrite with specific versions;
    # for compatible release specifier spec,
    # see https://packaging.python.org/en/latest/specifications/version-specifiers/#compatible-release
    session.install(
        f"websockets~={websockets}",
        f"textual~={textual}",
    )

    # TODO: run across all tests
    session.run(
        "pytest",
        "tests/test_component.py",
        silent=True,
    )


# latest available environment
# with code coverage report
@nox.session(
    venv_backend=BACKEND,
)
@nox.parametrize(
    "python",
    PYTHON[-1],
)
def coverage(session):
    NAME = Path(session._runner.envdir).stem
    LOG_FILE = LOG_PATH / f"{NAME}.log"
    set_log_file(LOG_FILE)

    # install from `pyproject.toml`;
    # make sure to install the latest possible versions since `uv` won't update otherwise
    if session.venv_backend == "uv":
        session.install("--exact", "--reinstall", *EDITABLE)
    else:
        session.install(*EDITABLE)

    # TODO: run across all tests
    session.run(
        "coverage",
        "run",
        "-m",
        "pytest",
        "tests/test_component.py",
        silent=True,
    )

    # generate reports
    session.run("coverage", "combine", silent=True)
    session.run("coverage", "report", silent=True)
    session.run("coverage", "html", silent=True)
