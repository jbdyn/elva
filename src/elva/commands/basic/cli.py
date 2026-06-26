from click import command, option
from click import password_option as secret

from elva.cli import SecretParamType, ask, context, unset

TRANSLATE = {
    "user": "user",
    "u": "user",
    "secret": "secret",
    "s": "secret",
    "command": "command",
    "c": "command",
}
"""
Table for translation from flag to parameter names.
"""


@command(name="basic")
@option(
    "--user",
    "-u",
    "user",
    help="Username for authentication.",
)
@secret(
    "--secret",
    "-s",
    "secret",
    help="Secret for authentication.",
    metavar="[SECRET]",
    prompt_required=False,
    type=SecretParamType(),
)
@option(
    "--command",
    "-x",
    help="The command returning the secret on stdin.",
)
@unset(TRANSLATE)
@context
def cli(config: dict):
    """
    Configure Basic Authentication.
    \f

    Arguments:
        config: the merged `basic` config section.
    """
    # alias
    c = config

    unset = set(c.get("unset", []))

    if (
        c.get("command", None)
        and not c.get("secret", None)
        and "secret" not in unset
        and "command" not in unset
    ):
        c["secret"] = ask(c["command"])
