---
date: 2025-03-11
author:
  - Jakob Zahn
---

# Indexing in Y-CRDTs

The indices of the Y data types in Python are not necessarily the same as the underlying Rust Y data types.
Here is why.

<!-- more -->

- UTF-8 encoding
- Strings in Python 2 and 3
- Unicode, codepoints, grapheme clusters

