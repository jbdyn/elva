#!/usr/bin/env python

import asyncio

from websockets import serve

from elva.auth import BasicAuth  # , LDAPBasicAuth


class DummyBasicAuth(BasicAuth):
    def verify(self, username, password):
        print(username, password)
        return username == "janedoe" and password == "johndoe"


async def print_message(websocket):
    print(websocket.id, "connected")
    async for message in websocket:
        print(message)
        await websocket.send(message)
    print(websocket.id, "disconnected")


async def main():
    # LDAP_SERVER = "example-ldap.com"
    # LDAP_BASE = "ou=user,dc=example,dc=com"

    async with serve(
        print_message,
        "localhost",
        8000,
        process_request=DummyBasicAuth("dummy").authenticate,
        # process_request=LDAPBasicAuth("tub", LDAP_SERVER, LDAP_BASE).authenticate,
    ):
        print("serving...")
        await asyncio.Future()  # run forever


try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("closing")
