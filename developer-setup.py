"""
Setup for git hooks.
"""

import sys
from pathlib import Path


def get_project_path() -> Path:
    """
    Get the absolute project path.

    Thereby, this script can be called from any location in
    the filesystem.

    Returns:
        the absolute ELVA project path.
    """
    script = sys.argv[0]
    return Path(script).absolute().parent


def create_hook_symlinks(project: Path):
    """
    Create symlinked hooks in the local .git directory.

    Arguments:
        project: the absolute ELVA project path
    """
    git_hooks = project / "git/hooks/"
    dotgit_hooks = project / ".git/hooks/"

    for target in git_hooks.iterdir():
        link = dotgit_hooks / target.name
        target = target.relative_to(dotgit_hooks, walk_up=True)

        if not link.exists():
            link.symlink_to(target)

        print(f"✓ {link}")


if __name__ == "__main__":
    project = get_project_path()
    create_hook_symlinks(project)
