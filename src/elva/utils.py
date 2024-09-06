import uuid
from pathlib import Path

import tomllib

from elva.store import SQLiteStore

FILE_SUFFIX = ".y"
LOG_SUFFIX = ".log"


def update_none_only(d, key, value):
    if d.get(key) is None:
        # `key` does not exist or its value is `None`
        d[key] = value


def update_context_with_file(ctx, file):
    c = ctx.obj

    # resolve to absolute, direct path
    file = file.resolve()

    # update data and render paths
    if FILE_SUFFIX not in file.suffixes:
        # given path is actually the rendered output
        render = file

        # set data file path accordingly
        file = Path(str(file) + FILE_SUFFIX)
    else:
        # file is taken as is, even if ".y" is not last suffix
        # e.g. in `foo.bar.y.bak`
        #
        # get the render path by stripping all suffixes after ".y"
        suffixes = "".join(file.suffixes)
        basename = file.name.removesuffix(suffixes)
        suffixes = suffixes.split(FILE_SUFFIX, maxsplit=1)[0]
        render = file.with_name(basename + suffixes)

    # update paths
    log = Path(str(render) + LOG_SUFFIX)
    for key, value in [
        ("file", file),
        ("render", render),
        ("log", log),
    ]:
        update_none_only(c, key, value)

    # update ctx with metadata
    if file.exists():
        metadata = SQLiteStore.get_metadata(file)
        for key, value in metadata.items():
            update_none_only(c, key, value)


def update_context_with_config(ctx, config):
    if not config.exists():
        return

    c = ctx.obj

    with open(config, "rb") as f:
        data = tomllib.load(f)

    for key, value in data.items():
        update_none_only(c, key, value)


def gather_context_information(ctx, file=None):
    c = ctx.obj
    config = c["config"]

    if file is not None:
        update_context_with_file(ctx, file)

    update_none_only(c, "identifier", str(uuid.uuid4()))

    if config is not None:
        update_context_with_config(ctx, config)
