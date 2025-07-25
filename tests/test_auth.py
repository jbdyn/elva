import pytest

from elva.auth import Auth, DummyAuth

# use AnyIO pytest plugin
pytestmark = pytest.mark.anyio


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
