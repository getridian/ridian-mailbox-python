import io
import json
import tempfile
import unittest
from importlib.metadata import version
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from ridian_mailbox import Mailbox, MailboxError


class Response(io.BytesIO):
    status = 200

    def __init__(self, data):
        super().__init__(json.dumps(data).encode())


def setup_result():
    return {
        "mailbox": {"id": "box1", "address": "calm-panda-4821@example.test"},
        "access_token": "ridian_mailbox_" + "a" * 64,
        "claim_secret": "b" * 64,
        "claim_url": "https://console.example.test/mailbox/claim",
    }


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.box = Mailbox(base_url="https://api.example.test", state=self.path)
        self.box._transport = Mock()

    def seed(self):
        self.box._transport.open.return_value = Response(setup_result())
        self.box.setup()

    def test_first_request_is_recoverable_and_public_return_omits_secrets(self):
        tokens = []

        def send(req, timeout):
            saved = json.loads(self.path.read_text())
            self.assertEqual(req.headers["Authorization"], "Bearer " + saved["setup_token"])
            self.assertEqual(
                req.get_header("User-agent"), "ridian-mailbox-python/" + version("ridian-mailbox")
            )
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
            tokens.append(saved["setup_token"])
            if len(tokens) == 1:
                raise URLError("lost response")
            return Response(setup_result())

        self.box._transport.open.side_effect = send
        with self.assertRaises(MailboxError):
            self.box.setup()
        result = self.box.setup()
        self.assertEqual(tokens[0], tokens[1])
        self.assertEqual(result, setup_result()["mailbox"])
        self.assertNotIn("access_token", result)
        self.assertNotIn(tokens[0], repr(self.box))

    def test_empty_message_pages_do_not_stop_pagination(self):
        self.seed()
        self.box._transport.open.side_effect = [
            Response({"data": [], "next_cursor": "a&b"}),
            Response({"data": [{"id": "m1"}], "next_cursor": None}),
        ]
        self.assertEqual(list(self.box.iter_messages()), [{"id": "m1"}])
        self.assertIn("cursor=a%26b", self.box._transport.open.call_args.args[0].full_url)

    def test_event_cursor_requires_explicit_ack(self):
        self.seed()
        self.box._transport.open.return_value = Response(
            {"data": [], "next_cursor": "next", "has_more": False, "poll_after_ms": 5000}
        )
        self.box.events()
        self.assertNotIn("event_cursor", json.loads(self.path.read_text()))
        self.box.acknowledge_events("next")
        self.assertEqual(json.loads(self.path.read_text())["event_cursor"], "next")

    def test_errors_are_sanitized_and_429_is_respected(self):
        self.seed()
        self.box._transport.open.side_effect = HTTPError(
            "secret-url", 429, "secret-message", {"Retry-After": "30"}, io.BytesIO(b"secret-body")
        )
        with self.assertRaises(MailboxError) as error:
            self.box.status()
        self.assertEqual(error.exception.retry_after, 30)
        self.assertNotIn("secret", str(error.exception))
        calls = self.box._transport.open.call_count
        with self.assertRaises(MailboxError):
            self.box.status()
        self.assertEqual(self.box._transport.open.call_count, calls)

    def test_redirect_is_not_followed_and_origin_cannot_change(self):
        self.seed()
        self.box._transport.open.side_effect = HTTPError(
            "https://api.example.test", 302, "", {"Location": "https://other.example"}, None
        )
        with self.assertRaises(MailboxError) as error:
            self.box.status()
        self.assertEqual(error.exception.code, "redirect_refused")
        other = Mailbox(base_url="https://other.example", state=self.path)
        with self.assertRaises(ValueError):
            other.status()
        from ridian_mailbox.client import NoRedirect

        self.assertIsNone(
            NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example")
        )

    def test_ids_are_encoded_and_revoke_is_explicit(self):
        self.seed()
        self.box._transport.open.return_value = Response({"id": "m1"})
        self.box.message("id/with?query")
        self.assertTrue(
            self.box._transport.open.call_args.args[0].full_url.endswith("id%2Fwith%3Fquery")
        )
        response = Response(None)
        response.status = 204
        self.box._transport.open.return_value = response
        self.assertIsNone(self.box.revoke())
        self.assertEqual(self.box._transport.open.call_args.args[0].method, "DELETE")
        self.assertTrue(self.path.exists())

    def test_default_state_reuses_access_and_separates_ports(self):
        with patch("pathlib.Path.home", return_value=Path(self.directory.name)):
            first = Mailbox(base_url="https://api.example.test")
            second = Mailbox(base_url="https://api.example.test")
            other = Mailbox(base_url="https://api.example.test:8443")
        self.assertEqual(first.state_path, second.state_path)
        self.assertNotEqual(first.state_path, other.state_path)
        first._transport = Mock()
        first._transport.open.return_value = Response(setup_result())
        first.setup()
        self.assertEqual(first._state()["setup_token"], second._state()["setup_token"])

    def test_files_and_origin_are_validated_before_requests(self):
        with self.assertRaises(ValueError):
            Mailbox(base_url="https://api.example.test/path", state=self.path)
        self.seed()
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.box.status()


if __name__ == "__main__":
    unittest.main()
