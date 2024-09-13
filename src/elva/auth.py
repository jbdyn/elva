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


def basic_authorization_header(username, password):
    bvalue = f"{username}:{password}".encode()
    b64bvalue = b64encode(bvalue).decode()

    return {"Authorization": f"Basic {b64bvalue}"}


def process_authorization_header(request_headers):
    auth_header = request_headers["Authorization"]
    scheme, credentials = auth_header.split(" ", maxsplit=1)
    if scheme not in AUTH_SCHEME:
        raise ValueError("invalid scheme in Authorization header")
    return scheme, credentials


def process_basic_auth_credentials(credentials: str):
    bb64cred = credentials.encode()
    bcred = b64decode(bb64cred)
    cred = bcred.decode()
    username, password = cred.split(":", maxsplit=1)
    return username, password


def abort_basic_auth(
    realm: str,
    body: None | str = None,
    status: HTTPStatus = HTTPStatus.UNAUTHORIZED,
):
    status = status
    headers = {"WWW-Authenticate": f"Basic realm={realm}"}
    if body:
        body = body.encode()
    return status, headers, body


class BasicAuth:
    def __new__(cls, *args, **kwargs):
        self = super().__new__(cls)
        self.log = logging.getLogger(
            f"{LOGGER_NAME.get(__name__)}.{self.__class__.__name__}"
        )
        return self

    def __init__(self, realm):
        self.realm = realm

    def authenticate(self, path, request_headers):
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

    def verify(self, username, password): ...


class DummyAuth(BasicAuth):
    def verify(self, username, password):
        return username == password


class LDAPBasicAuth(BasicAuth):
    def __init__(self, realm, server, base):
        super().__init__(realm)
        self.server = ldap3.Server(server, use_ssl=True)
        self.base = base
        self.log.info(f"server: {self.server.name}, base: {base}")

    def verify(self, username, password):
        user = f"uid={username},{self.base}"
        try:
            self.log.debug("try LDAP connection")
            with ldap3.Connection(
                self.server,
                user=user,
                password=password,
            ):  # as conn
                # res = conn.result["description"]  # "success" if bind is ok
                self.log.debug(f"successful self-bind with {user}")
                return True
        except LDAPException:
            self.log.debug(f"unable to connect with {user}")
            return False
