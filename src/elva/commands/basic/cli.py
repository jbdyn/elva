from shlex import split
from subprocess import PIPE, Popen

from click import ClickException, Context, Parameter, ParamType, command, option
from click import password_option as secret

from elva.auth import Password
from elva.cli import context, unset

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


def run(command: str) -> Password:
    """
    Run the command returning the secret for authentication on stdin.

    Arguments:
        command: the command to run.

    Returns:
        the password with the stripped stdout content as value.
    """
    args = split(command)

    process = Popen(args, text=True, stdout=PIPE, stderr=PIPE)

    stdout, stderr = process.communicate()

    if stderr:
        raise ClickException(stderr)

    return Password(stdout.rstrip("\r\n"))


class SecretParamType(ParamType):
    """
    CLI parameter type for parsing secrets.
    """

    name = "secret"

    def convert(
        self,
        value: Password | str | None,
        param: Parameter,
        ctx: Context,
    ) -> Password:
        """
        Convert the parsed CLI value to a secret.

        Arguments:
            value: the value given via CLI or API.
            param: the parameter instance.
            ctx: the context of the current invokation.

        Returns:
            the value in the `Password` wrapper or `None`.
        """
        if isinstance(value, Password) or value is None:
            return value

        return Password(value)


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
    "-c",
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
        c["secret"] = run(c["command"])
