"""
Module providing authentication utilities.
"""

import logging
from base64 import b64encode
from enum import IntEnum

import ldap3
from ldap3.core.exceptions import LDAPException
from ldap3.utils.log import (
    BASIC,
    ERROR,
    EXTENDED,
    NETWORK,
    OFF,
    PROTOCOL,
    set_library_log_detail_level,
)

from elva.log import LOGGER_NAME


class Password:
    """
    A container which stores a password behind an attribute and redacts its value.

    The purpose of this class is two-fold:
    A password's value needs to be requested explicitely and
    accidential leaking via printing and logging is prevented.
    """

    value: str
    """The actual password."""

    redact: str
    """The string to mask the password."""

    def __init__(self, value: str, redact: str = "REDACTED"):
        """
        Arguments:
            value: the actual password.
            redact: the string to mask the password.
        """
        self.value = value
        self.redact = redact

    def __str__(self) -> str:
        """
        The string conversion of this object.

        Returns:
            the value of the [`redact`][elva.auth.Password.redact] attribute.
        """
        return self.redact

    def __repr__(self) -> str:
        """
        The string representation of this object.

        Returns:
            the value of the [`redact`][elva.auth.Password.redact] attribute.
        """
        return self.redact


class LDAP3LogLevel(IntEnum):
    """
    The logging level specified by the LDAP3 Python library as enumeration.

    Intended as arguments for `ldap3.utils.log.set_library_log_detail_level`.
    See [https://ldap3.readthedocs.io/en/latest/logging.html]() for details.
    """

    OFF = OFF
    """Nothing is logged."""

    ERROR = ERROR
    """Only exceptions are logged."""

    BASIC = BASIC
    """Library activity is logged, only operation result is shownn"""

    PROTOCOL = PROTOCOL
    """LDAPv3 operations are logged, sent requests and received responses are shown."""

    NETWORK = NETWORK
    """Socket activity is logged."""

    EXTENDED = EXTENDED
    """LDAP messages are decoded and properly printed."""


def basic_authorization_header(
    username: str, password: str, charset: str = "utf-8"
) -> dict[str, str]:
    """
    Compose the Base64 encoded `Authorization` header for `Basic` authentication
    according to [*The 'Basic' Authentication Scheme*](https://datatracker.ietf.org/doc/html/rfc7617.html#section-2) in [**RFC 7617**](https://datatracker.ietf.org/doc/html/rfc7617.html).

    Arguments:
        username: user name used for authentication.
        password: password used for authentication.
        charset: the character encoding the server expects the basic credentials to be encoded in.

    Returns:
        dictionary holding the Base64 encoded `Authorization` header contents.
    """
    # in RFC 7617, user IDs containing a colon ':' are invalid
    if ":" in username:
        raise ValueError(f"given username '{username}' must not contain a colon ':'")

    # scheme given by RFC 7617
    user_pass = f"{username}:{password}"

    # we need an octet sequence for Base64 encoding;
    # the charset is either set to UTF-8 due to its global adoption or
    # given by the server in the WWW-Authenticate header
    octet_sequence = user_pass.encode(charset)

    # encode the octet sequence in Base64 and decode it for converting
    # the result from bytes to string;
    # the `ascii` encoding is just informational here as Base64 encoding
    # only produces a sequence of ASCII characters
    basic_credentials = b64encode(octet_sequence).decode("ascii")

    # scheme given by RFC 7617
    return {"Authorization": f"Basic {basic_credentials}"}


class Auth:
    """
    Base class for authentications.

    This class is intended to be used in the [`server`][elva.apps.server] app module.
    """

    def __new__(cls, *args, **kwargs):
        """
        Construct a new class.
        """
        self = super().__new__(cls, *args, **kwargs)
        self.log = logging.getLogger(
            f"{LOGGER_NAME.get(__name__)}.{self.__class__.__name__}"
        )
        return self

    def check(self, username: str, password: str) -> bool:
        """
        Decides whether the given credentials are valid or not.

        This is required to be implemented in inheriting subclasses.

        Arguments:
            username: user name to be checked.
            password: password to be checked.

        Returns:
            `True` if credentials are valid, `False` if they are not.
        """
        raise NotImplementedError("credential checking logic is required to be defined")


class DummyAuth(Auth):
    """
    Dummy `Basic Authentication` class where password equals user name.

    Danger:
        This class is intended for testing only. DO NOT USE IN PRODUCTION!
    """

    def __init__(self):
        self.log.warning("DUMMY AUTHENTICATION. DO NOT USE IN PRODUCTION!")

    def check(self, username: str, password: str) -> bool:
        """
        Checks whether username and password are identical.

        Arguments:
            username: user name to compare.
            password: password to compare.

        Returns:
            `True` if username and password are identical, `False` if they are not.
        """
        return username == password


class LDAPAuth(Auth):
    """
    `Basic Authentication` using LDAP self-bind.
    """

    def __init__(
        self,
        server: str,
        base: str,
        use_ssl: bool = True,
        log_level: None | LDAP3LogLevel = None,
    ):
        """
        Arguments:
            server: address of the LDAP server.
            base: base for lookup on the LDAP server.
            use_ssl: flag whether to use SSL verification (`True`) or not (`False`).
            log_level: the logging level of the underlying LDAP3 library.
        """
        self.server = ldap3.Server(server, use_ssl=use_ssl)
        self.base = base

        self.log.info(f"using server {self.server.name}")
        self.log.info(f"using base {base}")

        if log_level is not None:
            set_library_log_detail_level(log_level)

    def check(self, username: str, password: str) -> bool:
        """
        Perform a self-bind connection to the given LDAP server.

        Arguments:
            username: user name to use for the LDAP self-bind connection.
            password: password to use for the LDAP self-bind connection.

        Returns:
            `True` if the LDAP self-bind connection could be established, i.e. was successful, `False` otherwise.
        """
        user = f"uid={username},{self.base}"

        try:
            self.log.debug(f"trying connection with username {username}")
            with ldap3.Connection(
                self.server,
                user=user,
                password=password,
            ) as conn:
                if conn.result["description"] == "success":
                    self.log.debug(f"succeeded self-bind with username {username}")
                    return True
                else:
                    self.log.debug(f"failed self-bind with username {username}")
                    return False

        except LDAPException as exc:
            self.log.warning(f"failed connection with username {username}: {exc}")
            return False
