---
date: 2025-03-11
author:
  - Jakob Zahn
---

# About Strings in Python, Unicode Code Points and Grapheme Clusters

In Python, strings are not simply a sequence of characters and a character is not limited to a single letter, digit or punctuation mark.
Here is how that led to surprises in using Python bindings for Y-CRDTs.

<!-- more -->

## A bit of history

I know, I know, but this one is interesting!

In Python 2, there were [`str`](https://docs.python.org/2.7/library/functions.html#str), [`unicode`](https://docs.python.org/2.7/library/functions.html#unicode) and [`bytearray`](https://docs.python.org/2.7/library/functions.html#bytearray) [sequence types](https://docs.python.org/2.7/library/stdtypes.html#typesseq).
The types `str` and `unicode` were quite similar, with `str` being limited to 8-bit strings and only `unicode` being capable of interpreting Unicode code points.
This led to different behavior in the respective `splitlines()` methods and to the type-exclusive methods `unicode.isnumeric()` and `unicode.isdecimal()`.
A `bytearray` is a mutable sequence of integers between 0 (inclusive) and 256 (exclusive) and shares [most of the methods of mutable sequence types and `str`](https://docs.python.org/2.7/library/functions.html#bytearray).

The [sequence types changed](https://docs.python.org/3/library/stdtypes.html#textseq) then in Python 3: `unicode` became [`str`](https://docs.python.org/3/library/stdtypes.html#str) and there is an additional [`bytes`](https://docs.python.org/3/library/stdtypes.html#bytes) type which is the [immutable counterpart of `bytearray`](https://docs.python.org/3/library/stdtypes.html#bytearray-objects).
The `bytes` type can also be written as literals, but only allow (7-bit long) ASCII characters to be inserted and everything else, i.e. binary values above 127, needs to be escaped.


## The Surprise

While testing the ELVA editor, I curiously threw in some emoji.
Inserting `🌴`, `a`, `b` and `c` in sequence however led to `🌴cba` instead of the expected `🌴abc`.
Whoops, how did this happen?

Internally, the editor used the `pycrdt.Text` Y text data type binding for holding and synchronizing the content displayed in the editor's canvas.
This binding [aims to resemble the functionality](https://jupyter-server.github.io/pycrdt/usage/#quickstart) of Python's `str` type and inherits the indexing as well.

Now the clue: The Rust `yrs::types::text::TextRef` object, to which the `pycrdt.Text` binds,

> internally uses UTF-8 encoding and its length is described in a number of bytes rather than individual characters

as it is said [in the Yrs documentation](https://docs.rs/yrs/latest/yrs/types/text/struct.TextRef.html).
That means, `yrs::types::text::TextRef` uses UTF-8 indexing and `pycrdt.Text` is functionally nearer to a `bytes` type than to a `str` type in Python.

So, the indices given on text manipulation were simply wrong.


## Unicode Code Points and Grapheme Clusters

Let's do some measurements.
In Python, the length of the palm emoji `🌴` string literal is 1:

```python
>>> len("🌴")
1
```

whereas its UTF-8 encoded form `b'\xf0\x9f\x8c\xb4'`, which is also stored in `TextRef`, has a length of 4:

```python
>>> len("🌴".encode(encoding="utf-8"))
4
```

That is the index difference which caused the messed up character order in `🌴cba`.
`b` is shown before `a` because it was inserted at the `str` index 2, but the UTF-8 index 2 is inside the palm emoji code point.
`b` gets thereby appended right after the palm emoji, but before the `a` inserted previously at `str` index 1.
Analogously, the same happens when inserting `c`.

So far so good.
Now we know the bug in the editor.
But what about other emoji?
Do they also have a length of 1?
No.

An example would be the *part alternation mark* `〽️`, where the Python string literal has a length of 2:

```python
>>> len("〽️")
2
```

In the Python `str` type, the index corresponds to Unicode code points.
`🌴` is described in a single code point, whereas `〽️` consists of two.

But `〽️` is still displayed as one unit.
The [Unicode Standard Annex #29](https://www.unicode.org/reports/tr29/#Grapheme_Cluster_Boundaries) about Unicode text segmentation denotes such a user-perceived character a *grapheme cluster* - a stack of code points.

Knowing this does not help us fixing this bug.
Whether it is code point, grapheme cluster or another kind of indexing being used, some conversion needs to happen to and from UTF-8 indexing when changing the text.
But it will be helpful to know about it when refining the editor.
The end-user might care about pressing the backspace key only once or multiple times to delete a single grapheme cluster.


## The Workaround

It became clear that there is a mismatch between the suggested `str`-like indexing in `pycrdt.Text` and the actual indexing in `yrs::types::text::TextRef`.

Generally, converting from code point to UTF-8 indexing depends on the edited range and content.
The naive way requires encoding of the given string slice up to the given index and measuring the resulting length:

```python
utf8_index = len(my_str[:code_point_index].encode(encoding="utf-8"))
```

Similarily, in reverse, you would decode the binary string up to the given UTF-8 index and also measure its length:

```python
code_point_index = len(my_bytes[:utf8_index].decode(encoding="utf-8"))
```

Here, `my_bytes = my_str.encode(encoding="utf-8")`, or, equivalently `my_str = my_bytes.decode(encoding="utf-8")`.

So, you would need to have access to the whole text - either encoded or decoded - to be able to do the index conversion on every text manipulation (!), which seems neither efficient nor elegant, but has at least the advantage of being stateless.


## The Proper Fix

We can probably do better.

There is the [pull request #129](https://github.com/jupyter-server/pycrdt/pull/129) in the `pycrdt` repo dealing with the indexing problem, so for technical details you might want to look into this as well.

A developer needs to be aware that `pycrdt.Text` tries to be like `str`, but needs indices like `bytes` or `bytearray` to work.
Furthermore, for a proper text editor, we have another issue to solve:
The end-user expects cursor movements on boundaries of (perceived) characters or even bigger blocks like images rather than bytes.

Hence, the editor would need to somewhere keep track of a mapping between the user-used indexing and the indexing used for operation.
<!-- (There is also the mapping between cursor position in the text and on the screen, but that is [another story](./write-a-realtime-editor.md).) -->

I have a few ideas to approach this:

- Make `pycrdt.Text` only accept `bytes` arguments and explain the indexing properly in the documentation.
  That would avoid confusion, but this alone still leaves the index conversion to every single developer.
- Keep track of the cursor position or selection ranges in user space *and* bytes space.
  Thereby, updates can be done incrementally on small portions of the content rather than on the whole text, but that also introduces another state and with it a potential source of bugs.
- Let `pycrdt.Text` keep track of a mapping between code point indices of `str` and UTF-8 indices in `yrs::types:text:TextRef` and do the index conversion internally.
  In the worst case, the editor could end up with two mappings: user indexing to code point indexing outside of `pycrdt.Text` plus code point indexing to UTF-8 indexing inside.
  With that we would go too far.
- An index converter object which can be subclassed might be a good fit here:
  The default index converter provided by `pycrdt` maps between code point indices and UTF-8 indices and developers are free to adapt the converter to translate between grapheme cluster boundaries or blocks and UTF-8 indexing.

Either way, one needs to think about how an index mapping could be efficiently, elegantly and robustly implemented.
Maybe with double-ended queues?

*To be continued ...*
