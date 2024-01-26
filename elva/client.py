import anyio
from pycrdt import Doc, Text
from pycrdt_websocket import WebsocketProvider
from websockets import connect
from apps.editor import Editor
from providers import ElvaProvider
from time import sleep
import argparse
from utils import load_ydoc, save_ydoc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog='Elva - collaborative text editor')
    parser.add_argument("--save", "-s",  nargs='?', const='./ydoc', metavar='path', help='path where the ydoc should saved')
    parser.add_argument("--load", "-l",  nargs='?', const='./ydoc', metavar='path', help='path from where the ydoc should be loaded')
    parser.add_argument("--uuid", "-id", nargs='?', const='',       metavar='uuid', help='uuid of the file you wanna open')
    return parser.parse_args()

async def client():
    args = parse_args()
    ydoc = Doc()

    editor = Editor(ydoc)
    if args.load:
        print("loading")
        load_ydoc(ydoc, path=args.load)

    uuid = "9914bba9-8f17-429f-ab97-6b60f61bc49" if not args.uuid else args.uuid
    async with (
        connect("ws://localhost:1234/") as websocket,
        ElvaProvider({uuid: ydoc}, websocket) as provider,
    ):
        await editor.run_async()
    
    if args.save:
        print("saving")
        save_ydoc(ydoc, path=args.save)

anyio.run(client)
