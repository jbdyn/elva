from pycrdt import Doc, Text
from editor import Store
import anyio
import signal

def signal_handler(signum, frame):
    print(f"You raised a SigInt! Signal handler called with signal {signum}")
    print("exiting...")
    exit()

signal.signal(signal.SIGINT, signal_handler)

async def main():
    ydoc = Doc()
    ydoc["text"] = ytext = Text()
    store = Store('.', "test", ydoc)

    def text_callback(event):
        print("__class__", event.__class__)
        print("__dir__()", event.__dir__())
        print("target", event.target)
        print("delta", event.delta)
        print("path", event.path)


    ytext.observe(text_callback)

    def doc_callback(event):
        print("__class__", event.__class__)
        print("__dir__()", event.__dir__())
        print("update", event.update)
        print("before_state", event.before_state)
        print("after_state", event.after_state)
        print("delete_set", event.delete_set)
        print("transaction", event.transaction)

    ydoc.observe(doc_callback)

    async with store:
        try:
            await store.apply_updates()
        except Exception as e:
            print(e)
            
        ytext += "test"
        await anyio.sleep_forever()
        signal.raise_signal(signal.SIGINT)

anyio.run(main)
