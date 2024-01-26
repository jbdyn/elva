import json
import os.path
from pycrdt import Doc


def pprint_json(json_str):
    print(json.dumps(
        json.loads(json_str), indent=4, sort_keys=True
    ))

def print_tree(tree):
    pprint_json(tree.to_json())

def print_event(self, event):
    ftype = "directory" if event.is_directory else "file"
    msg = f"> {ftype} '{event.src_path}' {event.event_type}!"
    print(msg)

def save_ydoc(ydoc: Doc, path: str = "./ydoc"):
    with open(path, "wb") as file:
        state = ydoc.get_update()
        file.write(state)

def load_ydoc(ydoc: Doc, path: str = "./ydoc"):
    with open(path, "rb") as file:
        state = file.read()
        try:
            assert(os.path.isfile(path))
            ydoc.apply_update(state)
        except Exception as e:
            print(f"could not resore state from {path}")
            print("check:")
            print(e)
            raise e