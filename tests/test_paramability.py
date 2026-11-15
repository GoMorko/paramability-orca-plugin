"""Tests for the Paramability plugin against a fake `orca` module.

Run from the repository root: python3 -m unittest
"""
import base64
import importlib.util
import json
import os
import tempfile
import unittest

from tests import fake_orca

PLUGIN_PATH = os.path.join(os.path.dirname(__file__), os.pardir, "paramability", "paramability.py")


def load_plugin():
    calls = fake_orca.install()
    spec = importlib.util.spec_from_file_location("paramability_under_test", PLUGIN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, calls


class PluginTestCase(unittest.TestCase):
    def setUp(self):
        self.plugin, self.calls = load_plugin()
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.page = self.plugin.ParamabilityPage()
        self.addCleanup(self.page._discard_all)
        self.configure(save_folder=self.folder.name)

    def configure(self, **config):
        self.page.config_json = json.dumps(config)

    def send_file(self, file_id, name, payload, chunk_size=4, **overrides):
        """Send a whole transfer the way the app does. Overrides tweak what a broken page would get wrong."""
        chunks = [payload[i:i + chunk_size] for i in range(0, len(payload), chunk_size)]
        self.page.on_message({"type": "file-begin", "id": file_id, "name": name, "size": len(payload), "mime": ""})
        for index, chunk in enumerate(chunks):
            self.page.on_message(
                {"type": "file-chunk", "id": file_id, "index": index, "data": base64.b64encode(chunk).decode()}
            )
        self.page.on_message({"type": "file-end", "id": file_id, "chunks": overrides.get("chunks", len(chunks))})

    def last(self):
        return self.page.posted[-1]

    def files(self):
        return sorted(os.listdir(self.folder.name))

    def sizes(self):
        return {name: os.path.getsize(os.path.join(self.folder.name, name)) for name in self.files()}


class HelloAndConfig(PluginTestCase):
    def test_hello_is_answered_with_the_protocol_and_the_save_folder(self):
        self.page.on_message({"type": "hello", "protocol": 1, "app_version": "1.0.0"})
        info = self.last()
        self.assertEqual(info["type"], "host-info")
        self.assertEqual(info["protocol"], 1)
        self.assertTrue(info["save_folder"])

    def test_hello_lists_the_optional_messages_this_plugin_understands(self):
        self.page.on_message({"type": "hello", "protocol": 1})
        self.assertIn("open-external", self.last()["features"])

    def test_the_tab_page_forwards_to_the_configured_address_only_when_it_is_http(self):
        self.configure(url="https://localhost:5173/?host=orcaslicer")
        self.assertIn("https://localhost:5173/", self.page.get_ui())
        self.configure(url="javascript:alert(1)")
        ui = self.page.get_ui()
        self.assertNotIn("javascript:", ui)
        self.assertIn(self.plugin.DEFAULT_URL, ui)

    def test_a_config_value_of_the_wrong_type_falls_back_to_its_default(self):
        self.configure(max_file_mb="big", save_folder=7)
        config = self.page._config()
        self.assertEqual(config["max_file_mb"], self.plugin.DEFAULT_MAX_FILE_MB)
        self.assertEqual(config["save_folder"], self.plugin.DEFAULT_SAVE_FOLDER)

    def test_a_size_limit_that_is_not_a_finite_number_falls_back_to_the_default(self):
        for text in ('{"max_file_mb": Infinity}', '{"max_file_mb": NaN}', '{"max_file_mb": -3}'):
            self.page.config_json = text
            self.assertEqual(self.page._config()["max_file_mb"], self.plugin.DEFAULT_MAX_FILE_MB)
        self.page.config_json = '{"max_file_mb": Infinity}'
        self.assertEqual(self.page._max_bytes(), self.plugin.DEFAULT_MAX_FILE_MB * 1024 * 1024)

    def test_loading_registers_the_tab_and_asks_for_the_default_folder_once(self):
        self.plugin.ParamabilityPlugin().register_capabilities()
        self.assertEqual(self.calls.capabilities, [self.plugin.ParamabilityPage])
        self.assertEqual(len(self.calls.permissions), 1)
        granted = self.calls.permissions[0]["fs_readwrite"]
        self.assertEqual(len(granted), 1)
        self.assertTrue(granted[0].endswith(os.path.join("Paramability", "*")))


class SaveFlow(PluginTestCase):
    def test_a_complete_transfer_is_written_replied_to_and_announced(self):
        payload = bytes(range(50))
        self.send_file("a", "part.3mf", payload)
        self.assertEqual(self.files(), ["part.3mf"])
        with open(os.path.join(self.folder.name, "part.3mf"), "rb") as written:
            self.assertEqual(written.read(), payload)
        reply = self.last()
        self.assertEqual(reply["type"], "file-saved")
        self.assertEqual(reply["id"], "a")
        # The page gets the shortened folder and the name, never more of the path than the plater note shows.
        self.assertEqual(reply["path"], os.path.join(self.plugin.display_folder(os.path.abspath(self.folder.name)), "part.3mf"))
        self.assertEqual(len(self.calls.notifications), 1)
        self.assertIn("part.3mf", self.calls.notifications[0][1])
        self.assertIn("Import", self.calls.notifications[0][1])

    def test_chunks_are_written_to_the_file_as_they_arrive(self):
        self.page.on_message({"type": "file-begin", "id": "a", "name": "part.3mf", "size": 8})
        self.page.on_message({"type": "file-chunk", "id": "a", "index": 0, "data": base64.b64encode(b"abcd").decode()})
        self.page._transfers["a"].handle.flush()
        self.assertEqual(self.sizes(), {"part.3mf": 4})

    def test_a_name_in_use_gets_a_number_and_the_old_file_stays(self):
        self.send_file("a", "part.3mf", b"first")
        self.send_file("b", "part.3mf", b"second")
        self.assertEqual(self.files(), ["part (2).3mf", "part.3mf"])
        with open(os.path.join(self.folder.name, "part.3mf"), "rb") as kept:
            self.assertEqual(kept.read(), b"first")
        self.assertTrue(self.last()["path"].endswith("part (2).3mf"))

    def test_folders_in_the_name_never_leave_the_save_folder(self):
        self.send_file("a", "../../outside/..\\evil/part.STL", b"x")
        self.assertEqual(self.files(), ["part.stl"])

    def test_a_file_that_cannot_be_imported_is_saved_without_the_import_hint(self):
        self.send_file("a", "kit.zip", b"zip")
        self.assertEqual(self.files(), ["kit.zip"])
        self.assertNotIn("Import", self.calls.notifications[0][1])

    def test_a_missing_save_folder_is_created(self):
        nested = os.path.join(self.folder.name, "new", "folder")
        self.configure(save_folder=nested)
        self.send_file("a", "part.stl", b"x")
        self.assertEqual(os.listdir(nested), ["part.stl"])

    def test_a_failing_plater_note_does_not_undo_the_save(self):
        self.calls.notification_error = RuntimeError("no plater")
        self.send_file("a", "part.stl", b"x")
        self.assertEqual(self.last()["type"], "file-saved")


class RefusedTransfers(PluginTestCase):
    def posted_reasons(self):
        return [message.get("reason") for message in self.page.posted if message["type"] == "file-failed"]

    def assertRefused(self, reason):
        """The page was told why, no note was shown, and nothing readable is left in the folder."""
        self.assertEqual(self.last()["type"], "file-failed")
        self.assertEqual(self.last()["reason"], reason)
        self.assertEqual(sum(self.sizes().values()), 0)
        self.assertEqual(self.calls.notifications, [])

    def test_a_file_over_the_size_limit_is_refused_when_it_begins_and_nothing_is_created(self):
        self.configure(save_folder=self.folder.name, max_file_mb=0.00001)
        self.page.on_message({"type": "file-begin", "id": "a", "name": "part.3mf", "size": 100})
        self.assertRefused("too_large")
        self.assertEqual(self.files(), [])
        self.assertEqual(self.page._transfers, {})

    def test_refused_begins_are_not_stored_and_their_file_end_gets_no_second_answer(self):
        for index in range(50):
            self.page.on_message({"type": "file-begin", "id": "bad%d" % index, "name": "run.command", "size": 1})
        self.assertEqual(self.page._transfers, {})
        self.assertEqual(len(self.page.posted), 50)
        self.page.on_message({"type": "file-end", "id": "bad49", "chunks": 0})
        self.assertEqual(len(self.page.posted), 50)

    def test_total_bytes_in_flight_are_capped(self):
        self.configure(save_folder=self.folder.name, max_file_mb=1)
        one_mb = 1024 * 1024
        for index in range(self.plugin.IN_FLIGHT_LIMIT_FACTOR):
            self.page.on_message({"type": "file-begin", "id": "t%d" % index, "name": "p.3mf", "size": one_mb})
        self.page.on_message({"type": "file-begin", "id": "over", "name": "p.3mf", "size": one_mb})
        self.assertEqual(self.last(), {"type": "file-failed", "id": "over", "reason": "busy"})

    def test_more_bytes_than_declared_are_refused(self):
        self.page.on_message({"type": "file-begin", "id": "a", "name": "part.3mf", "size": 2})
        self.page.on_message({"type": "file-chunk", "id": "a", "index": 0, "data": base64.b64encode(b"abcd").decode()})
        self.page.on_message({"type": "file-end", "id": "a", "chunks": 1})
        self.assertRefused("too_large")

    def test_a_transfer_with_a_missing_chunk_is_refused(self):
        self.send_file("a", "part.3mf", bytes(10), chunks=5)
        self.assertRefused("incomplete")

    def test_chunks_out_of_order_are_refused(self):
        self.page.on_message({"type": "file-begin", "id": "a", "name": "part.3mf", "size": 4})
        self.page.on_message({"type": "file-chunk", "id": "a", "index": 1, "data": base64.b64encode(b"abcd").decode()})
        self.page.on_message({"type": "file-end", "id": "a", "chunks": 1})
        self.assertRefused("incomplete")

    def test_data_that_is_not_base64_is_refused(self):
        self.page.on_message({"type": "file-begin", "id": "a", "name": "part.3mf", "size": 4})
        self.page.on_message({"type": "file-chunk", "id": "a", "index": 0, "data": "not base64 !!"})
        self.page.on_message({"type": "file-end", "id": "a", "chunks": 1})
        self.assertRefused("bad_request")

    def test_a_file_type_outside_the_list_is_refused(self):
        self.send_file("a", "run.command", b"rm -rf")
        self.assertEqual(self.files(), [])
        self.assertEqual(self.posted_reasons()[0], "type_not_allowed")
        self.send_file("b", "model.obj", b"v 0 0 0")
        self.assertEqual(self.posted_reasons()[-2], "type_not_allowed")

    def test_an_end_with_no_begin_is_answered_as_incomplete(self):
        self.page.on_message({"type": "file-end", "id": "ghost", "chunks": 0})
        self.assertRefused("incomplete")

    def test_a_save_folder_that_cannot_be_written_is_reported(self):
        blocker = os.path.join(self.folder.name, "blocker")
        with open(blocker, "wb") as handle:
            handle.write(b"a file where the folder should be")
        self.configure(save_folder=os.path.join(blocker, "inside"))
        self.send_file("a", "part.3mf", b"x")
        self.assertEqual(self.last()["reason"], "write_failed")
        self.assertEqual(self.calls.notifications, [])

    def test_a_hello_drops_a_transfer_the_page_never_finished(self):
        self.page.on_message({"type": "file-begin", "id": "a", "name": "part.3mf", "size": 4})
        self.page.on_message({"type": "file-chunk", "id": "a", "index": 0, "data": base64.b64encode(b"ab").decode()})
        self.page.on_message({"type": "hello", "protocol": 1})
        self.assertEqual(self.sizes()["part.3mf"], 0)
        self.page.on_message({"type": "file-end", "id": "a", "chunks": 0})
        self.assertEqual(self.last()["reason"], "incomplete")

    def test_too_many_open_transfers_are_refused_at_once(self):
        for index in range(self.plugin.MAX_OPEN_TRANSFERS + 1):
            self.page.on_message({"type": "file-begin", "id": "t%d" % index, "name": "p.3mf", "size": 1})
        self.assertEqual(self.last(), {"type": "file-failed", "id": "t%d" % self.plugin.MAX_OPEN_TRANSFERS, "reason": "busy"})
        self.assertEqual(len(self.page._transfers), self.plugin.MAX_OPEN_TRANSFERS)

    def test_a_transfer_the_page_left_unfinished_for_too_long_is_emptied(self):
        self.page.on_message({"type": "file-begin", "id": "a", "name": "part.3mf", "size": 8})
        self.page.on_message({"type": "file-chunk", "id": "a", "index": 0, "data": base64.b64encode(b"abcd").decode()})
        self.page._transfers["a"].started -= self.plugin.TRANSFER_TTL_SECONDS + 1
        self.page.on_message({"type": "file-begin", "id": "b", "name": "other.3mf", "size": 1})
        self.assertNotIn("a", self.page._transfers)
        self.assertEqual(self.sizes()["part.3mf"], 0)

    def test_a_write_that_fails_part_way_tells_the_page_at_once(self):
        self.page.on_message({"type": "file-begin", "id": "a", "name": "part.3mf", "size": 8})
        self.page._transfers["a"].handle.close()
        self.page.on_message({"type": "file-chunk", "id": "a", "index": 0, "data": base64.b64encode(b"abcd").decode()})
        self.assertRefused("write_failed")
        self.assertEqual(self.page._transfers, {})

    def test_messages_that_are_not_objects_are_ignored(self):
        for junk in (None, "text", 5, ["file-end"], {"type": 3}, {"type": "file-begin"}):
            self.page.on_message(junk)
        self.assertEqual(self.page.posted, [])


class OpenExternal(PluginTestCase):
    def setUp(self):
        super().setUp()
        self.opened = []
        self.open_result = True
        original = self.plugin.webbrowser.open
        self.addCleanup(setattr, self.plugin.webbrowser, "open", original)
        self.plugin.webbrowser.open = self.fake_open

    def fake_open(self, url):
        if isinstance(self.open_result, Exception):
            raise self.open_result
        self.opened.append(url)
        return self.open_result

    def ask(self, url, request_id="r1"):
        # Each ask stands alone unless a test is about the rate limit.
        self.page._last_open = None
        self.page.on_message({"type": "open-external", "id": request_id, "url": url})

    def test_an_http_address_is_opened_in_the_browser_and_the_page_is_told(self):
        self.ask("https://example.com/guide?a=1")
        self.assertEqual(self.opened, ["https://example.com/guide?a=1"])
        self.assertEqual(self.last(), {"type": "external-opened", "id": "r1"})

    def test_anything_but_a_plain_web_address_is_refused_and_never_opened(self):
        for url in ("file:///etc/passwd", "javascript:alert(1)", "https://a.test/ x", "https://a.test/\nx", "mailto:a@b.c", None, 5):
            self.ask(url)
            self.assertEqual(self.last()["reason"], "bad_request")
        self.ask("https://a.test/" + "x" * 3000)
        self.assertEqual(self.last()["reason"], "bad_request")
        self.assertEqual(self.opened, [])

    def test_a_browser_that_does_not_open_or_a_refused_permission_is_reported(self):
        self.open_result = False
        self.ask("https://example.com/")
        self.assertEqual(self.last(), {"type": "external-failed", "id": "r1", "reason": "open_failed"})

        self.open_result = PermissionError("not allowed")
        self.ask("https://example.com/", "r2")
        self.assertEqual(self.last(), {"type": "external-failed", "id": "r2", "reason": "open_failed"})

    def test_a_second_link_inside_the_limit_is_refused_as_busy_and_not_opened(self):
        self.page.on_message({"type": "open-external", "id": "r1", "url": "https://example.com/a"})
        self.page.on_message({"type": "open-external", "id": "r2", "url": "https://example.com/b"})
        self.assertEqual(self.opened, ["https://example.com/a"])
        self.assertEqual(self.last(), {"type": "external-failed", "id": "r2", "reason": "busy"})
        self.page._last_open -= self.plugin.OPEN_EXTERNAL_MIN_SECONDS
        self.page.on_message({"type": "open-external", "id": "r3", "url": "https://example.com/c"})
        self.assertEqual(self.last(), {"type": "external-opened", "id": "r3"})

    def test_a_request_with_no_usable_id_gets_no_answer(self):
        self.page.on_message({"type": "open-external", "url": "https://example.com/"})
        self.assertEqual(self.page.posted, [])
        self.assertEqual(self.opened, [])


class FileNames(unittest.TestCase):
    def setUp(self):
        self.plugin, _ = load_plugin()

    def test_names_are_cleaned_to_a_stem_and_a_known_extension(self):
        clean = self.plugin.safe_file_name
        self.assertEqual(clean("a/b/c.3MF"), ("c", "3mf"))
        self.assertEqual(clean("..\\..\\win.stl"), ("win", "stl"))
        self.assertEqual(clean('we:ird*"na|me?.zip'), ("we_ird__na_me_", "zip"))
        self.assertEqual(clean(".hidden.stl"), ("hidden", "stl"))
        self.assertEqual(clean("CON.stl"), ("_CON", "stl"))
        self.assertEqual(clean(".stl"), None)
        self.assertEqual(clean("noextension"), None)
        self.assertEqual(clean("tool.exe"), None)
        self.assertEqual(clean("model.obj"), None)
        self.assertEqual(clean(None), None)

    def test_a_very_long_name_is_cut_by_bytes_and_keeps_its_extension(self):
        stem, extension = self.plugin.safe_file_name("x" * 400 + ".step")
        self.assertEqual(extension, "step")
        self.assertLessEqual(len(stem.encode("utf-8")), self.plugin.MAX_NAME_BYTES)
        wide, _ = self.plugin.safe_file_name("\u00e9" * 400 + ".stl")
        self.assertLessEqual(len(wide.encode("utf-8")), self.plugin.MAX_NAME_BYTES)
        self.assertTrue(wide)

    def test_format_characters_that_can_disguise_a_name_are_removed(self):
        # A right-to-left override makes "part\u202egnp.exe" read as "partexe.png" on screen.
        self.assertEqual(self.plugin.safe_file_name("part\u202e.stl"), ("part", "stl"))
        self.assertEqual(self.plugin.safe_file_name("pa\u200brt.stl"), ("part", "stl"))
        self.assertEqual(self.plugin.safe_file_name("lone\ud800.stl"), ("lone", "stl"))


if __name__ == "__main__":
    unittest.main()
