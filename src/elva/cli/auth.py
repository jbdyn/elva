from shlex import split
from subprocess import PIPE, Popen

from click import ClickException, Context, Parameter, ParamType

from elva.auth import Password


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


def ask(command: str) -> Password:
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
