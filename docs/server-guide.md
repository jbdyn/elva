# Server Guide

ELVA comes with a websocket server app, which can be simply run with

```
elva serve
```

listening for connections on port 8000 by default.
The host and port can be customized, of course:

```
elva serve 127.0.0.1 8765
```

## Persistence

The `--persistent` option controls the lifetime of documents:

- absent: No information are stored at all. When all peers disconnect, the identifier is free for a new document.

    ```
    elva serve
    ```

- present without argument: The document is held in volatile memory and lives as long as the server process. Content is discarded on shutdown or restart.

    ```
    elva serve --persistent
    ```

- present with argument: Documents are written to and read from disk under the specified path, hence surviving the server process.

    ```
    elva serve --persistent path/to/documents
    ```
