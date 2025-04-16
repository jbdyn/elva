---
date: 2025-04-16
author:
  - Jakob Zahn
---


# How to (Not) Write `Textual`-Apps

`Textual` is a great framework for text-based UI applications and has a [very well written documentation](https://textual.textualize.io/) to get started instantly.
In addition, here are some tips after lots of lines of code for widgets and apps.

<!-- more -->

## Where to put Textual CSS

For developing and debugging, write a separate TCSS file and use `textual console` and `textual run --dev my_textual_app.py` to speed up your workflow with `Textual`s live editing feature.
This applies changes to TCSS files while the app is running.

However, for shipping default styles in the library, write the style into the `CSS` class attribute of an app or a widget.
This makes it easier to ship (no additional files need to be declared to be included in the Python package) and to differentiate between default and new styles.


## References to Widgets

Don't keep references to widgets. [Query them](https://textual.textualize.io/guide/queries/).

This has several advantages:

- Sometimes, widgets break if initialized and referenced in an app's `__init__` method.
- There are less attributes and arguments to manage, which makes code shorter.
- Initialization on mount is isolated in the `compose` method.
- Code can be written stateless.
