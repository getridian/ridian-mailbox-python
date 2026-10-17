import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from test_client import Response, setup_result

from ridian_mailbox import Mailbox, MailboxError
from ridian_mailbox._state import load_or_create_state, prepare_curl, save_state
from ridian_mailbox.cli import main


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.box = Mailbox(base_url="https://api.example.test", state=self.path)
        self.box._transport = Mock()

    def seed(self):
        self.box._transport.open.return_value = Response(setup_result())
        self.box.setup()

    def test_invalid_setup_keeps_original_state(self):
        original = self.box._state(create=True)
        for field in ("access_token", "claim_secret"):
            with self.subTest(field=field):
                response = setup_result()
                response[field] = "invalid"
                self.box._transport.open.return_value = Response(response)
                with self.assertRaises(MailboxError):
                    self.box.setup()
                self.assertEqual(json.loads(self.path.read_text()), original)

    def test_response_cannot_replace_setup_identity(self):
        original = self.box._state(create=True)
        response = setup_result()
        response.update(
            base_url="https://other.example", setup_token="invalid", event_cursor="lost"
        )
        self.box._transport.open.return_value = Response(response)
        self.box.setup()
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved["setup_token"], original["setup_token"])
        self.assertEqual(saved["base_url"], original["base_url"])
        self.assertNotIn("event_cursor", saved)

    def test_repeated_cursor_stops_iteration(self):
        self.seed()
        self.box._transport.open.return_value = Response({"data": [], "next_cursor": "same"})
        self.box._transport.open.side_effect = lambda *a, **k: Response(
            {"data": [], "next_cursor": "same"}
        )
        with self.assertRaises(MailboxError) as error:
            list(self.box.iter_messages())
        self.assertEqual(error.exception.code, "invalid_pagination_cursor")

    def test_invalid_timeout_and_page_limits(self):
        for timeout in (0, -1, float("inf"), float("nan"), True):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                Mailbox(base_url="https://api.example.test", timeout=timeout)
        for limit in (True, 0, 51, 2.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.box.messages(limit=limit)

    def test_invalid_json_is_sanitized(self):
        self.seed()
        self.box._transport.open.return_value = io.BytesIO(b"private response")
        self.box._transport.open.return_value.status = 200
        with self.assertRaises(MailboxError) as error:
            self.box.status()
        self.assertEqual(str(error.exception), "Mailbox request failed: invalid_response")

    def test_webhook_and_attachment_requests(self):
        self.seed()
        self.box._transport.open.return_value = Response({"configured": True})
        self.box.set_webhook(url="https://receiver.example.test/hooks", signing_secret="synthetic")
        request = self.box._transport.open.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(json.loads(request.data)["signing_secret"], "synthetic")
        data = io.BytesIO(b"attachment bytes")
        self.box._transport.open.return_value = data
        self.assertEqual(self.box.attachment("a/b"), b"attachment bytes")
        self.assertTrue(self.box._transport.open.call_args.args[0].full_url.endswith("a%2Fb"))


class StateAndCliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.origin = "https://api.example.test"

    def test_symlinks_and_non_regular_files_are_rejected(self):
        target = self.path.with_name("original.json")
        load_or_create_state(target, self.origin)
        self.path.symlink_to(target)
        with self.assertRaises(OSError):
            load_or_create_state(self.path, self.origin)
        self.path.unlink()
        os.mkfifo(self.path, 0o600)
        with self.assertRaises(ValueError):
            load_or_create_state(self.path, self.origin)

    def test_invalid_state_is_preserved(self):
        self.path.write_text("[]")
        self.path.chmod(0o600)
        with self.assertRaises(ValueError):
            load_or_create_state(self.path, self.origin)
        self.assertEqual(self.path.read_text(), "[]")

    def test_atomic_write_failure_keeps_old_state(self):
        before = load_or_create_state(self.path, self.origin)
        with patch("ridian_mailbox._state.os.replace", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                save_state(self.path, {**before, "event_cursor": "next"})
        self.assertEqual(json.loads(self.path.read_text()), before)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_curl_preparation_preserves_existing_response(self):
        state = load_or_create_state(self.path, self.origin)
        prepare_curl(self.path, state)
        response = Path(str(self.path) + ".response.json")
        response.write_text("saved response")
        prepare_curl(self.path, state)
        self.assertEqual(response.read_text(), "saved response")
        for path in (self.path, response, Path(str(self.path) + ".headers")):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_cli_setup_uses_library_and_omits_credentials(self):
        argv = ["ridian-mailbox", "--base-url", self.origin, "--state", str(self.path), "setup"]
        with patch("sys.argv", argv), patch("ridian_mailbox.client.build_opener") as opener:
            opener.return_value.open.return_value = Response(setup_result())
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(), 0)
            self.assertEqual(json.loads(output.getvalue()), setup_result()["mailbox"])
            self.assertNotIn("access_token", output.getvalue())
            self.assertTrue(self.path.exists())

    def test_cli_http_error_cannot_print_arbitrary_headers_or_body(self):
        argv = ["ridian-mailbox", "--base-url", self.origin, "--state", str(self.path), "setup"]
        with patch("sys.argv", argv), patch("ridian_mailbox.client.build_opener") as opener:
            opener.return_value.open.side_effect = HTTPError(
                self.origin, 429, "private", {"Retry-After": "private"}, io.BytesIO(b"private")
            )
            with contextlib.redirect_stderr(io.StringIO()) as output:
                self.assertEqual(main(), 1)
            self.assertNotIn("private", output.getvalue())
            self.assertIn("60 seconds", output.getvalue())
