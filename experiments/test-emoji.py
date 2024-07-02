from pycrdt import Doc, Text

## setup

ydoc = Doc()
ytext = Text()
ydoc["text"] = ytext

state = ""            # track state of ytext


def callback(event):
    """Print change record"""
    global state

    new_state = str(event.target)
    delta = str(event.delta)
    print(f"{delta}: '{state}' -> '{new_state}'")

    # update current state
    state = new_state


ytext.observe(callback)


## Manipulate Text

print("Insert and delete single emoji '🌴'")
# works as expected
ytext.insert(0, "🌴")
assert state == "🌴"

# given index is for Unicode code points
# but callback returns length of individual bytes in delta
del ytext[0:len(str(ytext)[:1].encode())]
assert state == ""

print("\nInsert '🌴abcde' sequentially")
for c, char in enumerate("🌴abcde"):
    ytext.insert(len(str(ytext)[:c].encode()), char)
assert state == "🌴abcde"

