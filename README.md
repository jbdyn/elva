# ELVA

A suite of apps enabling real-time collaboration locally, with CRDTs at its heart ❤️.

ELVA (_Norwegian: the river_, _German abbreviation "Evaluation von Lösungen für verteilte Arbeit"_) is a suite of apps which allow the user to share projects in real-time with other peers in a network.


# Installation

In the project's root directory, create a new virtual Python environment (named `env` here) with

```shell
python -m venv --upgrade-deps env
```

and call

```shell
pip install .
```

to install the `elva` package along with its dependencies.

If you need the developer dependencies as well, use

```shell
pip install .[dev]
```

and you will be able to build the documentation and the Python wheel yourself.


## Packaging and Publishing

Currently, `setuptools` is used for building and packaging.
To be able to build your own Python wheel, run

```shell
python -m build
```

in the project's root directory after installing the development dependencies.

Upload the wheel to PyPI with `twine` like

```shell
twine upload [-r testpypi] dist/*
```

by specifing the remote repository with `-r <repository>`, "Test PyPI" in this particular case.

## Licensing

The ELVA source code is dsitributed under the GNU Affero General Public License (AGPL) 3.0, *except* for the `logo/` directory and its contents, which are licensed under the [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)](https://creativecommons.org/licenses/by-nc-sa/4.0/).
