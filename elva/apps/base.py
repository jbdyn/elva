from abc import ABC
from pycrdt import Doc

class BaseApp(ABC):
    def __init__(self, doc=None):
        self.doc = doc if doc is not None else Doc()
