# User Guide

## Installation

In order to use ELVA, run

```sh
pipx install elva
```

to install it in its own global environment or via

```sh
pip install elva
```

in your custom one.
After starting a new shell (and perhaps reactivating your environment), the command `elva` should be available to you:

```
elva --help
```


## Tutorial

### First Step

ELVA does not need anything special to start working on shared documents.
Type

```sh
elva edit
```

and you will see ELVA's real-time capable editor.

However, this way, your work is **neither saved nor shared**.


### Connect or Publish

To be able to really share the work you are seeing, you need to specify where to connect to peers.
Point ELVA to a websocket server being capable of forwarding websocket messages.
You do this with

```
elva --server ws://<url-to-server> edit
```

This publishes the document and its contents on the specified server under a random [UUID](https://datatracker.ietf.org/doc/html/rfc4122) (v4).

On some servers, you will need to give credentials to authenticate yourself.
Provide them with the `--username` and `--password` options:

```
elva --server ws://<url-to-server> --username foo --password mY$3cR3T edit
```


### Customize the Identifier

Sometimes, UUIDs are not desired for the sake of readability, sharability or other reasons. You can change the identifier of a document to your liking with

```
elva --identifier <my-identifier> edit
```

Please note that your custom identifier might have been already chosen by someone else or enables others to guess it.


### Save Content Locally

You are now able to contribute to published documents and can continue to do so if this documents *remains* published by servers or other peers.

This makes you dependent on external resources.

You can address this by specifying a filename:

```
elva edit my-file.md
```

This saves the document locally on your system and you can work on it even if you are offline.
The documents are then merged automatically on the next connection to the synchronizing server.

ELVA saves contents in files with a `.y` extension, so with the example above one would get a `my-file.md.y` file.
This is basically an [SQLite](https://sqlite.org/) database containing the update history alongside some metadata.


### Render Content

To actually get a `my-file.md`, you will need to render it from within the ELVA editor.


### Save Settings

Typing in server URLs or identifiers is cumbersome.
So instead you can save those information in several places ELVA reads them from:

- in the global `elva.toml`
- in the project's `elva.toml`
- in the `.y`-file

Those obey a specified order of precedence (from highest to lowest):

- command line arguments
- the `.y`-file
- the project's `elva.toml`
- the global `elva.toml`
- defaults

ELVA reads in configuration files automatically and the result can be printed with

```
elva context
```

You can also specify a path to a certain `elva.toml` configuration file:

```
elva --config path/to/config edit
```

## Apps

### Editor

```
elva edit
```

The built in editor can be used for any plain text file.

### Chat

```
elva chat
```

The chat enables real-time previews of composed messages and stores the history.


### Service

```
elva service
```

The service is mainly intended for background synchronization.
