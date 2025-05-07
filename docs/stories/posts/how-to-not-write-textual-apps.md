---
date: 2025-04-16
author:
  - Jakob Zahn
---


# How to (Not) Write `Textual`-Apps

`Textual` is a great framework for text-based UI applications and has a [very well written documentation](https://textual.textualize.io/) to get started instantly.
In addition, here are some tips I wish I had known when I started.

<!-- more -->

## Where to put Textual CSS

For developing and debugging, write a separate TCSS file and use `textual console` and `textual run --dev my_textual_app.py` to speed up your workflow with `Textual`s live editing feature.
This applies changes to TCSS files while the app is running.

However, for shipping default styles in the library, write the style into the `CSS` class attribute of an app or a widget.
This makes it easier to ship (no additional files need to be declared to be included in the Python package) and to differentiate between default and new styles.

Last but not least, define your style in style sheets as much as possible, avoid writing it in code.


## References to Widgets

Don't keep references to widgets. [Query them](https://textual.textualize.io/guide/queries/).

This has several advantages:

- There are less attributes and arguments to manage, which makes code shorter.
- Initialization of widgets on mount is isolated in the `compose` method.
- Code can be written stateless.
- Sometimes, widgets break if initialized and referenced in an app's or widget's `__init__` method.


## Text-Based UI Design

Arrange your widgets vertically. And keep it simple.

At the time of writing, there are no breakpoints in TCSS.
Hence, you would either need to implement this functionality in the app or widget code yourself, which you would need to do for every app, or you need to find a design which works for all terminal sizes.
I recommend doing the latter and suggest to hereby arrange theh widgets vertically and not horizontally.
As a user, I tend to easily narrow down the width of my terminal window, but barely its height.

Additionally, with `Textual` you are probably writing a text-based UI and your users might be using the keyboard more than the mouse.
However, loading lots of (focusable) widgets into the canvas makes it tedious to navigate with the tab key.
I found myself being annoyed by that because I was kind of forced to use my mouse to make progress.
Thereby, I aim to use as less focusable widgets as possible. If that cannot be avoided, I try to isolated the navigation with a hidden widget or putting functionality in a separate screen.

Following this, you might wonder how this works for apps used in a purely graphical workflow.
I mean starting the app by clicking on a desktop icon and never seeing the command prompt, even after closing.
That implies to implement customizability into the app's UI, such that a user would have the possibility to configure the app's to the own needs.
Unfortunately, this collides with not having too much focusable widgets.
Maybe a REPL might solve this issue, as it unites keyboard friendliness with full control and slim UI design.
Stay tuned for a follow-up article on this!
<!-- For a solution to this, I recommend checking out [the post about a REPL `Textual` widget](./writing-a-textual-application-repl.md), which units keyboard friendliness with full control and slim UI design. -->
