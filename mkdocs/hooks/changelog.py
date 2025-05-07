from pathlib import Path

from mkdocs.config.base import Config
from mkdocs.structure.files import File, Files


def on_files(files: Files, config: Config) -> Files | None:
    """
    Hook adding the changelog to the file collection.

    Arguments:
        files: global files collection
        config: global configuration object

    Returns:
        global files collection
    """
    # find the changelog relative to the given config file path
    project_path = Path(config["config_file_path"]).parent
    abs_src_path = (project_path / "CHANGELOG.md").absolute()

    # must be the same as in the `nav` section of the given `mkdocs.yml`
    src_uri = "changelog.md"

    # generate a virtual changelog file with the contents under `abs_src_path`
    # and pretending to be at `src_uri`
    changelog = File.generated(config, src_uri, abs_src_path=abs_src_path)

    # append the generated changelog file to the `mkdocs` file collection
    files.append(changelog)

    return files
