class Provider():
    def __init__(self, ydoc, connection):
        self.ydoc = ydoc
        self.connection = connection

    def generate_update(self):
        return ydoc.get_update()

    def send(self):
        update = self.generate_update()
        connection.send(update)

    def recv(self):
        update = connection.recv()
        self.apply(update)

    def apply(self, update):
        ydoc.set_update(update)
