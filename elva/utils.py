import json

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

