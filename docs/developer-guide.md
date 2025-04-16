# Developer Guide

## Project Setup

With [`git`](https://git-scm.com/) fork the project on GitHub if you want to contribute and clone this fork locally with 

```sh
git clone <url-of-your-forked-elva-project>
```

or directly clone the project into your desired location with

```sh
git clone https://github.com/innocampus/elva <location>
```

Then run

```sh
uv pip install .[dev]
```

or an equivalent package manager command to also install the development dependencies.

If you want to work on the logo, you will need to install the dependencies from the `logo` group:

```sh
uv pip install .[logo]
```


## Orientation

- We use [`git-cliff`](https://git-cliff.org/) in the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format for changelog drafting and [`mkdocs`](https://www.mkdocs.org/) for documentation.
- This project ships both: The end-user facing code in `src/elva/apps` and the developer-facing library in `src/elva`.
- We follow the [GitHub flow](https://docs.github.com/de/get-started/using-github/github-flow) for collaboration.
- The naming scheme is `MAJOR.MINOR` and depends on git tags.
- The core idea is to combine the libraries [`pycrdt`](https://github.com/jupyter-server/pycrdt), [`textual`](https://github.com/Textualize/textual) and networking libraries like [`websockets`](https://github.com/python-websockets/websockets) to make useful apps for real-time collaboration.


## Version Change Workflow

1. Merge pull requests via GitHub's web UI.
2. Create a changelog draft with [`git-cliff`](https://git-cliff.org/):

    ```sh
    git cliff --unreleased --tag <bumped-tag> --prepend CHANGELOG.md
    ```

    This adds only unreleased, i.e. untagged, commit messages with the manually increased `<bumped-tag>`.

3. Edit the commit messages in `CHANGELOG.md` by hand.
4. On branch `main`, commit and tag this new commit with `<bumped-tag>` (and perhaps an appropriate tag message as the release notes).
5. Push to `origin/main`.
6. Build the package and upload it to PyPI.
7. Create a new release on GitHub.
8. Build and update the documentation website.
