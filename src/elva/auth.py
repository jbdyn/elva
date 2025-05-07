"""
Module providing authentication utilities for [`server`][elva.apps.server] app module.
"""

import logging
from base64 import b64decode, b64encode
from http import HTTPStatus

import ldap3
from ldap3.core.exceptions import LDAPException

from elva.log import LOGGER_NAME

AUTH_SCHEME = [
    "Basic",
    "Digest",
    "Negotiate",
]
"""
Valid autentication schemes in `Authorization` HTTP request header.
"""


def basic_authorization_header(username: str, password: str) -> dict[str, str]:
    """
    Compose the Base64 encoded `Authorization` header for `Basic` authentication.

    Arguments:
        username: user name used for authentication.
        password: password used for authentication.

    Returns:
        dictionary holding the Base64 encoded `Authorization` header contents as value.
    """
    bvalue = f"{username}:{password}".encode()
    b64bvalue = b64encode(bvalue).decode()

    return {"Authorization": f"Basic {b64bvalue}"}


def process_authorization_header(request_headers: dict) -> tuple[str, str]:
    """
    Decompose Base64 encoded `Authorization` header into scheme and credentials.

    Arguments:
        request_headers: dictionary of HTTP request headers.

    Returns:
        tuple holding the scheme and the (still Base64 encoded) credentials.
    """
    auth_header = request_headers["Authorization"]
    scheme, credentials = auth_header.split(" ", maxsplit=1)
    if scheme not in AUTH_SCHEME:
        raise ValueError("invalid scheme in Authorization header")
    return scheme, credentials


def process_basic_auth_credentials(credentials: str) -> tuple[str, str]:
    """
    Decode Base64 encoded `Basic` authorization header payload.

    Arguments:
        credentials: Base64 encoded credentials from the `Authorization` HTTP request header.

    Returns:
        tuple holding decoded user name and password.
    """
    bb64cred = credentials.encode()
    bcred = b64decode(bb64cred)
    cred = bcred.decode()
    username, password = cred.split(":", maxsplit=1)
    return username, password


def abort_basic_auth(
    realm: str,
    body: None | str = None,
    status: HTTPStatus = HTTPStatus.UNAUTHORIZED,
) -> tuple[HTTPStatus, dict[str, str], None | bytes]:
    """
    Compose `Basic Authentication` abort information.

    Arguments:
        realm: `Basic Authentication` realm.
        body: message body to send.
        status: HTTP status for this abort.

    Returns:
        tuple holding the HTTP status, the dictionary with the `WWW-Authenticate` header information for `Basic Authentication` and the UTF-8 encoded message body if given.
    """
    headers = {"WWW-Authenticate": f"Basic realm={realm}"}
    if body:
        body = body.encode()
    return status, headers, body


class BasicAuth:
    """
    Base class for `Basic Authentication`.

    This class is intended to be used in the [`server`][elva.apps.server] app module.
    """

    def __new__(cls, *args, **kwargs):
        self = super().__new__(cls)
        self.log = logging.getLogger(
            f"{LOGGER_NAME.get(__name__)}.{self.__class__.__name__}"
        )
        return self

    def __init__(self, realm: str):
        """
        Arguments:
            realm: realm of the `Basic Authentication`.
        """
        self.realm = realm

    def authenticate(
        self, path: str, request_headers: dict
    ) -> None | tuple[HTTPStatus, dict[str, str], None | bytes]:
        """
        Wrapper around [`verify`][elva.auth.BasicAuth.verify] with processing and logging.

        Arguments:
            path: the path used in the HTTP request.
            request_headers: the HTTP request headers.

        Returns:
            `None` if [`verify`][elva.auth.BasicAuth.verify] returns `True`, else it returns the request abort information as specified in [`abort_basic_auth`][elva.auth.abort_basic_auth].
        """
        try:
            scheme, credentials = process_authorization_header(request_headers)
        except KeyError:
            return self._log_and_abort("missing Authorization header")
        except ValueError:
            return self._log_and_abort("malformed Authorization header")

        match scheme:
            case "Basic":
                username, password = process_basic_auth_credentials(credentials)
            case _:
                return self._log_and_abort("unsupported Authorization scheme")

        if not self.verify(username, password):
            return self._log_and_abort("invalid credentials")

    def _abort(self, body=None, status=HTTPStatus.UNAUTHORIZED):
        return abort_basic_auth(self.realm, body=body, status=status)

    def _log_and_abort(self, msg):
        self.log.debug(msg)
        return self._abort(msg)

    def verify(self, username: str, password: str) -> bool:
        """
        Decides whether the given credentials are valid or not.

        This is defined as a no-op and is intended to implemented in inheriting subclasses.

        Arguments:
            username: user name provided in the HTTP request headers.
            password: password provided in the HTTP request headers.

        Returns:
            `True` if credentials are valid, `False` if they are not.
        """
        ...


class DummyAuth(BasicAuth):
    """
    Dummy `Basic Authentication` class where password equals user name.

    Danger:
        This class is intended for testing only. DO NOT USE IN PRODUCTION!
    """

    def verify(self, username, password):
        return username == password


class LDAPBasicAuth(BasicAuth):
    """
    `Basic Authentication` using LDAP self-bind.
    """

    def __init__(self, realm: str, server: str, base: str):
        """
        Arguments:
            realm: realm of the `Basic Authentication`.
            server: address of the LDAP server.
            base: base for lookup on the LDAP server.
        """
        super().__init__(realm)
        self.server = ldap3.Server(server, use_ssl=True)
        self.base = base
        self.log.info(f"server: {self.server.name}, base: {base}")

    def verify(self, username: str, password: str) -> bool:
        """
        Perform a self-bind connection to the given LDAP server.

        Arguments:
            username: user name to use for the LDAP self-bind connection.
            password: password to use for the LDAP self-bind connection.

        Returns:
            `True` if the LDAP self-bind connection could be established, i.e. was successful, `False` if no successful connection could be established.
        """
        user = f"uid={username},{self.base}"
        try:
            self.log.debug("try LDAP connection")
            with ldap3.Connection(
                self.server,
                user=user,
                password=password,
            ) as conn:
                if conn.result["description"] == "success":
                    self.log.debug(f"successful self-bind with {user}")
                    return True
                else:
                    self.log.debug(f"self-bind with {user} not successful")
                    return False

        except LDAPException:
            self.log.debug(f"unable to connect with {user}")
            return False
