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

    # overwrite with specific versions;
    # for compatible release specifier spec,
    # see https://packaging.python.org/en/latest/specifications/version-specifiers/#compatible-release;
    # set the environment for making `uv` in the temporary `nox` venv
    session.run(
        "uv",
        "add",
        f"websockets~={websockets}",
        f"textual~={textual}",
        f"--python={session.virtualenv.location}",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )

    # sync all dependencies
    session.run(
        "uv",
        "sync",
        "--all-extras",
        f"--python={session.virtualenv.location}",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )

    # run pytest session
    session.run(
        "pytest",
        "-x",
        "--strict-config",
        silent=True,
    )

    # restore altered package management files
    session.run(
        "git",
        "restore",
        "pyproject.toml",
        "uv.lock",
        silent=True,
        external=True,
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

    # make sure to install the latest possible versions since `uv` won't update otherwise
    session.run_install(
        "uv",
        "sync",
        "--reinstall",
        "--all-extras",
        "--upgrade",
        f"--python={session.virtualenv.location}",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )

    # run coverage session
    session.run(
        "coverage",
        "run",
        "-m",
        "pytest",
        "-x",
        "--strict-config",
        silent=True,
    )

    # generate reports
    session.run("coverage", "combine", silent=True)
    session.run("coverage", "report", silent=True)
    session.run("coverage", "html", silent=True)

    # restore altered package management files
    session.run(
        "git",
        "restore",
        "pyproject.toml",
        "uv.lock",
        silent=True,
        external=True,
    )
