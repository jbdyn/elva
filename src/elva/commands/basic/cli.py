from click import Context, Parameter, ParamType, command, option
from click import password_option as secret

from elva.auth import Password
from elva.cli import context


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
@context
def cli():
    """
    Configure Basic Authentication.
    """
    return
