import anyio

class Connection():
    def __init__(self):
        self.connected = anyio.Event()
        self.disconnected = anyio.Event()

    async def connect(self):
        while True:
            try:
                await connecting()
            except:
                continue
            else:
                self.connected.set()

    async def send(self, message):
        await self.connected.wait()
        try:
            await sending(message)
        except:
            self.connected = anyio.Event()
            self.disconnected.set()

    async def recv(self):
        async for message in receiving():
            return message
