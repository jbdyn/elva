import pytest

from elva.auth import Auth, DummyAuth, Password

# use AnyIO pytest plugin
pytestmark = pytest.mark.anyio


def test_password():
    """
    The `Password` container redacts a password on string conversion
    and in its string representiation.
    """
    # setup
    secret = "s3cR3t!"
    password = Password(secret)

    # calls `__str__` method
    assert str(password) != secret
    assert str(password) == password.redact

    # calls `__repr__` method
    assert repr(password) != secret
    assert repr(password) == password.redact

    # calls `__repr__` method implicitely
    assert f"{password}" != secret
    assert f"{password}" == password.redact

    # we need to request the value explicitely
    assert password.value == secret

    # we can change the password value via attribute
    new_secret = "1234"  # never ever do this
    password.value = new_secret
    assert password.value == new_secret

    # we can change the redact string
    # via the `redact` attribute
    new_redact = "∙∙∙∙∙"  # Bullet Operator U+2219, BMP
    password.redact = new_redact
    str(password) == new_redact

    # on initialization
    new_password = Password("foo", redact=new_redact)
    str(new_password) == new_redact


def test_auth_class():
    """Unspecified credential checking logic results in an error."""
    auth = Auth()

    assert hasattr(auth, "log")

    username = "some-user"
    password = "secret"

    with pytest.raises(NotImplementedError):
        auth.check(username, password)


async def test_async_auth_class():
    """Defining `check` as coroutine should work as expected"""
    PASSWORD = "1234"

    class TestAuth(Auth):
        async def check(self, username, password):
            return password == PASSWORD

    auth = TestAuth()

    assert await auth.check("anybody", PASSWORD)
    assert not await auth.check("nobody", "abcd")


def test_dummy_auth_class():
    """Dummy authentication works as expected."""
    auth = DummyAuth()

    username = "Jane"
    password = "nobody_knows"

    assert not auth.check(username, password)

    username = "Jon"
    password = "Jon"
    assert auth.check(username, password)


# TODO: add tests for LDAPAuth, which requires a reliable test server
