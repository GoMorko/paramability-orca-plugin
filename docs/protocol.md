# Protocol between the app and the plugin

Version 1. JSON objects. The page sends with `orca.postMessage(...)`; the plugin answers with `post_message(...)`.
OrcaSlicer gives the page `window.orca` in a plugin tab.

| Direction | Message |
| --- | --- |
| page to plugin | `{type: "hello", protocol: 1, app_version}` |
| plugin to page | `{type: "host-info", protocol: 1, plugin_version, save_folder, features}` |
| page to plugin | `{type: "file-begin", id, name, size, mime}` |
| page to plugin | `{type: "file-chunk", id, index, data}` (base64, up to 1 MiB of raw bytes) |
| page to plugin | `{type: "file-end", id, chunks}` |
| plugin to page | `{type: "file-saved", id, path}` or `{type: "file-failed", id, reason}` |
| page to plugin | `{type: "open-external", id, url}` (only when `features` lists `open-external`) |
| plugin to page | `{type: "external-opened", id}` or `{type: "external-failed", id, reason}` |

## Rules

- The page says `hello` first and waits for `host-info`. A message sent before the page exists is lost, so the
  page always asks.
- `features` lists the optional messages that the plugin understands. An older plugin sends no list, which means
  none. So a newer page can work with an older plugin.
- Every file and every `open-external` gets exactly one answer.
- A file that the plugin refuses at `file-begin` gets `file-failed` at once. The page then stops sending it.
- Chunks must come in order. A missing or out-of-order chunk stops the transfer.
- `path` in `file-saved` is the short folder (for example `~/Downloads/Paramability`) plus the file name, not the
  full path.
- `reason` for a file: `too_large`, `incomplete`, `bad_request`, `type_not_allowed`, `write_failed`, `busy`.
- `reason` for a link: `bad_request`, `busy`, `open_failed`.

The plugin does not trust the page: OrcaSlicer does not check which page sends a message. Names are cleaned,
sizes and types are limited, and only plain http and https links are opened.
