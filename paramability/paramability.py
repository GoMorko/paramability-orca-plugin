# /// script
# requires-python = ">=3.9"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# name = "Paramability"
# description = "Opens Paramability in its own tab and saves what you export from it to a folder, ready for File > Import."
# author = "Paramability"
# version = "0.3.0"
# ///
"""Paramability tab for OrcaSlicer 2.5.

One Pages capability. The tab shows the Paramability web app. When the app exports a file, it sends the
bytes over the page bridge (protocol 1, below), and this plugin writes them to a folder on disk and shows a
note in the plater. OrcaSlicer has no plugin call that puts a file on the plate, so the person imports it.

Bridge protocol 1, JSON objects, `orca.postMessage` (page to plugin) and `post_message` (plugin to page):

  page   -> plugin  {type: "hello", protocol: 1, app_version}
  plugin -> page    {type: "host-info", protocol: 1, plugin_version, save_folder}
  page   -> plugin  {type: "file-begin", id, name, size, mime}
  page   -> plugin  {type: "file-chunk", id, index, data}   (base64, up to 1 MiB of raw bytes each)
  page   -> plugin  {type: "file-end", id, chunks}
  plugin -> page    {type: "file-saved", id, path}   (path is the shortened folder plus the file name)
                 or {type: "file-failed", id, reason}
  page   -> plugin  {type: "open-external", id, url}
  plugin -> page    {type: "external-opened", id}
                 or {type: "external-failed", id, reason}

`host-info` also lists `features`, the optional messages this plugin understands (`open-external`), so a
newer page can work with an older plugin. `reason` is one of the REASON_* codes below. A file the plugin
refuses (a type, size or load limit) is answered with file-failed at file-begin and is not kept; the page
stops sending it. A transfer that fails later is answered at once. Every file and every open-external gets
exactly one answer. The page is not trusted: names are cleaned, sizes are limited, a transfer that does not
finish is cut back to an empty file, and only plain http and https addresses are opened.

Chunks are written to the file as they arrive, so memory holds one chunk at a time. OrcaSlicer asks the
person before every rename or delete, so the file is created under its final name (a plain open, which the
folder grant covers) and a failed transfer is emptied, never renamed or deleted.
"""
import base64
import binascii
import collections
import html
import json
import math
import os
import re
import time
import unicodedata
import webbrowser

import orca

PLUGIN_VERSION = "0.3.0"
PROTOCOL = 1

CAPABILITY_NAME = "Paramability"
DEFAULT_URL = "https://paramability.app/?host=orcaslicer"
DEFAULT_SAVE_FOLDER = os.path.join("~", "Downloads", "Paramability")
# The biggest exports are a project with models and a rendered video. More than this is refused.
DEFAULT_MAX_FILE_MB = 512

REASON_TOO_LARGE = "too_large"
REASON_INCOMPLETE = "incomplete"
REASON_BAD_REQUEST = "bad_request"
REASON_BAD_TYPE = "type_not_allowed"
REASON_WRITE_FAILED = "write_failed"
REASON_BUSY = "busy"
REASON_OPEN_FAILED = "open_failed"

FEATURES = ["open-external"]
MAX_URL_LENGTH = 2048

MAX_CHUNK_BYTES = 1024 * 1024
MAX_OPEN_TRANSFERS = 4
# The declared sizes of all open transfers together may not pass this many times the file limit.
IN_FLIGHT_LIMIT_FACTOR = 2
# One link opening per this many seconds, so a page cannot flood the computer with browser tabs.
OPEN_EXTERNAL_MIN_SECONDS = 1.0
# A transfer the page never finished (a reload in the middle) is dropped after this long.
TRANSFER_TTL_SECONDS = 10 * 60
# Bytes, not characters: file systems limit names in bytes.
MAX_NAME_BYTES = 150
MAX_ID_LENGTH = 128
# How many refused or failed ids are remembered, so the file-end that still follows them gets no second answer.
MAX_ANSWERED_IDS = 64

# What the app exports: models, STEP, zips, pictures, videos, recipe scripts, build lists and the session log.
# Anything else is refused, so a page that is not the app cannot drop a script or a program into the folder.
ALLOWED_EXTENSIONS = frozenset({
    "3mf", "stl", "stp", "step", "zip", "png", "gif", "mp4", "webm", "scad", "py", "txt", "json",
})
# Files the person can load with File > Import in OrcaSlicer.
IMPORTABLE_EXTENSIONS = frozenset({"3mf", "stl", "step", "stp", "obj"})

_RESERVED_WINDOWS_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {"com%d" % n for n in range(1, 10)}
    | {"lpt%d" % n for n in range(1, 10)}
)
_UNSAFE_NAME_CHARS = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')


def split_name(name):
    """Return (stem, extension) of a name with no folders; the extension is lowercase, without the dot."""
    stem, dot, extension = name.rpartition(".")
    if not dot or not stem:
        return name, ""
    return stem, extension.lower()


def safe_file_name(raw):
    """Clean a file name from the page: no folders, no odd characters, a known extension.

    Returns (stem, extension) or None when nothing usable is left. The extension is kept, lowercase.
    """
    if not isinstance(raw, str):
        return None
    last = raw.replace("\\", "/").split("/")[-1]
    # Format characters (a right-to-left override, zero-width marks) can disguise an extension; lone surrogates cannot be encoded.
    last = "".join(char for char in last if unicodedata.category(char) not in ("Cf", "Cs"))
    last = _UNSAFE_NAME_CHARS.sub("_", last).strip().rstrip(". ").lstrip(".")
    stem, extension = split_name(last)
    if extension not in ALLOWED_EXTENSIONS:
        return None
    stem = stem.strip().rstrip(". ")
    if not stem:
        stem = "export"
    if stem.lower() in _RESERVED_WINDOWS_NAMES:
        stem = "_" + stem
    stem = stem.encode("utf-8", "ignore")[:MAX_NAME_BYTES].decode("utf-8", "ignore").rstrip(". ")
    return (stem or "export"), extension


def open_unique(folder, stem, extension):
    """Create a new file in `folder` named `stem.extension`, or `stem (2).extension` when it exists.

    Exclusive creation, so two saves can never share a file. Returns (file object, path).
    """
    for attempt in range(1, 1000):
        suffix = "" if attempt == 1 else " (%d)" % attempt
        path = os.path.join(folder, "%s%s.%s" % (stem, suffix, extension))
        try:
            return open(path, "xb"), path
        except FileExistsError:
            continue
    raise FileExistsError("no free name for %s.%s" % (stem, extension))


def display_folder(folder):
    """The folder with the home folder shortened to ~, for the note in the plater."""
    home = os.path.expanduser("~")
    if folder == home or folder.startswith(home + os.sep):
        return os.path.join("~", folder[len(home):].lstrip("\\/"))
    return folder


def _is_http_url(value):
    return isinstance(value, str) and re.match(r"^https?://[^\s]+$", value, re.IGNORECASE) is not None


def is_openable_url(value):
    """True for one plain http or https address: no spaces or control characters, a bounded length."""
    return (
        isinstance(value, str)
        and len(value) <= MAX_URL_LENGTH
        and re.match(r"^https?://[^\s\x00-\x1f\x7f]+$", value, re.IGNORECASE) is not None
    )


class _Transfer:
    """One file being received: its open handle, how far it got, and where it lives."""

    def __init__(self, handle, path, size):
        self.handle = handle
        self.path = path
        self.size = size
        self.chunks = 0
        self.received = 0
        self.started = time.monotonic()

    def abandon(self):
        """Close the file and empty it. OrcaSlicer asks before every delete, so it is cut back, not removed."""
        try:
            self.handle.close()
            open(self.path, "wb").close()
        except OSError:
            pass


class ParamabilityPage(orca.pages.PagesPluginCapabilityBase):
    def __init__(self):
        super().__init__()
        self._transfers = {}
        self._last_open = None
        self._answered = collections.deque(maxlen=MAX_ANSWERED_IDS)

    # -- capability surface ------------------------------------------------------------------

    def get_name(self):
        return CAPABILITY_NAME

    def get_icon(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "paramability.svg")

    def get_default_config(self):
        return {"url": DEFAULT_URL, "save_folder": DEFAULT_SAVE_FOLDER, "max_file_mb": DEFAULT_MAX_FILE_MB}

    def get_ui(self):
        url = self._config()["url"]
        # The page only forwards to the app. Every address it can carry is checked to be http or https.
        return (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<meta http-equiv='refresh' content='0;url=%s'></head><body>"
            "<p>Opening Paramability. If nothing happens, <a href='%s'>open it here</a>.</p>"
            "<script>location.replace(%s)</script></body></html>"
            % (html.escape(url, quote=True), html.escape(url, quote=True), json.dumps(url).replace("</", "<\\/"))
        )

    def on_message(self, data):
        if not isinstance(data, dict):
            return
        kind = data.get("type")
        if kind == "hello":
            self._on_hello()
        elif kind == "file-begin":
            self._on_file_begin(data)
        elif kind == "file-chunk":
            self._on_file_chunk(data)
        elif kind == "file-end":
            self._on_file_end(data)
        elif kind == "open-external":
            self._on_open_external(data)

    # -- config ------------------------------------------------------------------------------

    def _config(self):
        """The saved config over the defaults; a value of the wrong type falls back to its default."""
        config = self.get_default_config()
        try:
            saved = json.loads(self.get_config())
        except (TypeError, ValueError):
            saved = {}
        if isinstance(saved, dict):
            if _is_http_url(saved.get("url")):
                config["url"] = saved["url"]
            if isinstance(saved.get("save_folder"), str) and saved["save_folder"].strip():
                config["save_folder"] = saved["save_folder"].strip()
            limit = saved.get("max_file_mb")
            # JSON can carry Infinity and NaN, which are not sizes.
            if isinstance(limit, (int, float)) and not isinstance(limit, bool) and math.isfinite(limit) and limit > 0:
                config["max_file_mb"] = limit
        return config

    def _save_folder(self):
        return os.path.abspath(os.path.expanduser(self._config()["save_folder"]))

    def _max_bytes(self):
        return int(self._config()["max_file_mb"] * 1024 * 1024)

    # -- messages ----------------------------------------------------------------------------

    def _on_hello(self):
        # A hello means the page just loaded, so anything half sent before is dead.
        self._discard_all()
        self.post_message({
            "type": "host-info",
            "protocol": PROTOCOL,
            "plugin_version": PLUGIN_VERSION,
            "save_folder": display_folder(self._save_folder()),
            "features": FEATURES,
        })

    def _fail(self, transfer_id, reason):
        self._answered.append(transfer_id)
        self.post_message({"type": "file-failed", "id": transfer_id, "reason": reason})

    def _discard(self, transfer_id):
        transfer = self._transfers.pop(transfer_id, None)
        if transfer is not None:
            transfer.abandon()

    def _discard_all(self):
        for transfer_id in list(self._transfers):
            self._discard(transfer_id)

    def _drop_stale(self):
        now = time.monotonic()
        for key in [k for k, t in self._transfers.items() if now - t.started > TRANSFER_TTL_SECONDS]:
            self._discard(key)

    def _refusal_for(self, parts, size):
        """The reason to refuse a new transfer of this name and size, or None."""
        if len(self._transfers) >= MAX_OPEN_TRANSFERS:
            return REASON_BUSY
        if parts is None:
            return REASON_BAD_TYPE
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            return REASON_BAD_REQUEST
        limit = self._max_bytes()
        if size > limit:
            return REASON_TOO_LARGE
        if sum(t.size for t in self._transfers.values()) + size > limit * IN_FLIGHT_LIMIT_FACTOR:
            return REASON_BUSY
        return None

    def _on_file_begin(self, data):
        transfer_id = data.get("id")
        if not isinstance(transfer_id, str) or not transfer_id or len(transfer_id) > MAX_ID_LENGTH:
            return
        # The same id again starts over.
        self._discard(transfer_id)
        if transfer_id in self._answered:
            self._answered.remove(transfer_id)
        self._drop_stale()
        size = data.get("size")
        parts = safe_file_name(data.get("name"))
        failed = self._refusal_for(parts, size)
        if failed is not None:
            self._fail(transfer_id, failed)
            return
        try:
            handle, path = self._create(*parts)
        except OSError:
            # A refused permission is a PermissionError, which is an OSError too.
            self._fail(transfer_id, REASON_WRITE_FAILED)
            return
        self._transfers[transfer_id] = _Transfer(handle, path, size)

    def _on_file_chunk(self, data):
        transfer_id = data.get("id")
        transfer = self._transfers.get(transfer_id)
        if transfer is None:
            return
        encoded = data.get("data")
        if data.get("index") != transfer.chunks or not isinstance(encoded, str):
            self._abort(transfer_id, REASON_INCOMPLETE)
            return
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            self._abort(transfer_id, REASON_BAD_REQUEST)
            return
        if len(raw) > MAX_CHUNK_BYTES or transfer.received + len(raw) > transfer.size:
            self._abort(transfer_id, REASON_TOO_LARGE)
            return
        try:
            transfer.handle.write(raw)
        except (OSError, ValueError):
            self._abort(transfer_id, REASON_WRITE_FAILED)
            return
        transfer.chunks += 1
        transfer.received += len(raw)

    def _abort(self, transfer_id, reason):
        """Stop a transfer that went wrong; the page is told now, so it stops sending."""
        self._discard(transfer_id)
        self._fail(transfer_id, reason)

    def _on_file_end(self, data):
        transfer_id = data.get("id")
        if not isinstance(transfer_id, str):
            return
        transfer = self._transfers.pop(transfer_id, None)
        if transfer is None:
            # A transfer that was refused or failed was answered already; one never begun is answered now.
            if transfer_id not in self._answered:
                self._fail(transfer_id, REASON_INCOMPLETE)
            return
        if data.get("chunks") != transfer.chunks or transfer.received != transfer.size:
            transfer.abandon()
            self._fail(transfer_id, REASON_INCOMPLETE)
            return
        try:
            transfer.handle.close()
        except OSError:
            transfer.abandon()
            self._fail(transfer_id, REASON_WRITE_FAILED)
            return
        shown_folder = display_folder(os.path.dirname(transfer.path))
        name = os.path.basename(transfer.path)
        self.post_message({"type": "file-saved", "id": transfer_id, "path": os.path.join(shown_folder, name)})
        self._notify_saved(transfer.path)

    def _on_open_external(self, data):
        """Open a web address in the computer's browser. A tab in OrcaSlicer cannot, it only loads it over the app."""
        request_id = data.get("id")
        if not isinstance(request_id, str) or not request_id or len(request_id) > MAX_ID_LENGTH:
            return
        url = data.get("url")
        if not is_openable_url(url):
            self.post_message({"type": "external-failed", "id": request_id, "reason": REASON_BAD_REQUEST})
            return
        now = time.monotonic()
        if self._last_open is not None and now - self._last_open < OPEN_EXTERNAL_MIN_SECONDS:
            self.post_message({"type": "external-failed", "id": request_id, "reason": REASON_BUSY})
            return
        self._last_open = now
        try:
            opened = webbrowser.open(url)
        except (OSError, webbrowser.Error):
            # A refused permission is a PermissionError, which is an OSError too.
            opened = False
        if opened:
            self.post_message({"type": "external-opened", "id": request_id})
        else:
            self.post_message({"type": "external-failed", "id": request_id, "reason": REASON_OPEN_FAILED})

    # -- disk and plater ---------------------------------------------------------------------

    def _create(self, stem, extension):
        """Create the file under a free name in the save folder, ready to write. Returns (handle, path)."""
        folder = self._save_folder()
        # Creating a folder asks the person again every time, so it is only done when it is missing.
        if not os.path.isdir(folder):
            os.makedirs(folder)
        return open_unique(folder, stem, extension)

    def _notify_saved(self, path):
        _, extension = split_name(os.path.basename(path))
        hint = " Use File > Import to add it." if extension in IMPORTABLE_EXTENSIONS else ""
        message = "Saved %s to %s.%s" % (os.path.basename(path), display_folder(os.path.dirname(path)), hint)
        try:
            level = orca.host.ui.NotificationLevel.RegularNotificationLevel
            orca.host.ui.push_notification(level, message)
        except Exception:
            # The file is saved and the page is told; a missing note must not undo that.
            pass


@orca.plugin
class ParamabilityPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(ParamabilityPage)
        # Asked once at load. A folder tree grant covers the folder and everything in it. Another folder
        # set in the config is asked for the first time a file is saved there.
        default_folder = os.path.abspath(os.path.expanduser(DEFAULT_SAVE_FOLDER))
        orca.request_permissions(fs_readwrite=[os.path.join(default_folder, "*")])
