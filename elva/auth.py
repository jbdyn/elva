from getpass import getpass

import ldap3
from ldap3.core.exceptions import LDAPException

LDAP_SERVER = "example-ldap.com"
LDAP_BASE = "ou=user,dc=example,dc=com"


# code from https://stackoverflow.com/a/65907735
def ldap_login(server, username, password):
    try:
        with ldap3.Connection(
            server, user=f"uid={username},{LDAP_BASE}", password=password
        ) as conn:
            # print(conn.result["description"])  # "success" if bind is ok
            return True
    except LDAPException:
        # print("Unable to connect to LDAP server")
        return False


if __name__ == "__main__":
    server = ldap3.Server(LDAP_SERVER, use_ssl=True)
    ldap_login(server, input("Username: "), getpass())
