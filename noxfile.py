import logging
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Generator, Iterable

import nox

##
#
# CONSTANTS
#

BACKEND = "uv"
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
WEBSOCKETS = ("14.0.0", "14.1.0", "14.2.0", "15.0.0")
TEXTUAL = ("2.0", "3.0", "4.0", "5.0.0", "5.1.0", "5.2.0", "5.3.0")

# default `pytest` command options
PYTEST_OPTS = ("-x", "--strict-config")


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


def get_uv_opts_and_env(session: nox.Session) -> tuple[tuple, dict]:
    """
    Get the the options and environment configuration for `uv`.

    Arguments:
        session: the nox session object.

    Returns:
        a tuple of options tuple and environment dictionary.
    """
    opt = (f"--python={session.virtualenv.location}",)
    env = dict(
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )

    return opt, env


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


def setup_logging(session: nox.Session):
    """
    Get and and set the log file for a session.

    Arguments:
        session: the nox session object.
    """
    NAME = Path(session._runner.envdir).stem
    LOG_FILE = LOG_PATH / f"{NAME}.log"
    set_log_file(LOG_FILE)


def setup_venv(session: nox.Session, websockets: str, textual: str):
    """
    Install Python packages with desired versions and from `pyproject.toml`.

    Arguments:
        session: the nox session object.
        websockets: the websockets version.
        textual: the textual version.
    """
    UV_OPTS, UV_ENV = get_uv_opts_and_env(session)

    # overwrite with specific versions;
    # for compatible release specifier spec,
    # see https://packaging.python.org/en/latest/specifications/version-specifiers/#compatible-release;
    # set the environment for making `uv` in the temporary `nox` venv
    session.run(
        "uv",
        "add",
        f"websockets~={websockets}",
        f"textual~={textual}",
        *UV_OPTS,
        **UV_ENV,
        silent=True,
    )

    # sync all dependencies
    session.run(
        "uv",
        "sync",
        "--all-extras",
        *UV_OPTS,
        **UV_ENV,
        silent=True,
    )


def setup(session: nox.Session, websockets: str, textual: str):
    """
    Setup logging and the virtual environment.

    Arguments:
        session: the nox session object.
        websockets: the websockets version.
        textual: the textual version.
    """
    setup_logging(session)
    setup_venv(session, websockets, textual)


def restore_venv_spec(session: nox.Session):
    """
    Restore altered package management files.

    Arguments:
        session: the nox session object.
    """
    session.run(
        "git",
        "restore",
        "pyproject.toml",
        "uv.lock",
        silent=True,
        external=True,
    )


##
#
# SESSIONS
#


@nox.session(
    venv_backend=BACKEND,
)
@nox.parametrize(
    # exclude newest since this environment configuration is covered by the `coverage` session below
    ("python", "websockets", "textual"),
    parameters_excluding_last(PYTHON, WEBSOCKETS, TEXTUAL),
)
def tests(session: nox.Session, websockets: str, textual: str):
    setup(session, websockets, textual)

    # run pytest session
    session.run(
        "pytest",
        *PYTEST_OPTS,
        silent=True,
    )

    restore_venv_spec(session)

    # idempotent
    session.notify("coverage")


# latest available environment
# with code coverage report
@nox.session(
    venv_backend=BACKEND,
)
@nox.parametrize(
    ("python", "websockets", "textual"), ((PYTHON[-1], WEBSOCKETS[-1], TEXTUAL[-1]),)
)
def coverage(session: nox.Session, websockets: str, textual: str):
    setup(session, websockets, textual)

    # run coverage session
    session.run(
        "coverage",
        "run",
        "-m",
        "pytest",
        *PYTEST_OPTS,
        silent=True,
    )

    # generate reports
    session.run("coverage", "combine", silent=True)
    session.run("coverage", "report", silent=True)
    session.run("coverage", "html", silent=True)

    restore_venv_spec(session)


# latest available environment
# with code coverage report
@nox.session(
    venv_backend=BACKEND,
    default=False,
)
@nox.parametrize(
    "python",
    PYTHON[-1],
)
def upgraded(session: nox.Session):
    setup_logging(session)

    UV_OPTS, UV_ENV = get_uv_opts_and_env(session)

    # make sure to install the latest possible versions since `uv` won't update otherwise
    session.run(
        "uv",
        "sync",
        "--reinstall",
        "--all-extras",
        "--upgrade",
        *UV_OPTS,
        **UV_ENV,
        silent=True,
    )

    # run coverage session
    session.run(
        "pytest",
        *PYTEST_OPTS,
        silent=True,
    )

    restore_venv_spec(session)
