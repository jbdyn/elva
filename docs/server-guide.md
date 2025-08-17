# Server Guide

ELVA comes with a websocket server app, which can be simply run with

```
elva server
```

listening for connections on `0.0.0.0` and a random port by default.
The host and port can be customized, of course:

```
elva server --host 127.0.0.1 --port 8765
```

## Persistence

The `--persistent` option controls the lifetime of documents:

- absent: No information are stored at all. When all peers disconnect, the identifier is free for a new document.

    ```
    elva server
    ```

- present without argument: The document is held in volatile memory and lives as long as the server process. Content is discarded on shutdown or restart.

    ```
    elva server --persistent
    ```

- present with argument: Documents are written to and read from disk under the specified path, hence surviving the server process.

    ```
    elva server --persistent path/to/documents
    ```
