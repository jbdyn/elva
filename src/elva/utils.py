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


def get_params_from_file(file):
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

    params = dict(file=file, render=render, log=log)

    # update ctx with metadata
    if file.exists():
        metadata = SQLiteStore.get_metadata(file)
        params.update(metadata)

    return params


def get_params_from_configs(configs):
    params = dict()

    # last listed config file has lowest priority
    for config in reversed(configs):
        if not config.exists():
            continue

        with open(config, "rb") as f:
            data = tomllib.load(f)

        params.update(data)

    return params


def gather_context_information(ctx, file=None, app=None):
    c = ctx.obj

    params = dict()

    # params defined in configs and data files
    configs = c["configs"]
    if configs is not None:
        config_params = get_params_from_configs(configs)

        params.update(config_params)

    apps = ["default"]
    if app is not None:
        apps.append(app)

    for app in apps:
        try:
            app_params = params["app"][app]
            params.update(app_params)
        except KeyError:
            pass

    params.pop("app", None)

    if file is not None:
        file_params = get_params_from_file(file)

        params.update(file_params)

    # defaults
    for key, default in [
        ("identifier", str(uuid.uuid4())),
        ("messages", "yjs"),
    ]:
        if params.get(key) is None:
            params[key] = default

    # merge with CLI
    for k, v in params.items():
        update_none_only(c, k, v)
