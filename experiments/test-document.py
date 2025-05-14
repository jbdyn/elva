from pycrdt import Doc, Text

from elva.document import YDocument

doc = Doc()
text = Text()
doc["text"] = text

ydoc = YDocument(text)

text += "tes🏴󠁧󠁢󠁳󠁣󠁴󠁿t\na"

print(len("🏴󠁧󠁢󠁳󠁣󠁴󠁿"))
res = ydoc.get_text_range(ydoc.start, ydoc.end)
print(res)
print(ydoc.end)
