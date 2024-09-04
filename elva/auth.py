from base64 import b64decode, b64encode
from getpass import getpass
from http import HTTPStatus

import ldap3
from ldap3.core.exceptions import LDAPException

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
    reason: None | str = None,
    status: None | HTTPStatus = None,
):
    status = status or HTTPStatus.UNAUTHORIZED
    headers = {"WWW-Authenticate": f"Basic realm={realm}"}
    if reason:
        reason = reason.encode()
    return status, headers, reason


class BasicAuth:
    scheme = "Basic"

    def __init__(self, realm):
        self.realm = realm

    def authenticate(self, path, request_headers):
        try:
            scheme, credentials = process_authorization_header(request_headers)
        except KeyError:
            print("missing")
            return self.abort("missing Authorization header")
        except ValueError:
            print("malformed")
            return self.abort("malformed Authorization header")

        match scheme:
            case "Basic":
                username, password = process_basic_auth_credentials(credentials)
            case _:
                print("unsupported")
                return self.abort("unsupported Authorization scheme")

        if not self.verify(username, password):
            print("invalid")
            return self.abort("invalid credentials")

    def abort(self, reason=None, status=None):
        return abort_basic_auth(self.realm, reason=reason, status=status)

    def verify(self, username, password): ...


# code from https://stackoverflow.com/a/65907735
def ldap_self_bind(username, password, server, ldap_base):
    try:
        user = f"uid={username},{ldap_base}"
        with ldap3.Connection(
            server,
            user=user,
            password=password,
        ):  # as conn
            # res = conn.result["description"]  # "success" if bind is ok
            return True
    except LDAPException:
        # print("Unable to connect to LDAP server")
        return False


if __name__ == "__main__":
    ldap_server = "example-ldap.com"
    ldap_base = "ou=user,dc=example,dc=com"

    server = ldap3.Server(ldap_server, use_ssl=True)

    ldap_self_bind(input("Username: "), getpass(), server, ldap_base)
